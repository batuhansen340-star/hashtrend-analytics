"""
Kahve & Tatlı Trend Radarı — rollup script'i.

Canlı Supabase'deki raw_mentions + trend_scores tablolarından watchlist
(config/food_watchlist.py) kavramlarını çeker, daily/weekly/monthly
pencerelerinde world/TR agregasyonu yapar ve docs/data/kahve.json üretir.

Şema v2: v1 alanları aynen korunur; ek olarak ülke-bazlı "countries" bloğu
üretilir (yalnız gerçek verisi olan ISO2 ülkeler; GLOBAL harita dışıdır).

Şema v3: v2 alanları aynen korunur; ek olarak Google Trends
interest_by_region tabanlı "geo" bloğu üretilir. Her çalıştırmada en bayat
GEO_BATCH kavram tazelenir (rotasyon), kalanlar ve her tür hata durumunda
mevcut kahve.json'daki geo verisi AYNEN taşınır (carry-forward) — geo
katmanı rollup'ı asla düşürmez.

LLM çağrısı YOK — REST (PostgREST) agregasyon + pytrends.

Kullanım:
    python3 rollup_food.py [--out PATH]
    python3 rollup_food.py --self-test   # ağ gerektirmeyen birim testler
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Script başka bir cwd'den çalıştırılsa da paket importları çalışsın
_PKG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_DIR))

from loguru import logger  # noqa: E402

from config.food_watchlist import WATCHLIST, all_variants, concept_for  # noqa: E402
from core.database import db  # noqa: E402

# Varsayılan çıktı: <repo>/docs/data/kahve.json (repo kökü = paketin bir üstü)
DEFAULT_OUT = _PKG_DIR.parent / "docs" / "data" / "kahve.json"

PAGE_SIZE = 1000        # PostgREST sayfalama
FILTER_CHUNK = 12       # or=(ilike...) filtresine sokulacak varyant sayısı (URL sınırı)
# Zaman dilimi (gün): tek sorgu statement_timeout'a (57014) takılmasın diye.
# raw_mentions'ta topic üzerinde trigram GIN index var → geniş dilim sorunsuz.
# trend_scores'ta topic_name index'siz → geniş dilimde planner timeout'a giriyor.
SLICE_DAYS = {"raw_mentions": 15, "trend_scores": 2}
MIN_SLICE = timedelta(hours=6)  # 57014'te dilim ikiye bölünür, bu alt sınıra kadar

WINDOW_DELTAS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}

# Harita paneli için ülke başına en fazla kaç kavram listelensin
COUNTRY_TOP_N = 10

# ISO2 → Türkçe ülke adı (listede yoksa ISO kodu gösterilir)
COUNTRY_NAMES_TR = {
    "TR": "Türkiye", "US": "Amerika", "GB": "İngiltere", "JP": "Japonya",
    "DE": "Almanya", "ES": "İspanya", "BR": "Brezilya", "FR": "Fransa",
    "IN": "Hindistan", "AU": "Avustralya", "IT": "İtalya", "KR": "Güney Kore",
    "CA": "Kanada", "MX": "Meksika", "NL": "Hollanda", "SA": "Suudi Arabistan",
    "AE": "Birleşik Arap Emirlikleri", "RU": "Rusya", "CN": "Çin", "EG": "Mısır",
    "ID": "Endonezya", "PH": "Filipinler", "TH": "Tayland", "VN": "Vietnam",
    "MY": "Malezya", "SG": "Singapur", "PK": "Pakistan", "AZ": "Azerbaycan",
    "GR": "Yunanistan", "PT": "Portekiz", "PL": "Polonya", "SE": "İsveç",
    "NO": "Norveç", "DK": "Danimarka", "FI": "Finlandiya", "CH": "İsviçre",
    "AT": "Avusturya", "BE": "Belçika", "IE": "İrlanda", "UA": "Ukrayna",
    "AR": "Arjantin", "CL": "Şili", "CO": "Kolombiya", "ZA": "Güney Afrika",
    "NZ": "Yeni Zelanda", "IL": "İsrail", "QA": "Katar", "KW": "Kuveyt",
    "MA": "Fas", "NG": "Nijerya",
}


def _parse_ts(value: str) -> datetime:
    """PostgREST'ten gelen ISO zaman damgasını timezone-aware UTC'ye çevir."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _or_filter(column: str, variants: list[str]) -> str:
    """PostgREST or=(col.ilike.*v*,...) filtre string'i üret."""
    parts = []
    for v in variants:
        # Filtre söz dizimini bozacak karakterleri ayıkla (varyantlarda beklenmez)
        pat = v.replace(",", " ").replace("(", " ").replace(")", " ").strip()
        parts.append(f"{column}.ilike.*{pat}*")
    return ",".join(parts)


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _is_timeout(err: Exception) -> bool:
    return getattr(err, "code", None) == "57014" or "57014" in str(err)


def _fetch_slice(table: str, select_cols: str, topic_col: str, time_col: str,
                 start: datetime, end: datetime, chunk: list[str],
                 rows_by_id: dict) -> int:
    """
    Tek (varyant parçası × zaman dilimi) sorgusunu PAGE_SIZE sayfalarla çek.
    Statement timeout (57014) olursa dilimi ikiye bölüp tekrar dener.
    Döndürdüğü değer: yapılan sorgu sayısı.
    """
    n_queries = 0
    offset = 0
    try:
        while True:
            result = (
                db.client.table(table)
                .select(select_cols)
                .gte(time_col, start.isoformat())
                .lt(time_col, end.isoformat())
                .or_(_or_filter(topic_col, chunk))
                .order(time_col, desc=False)
                .order("id", desc=False)
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            n_queries += 1
            data = result.data or []
            for row in data:
                rows_by_id[row["id"]] = row
            if len(data) < PAGE_SIZE:
                return n_queries
            offset += PAGE_SIZE
    except Exception as e:
        if _is_timeout(e) and (end - start) > MIN_SLICE:
            mid = start + (end - start) / 2
            logger.warning(f"{table}: 57014 → dilim bölünüyor "
                           f"({start:%m-%d %H:%M} / {end:%m-%d %H:%M})")
            n_queries += _fetch_slice(table, select_cols, topic_col, time_col,
                                      start, mid, chunk, rows_by_id)
            n_queries += _fetch_slice(table, select_cols, topic_col, time_col,
                                      mid, end, chunk, rows_by_id)
            return n_queries
        raise


def _fetch_matching(table: str, select_cols: str, topic_col: str,
                    time_col: str, since: datetime, until: datetime) -> list[dict]:
    """
    Watchlist varyantlarıyla eşleşen satırları çek.

    Strateji: varyantlar FILTER_CHUNK'lık parçalara, zaman aralığı tablo bazlı
    SLICE_DAYS'lik dilimlere bölünür; her (parça × dilim) sorgusu PAGE_SIZE'lık
    sayfalarla gezilir. Aynı satır birden çok parçayla eşleşebilir → id dedup.
    """
    variants = all_variants()
    rows_by_id: dict = {}
    n_queries = 0
    slice_delta = timedelta(days=SLICE_DAYS[table])

    slice_start = since
    while slice_start < until:
        slice_end = min(slice_start + slice_delta, until)
        for chunk in _chunks(variants, FILTER_CHUNK):
            n_queries += _fetch_slice(table, select_cols, topic_col, time_col,
                                      slice_start, slice_end, chunk, rows_by_id)
        slice_start = slice_end

    logger.info(f"{table}: {len(rows_by_id)} eşleşen satır ({n_queries} sorgu)")
    return list(rows_by_id.values())


def _norm_country(value) -> str | None:
    """country kolonunu ISO2'ye normalize et; None/boş/'GLOBAL'/ISO2-dışı → None (harita dışı).

    ISO2 biçimi (2 ASCII harf) zorunlu: countries bloğu sözleşmesi "yalnız ISO2"
    der ve kahve.html anahtarı onclick attribute'una gömer — çöp değer sızmasın.
    """
    c = (value or "").strip().upper()
    if len(c) != 2 or not c.isascii() or not c.isalpha():
        return None  # boş, "GLOBAL" ve diğer ISO2-dışı değerler harita dışı
    return c


def _build_countries(country_counts: dict[str, dict[str, dict[str, dict[str, int]]]]) -> dict:
    """
    Ülke bazlı sayaçları v2 "countries" bloğuna çevir.

    Girdi: iso2 → pencere → concept_id → {"mentions", "prev_mentions"}.
    Kurallar: kavramlar mentions>0 + mentions DESC + en çok COUNTRY_TOP_N;
    ülke ancak en az bir penceresinde total_mentions>0 ise listeye girer.
    total_mentions = penceredeki TÜM kavram mention'larının toplamı (top-N değil).
    """
    countries: dict = {}
    for iso in sorted(country_counts):
        windows_out = {}
        has_data = False
        for wname in WINDOW_DELTAS:
            per_cid = country_counts[iso][wname]
            total = sum(e["mentions"] for e in per_cid.values())
            concepts = sorted(
                (
                    {"id": cid, "mentions": e["mentions"], "prev_mentions": e["prev_mentions"]}
                    for cid, e in per_cid.items()
                    if e["mentions"] > 0
                ),
                key=lambda c: (-c["mentions"], c["id"]),
            )[:COUNTRY_TOP_N]
            windows_out[wname] = {"total_mentions": total, "concepts": concepts}
            if total > 0:
                has_data = True
        if has_data:
            countries[iso] = {
                "name_tr": COUNTRY_NAMES_TR.get(iso, iso),
                "windows": windows_out,
            }
    return countries


def _empty_metric() -> dict:
    return {
        "mentions": 0, "appearances": 0,
        "avg_cts": None, "max_cts": None,
        "burst": 0, "prev_mentions": 0, "delta_pct": None,
        # geçici alan — avg hesabı için, çıktıdan silinir
        "_cts_sum": 0.0,
    }


def build_rollup(now: datetime) -> dict:
    """Canlı veriden JSON sözleşmesine uygun rollup dict'i üret."""
    windows = {
        name: {"since": now - delta, "until": now}
        for name, delta in WINDOW_DELTAS.items()
    }

    # ── Coarse fetch ────────────────────────────────────────────────────
    # raw_mentions: monthly prev penceresi için 60 gün geriye git.
    # trend_scores: prev için yalnız mentions gerekir (cts gerekmez) → 30 gün yeter.
    raw_rows = _fetch_matching(
        "raw_mentions", "id,topic,mention_count,country,collected_at",
        "topic", "collected_at", now - timedelta(days=60), now,
    )
    score_rows = _fetch_matching(
        "trend_scores", "id,topic_name,cts_score,is_burst,country,scored_at",
        "topic_name", "scored_at", now - timedelta(days=30), now,
    )

    if not raw_rows and not score_rows:
        raise RuntimeError("Hiç eşleşen satır gelmedi — DB/filtre kontrol et")

    # ── Agregasyon iskeleti ─────────────────────────────────────────────
    metrics: dict[str, dict] = {
        c["id"]: {w: {"world": _empty_metric(), "tr": _empty_metric()}
                  for w in WINDOW_DELTAS}
        for c in WATCHLIST
    }
    # sample_topics: kavram başına gerçek topic adları (küçük-harf dedup)
    topic_counter: dict[str, Counter] = {c["id"]: Counter() for c in WATCHLIST}
    topic_display: dict[str, dict[str, str]] = {c["id"]: {} for c in WATCHLIST}
    # v2: iso2 → pencere → concept_id → {"mentions", "prev_mentions"}
    country_counts: dict[str, dict[str, dict[str, dict[str, int]]]] = {}

    def _note_topic(cid: str, name: str, weight: int) -> None:
        key = name.strip().lower()
        if not key:
            return
        topic_counter[cid][key] += weight
        topic_display[cid].setdefault(key, name.strip())

    # ── raw_mentions → mentions + prev_mentions ─────────────────────────
    for row in raw_rows:
        cid = concept_for(row.get("topic") or "")
        if cid is None:
            continue  # ilike kaba eşleşti ama kesin eşleşme yok
        ts = _parse_ts(row["collected_at"])
        count = int(row.get("mention_count") or 0)
        iso = _norm_country(row.get("country"))
        is_tr = iso == "TR"
        _note_topic(cid, row.get("topic") or "", count)

        for wname, delta in WINDOW_DELTAS.items():
            since = windows[wname]["since"]
            prev_since = since - delta
            scopes = ["world"] + (["tr"] if is_tr else [])
            if since <= ts < now:
                bucket = "mentions"
            elif prev_since <= ts < since:
                bucket = "prev_mentions"
            else:
                continue
            for s in scopes:
                metrics[cid][wname][s][bucket] += count
            if iso is not None:
                per_win = country_counts.setdefault(
                    iso, {w: {} for w in WINDOW_DELTAS})
                entry = per_win[wname].setdefault(
                    cid, {"mentions": 0, "prev_mentions": 0})
                entry[bucket] += count

    # ── trend_scores → appearances / avg_cts / max_cts / burst ─────────
    for row in score_rows:
        cid = concept_for(row.get("topic_name") or "")
        if cid is None:
            continue
        ts = _parse_ts(row["scored_at"])
        cts = float(row.get("cts_score") or 0.0)
        is_burst = bool(row.get("is_burst"))
        is_tr = (row.get("country") or "").strip().upper() == "TR"
        _note_topic(cid, row.get("topic_name") or "", 1)

        for wname in WINDOW_DELTAS:
            if not (windows[wname]["since"] <= ts < now):
                continue
            for s in (["world"] + (["tr"] if is_tr else [])):
                m = metrics[cid][wname][s]
                m["appearances"] += 1
                m["_cts_sum"] += cts
                m["max_cts"] = cts if m["max_cts"] is None else max(m["max_cts"], cts)
                if is_burst:
                    m["burst"] += 1

    # ── Türetilen alanlar + temizlik ────────────────────────────────────
    for cid in metrics:
        for wname in WINDOW_DELTAS:
            for s in ("world", "tr"):
                m = metrics[cid][wname][s]
                if m["appearances"] > 0:
                    m["avg_cts"] = round(m["_cts_sum"] / m["appearances"], 2)
                    m["max_cts"] = round(m["max_cts"], 2)
                del m["_cts_sum"]
                if m["mentions"] == 0 and m["prev_mentions"] == 0:
                    m["delta_pct"] = None
                else:
                    m["delta_pct"] = round(
                        (m["mentions"] - m["prev_mentions"])
                        / max(m["prev_mentions"], 1) * 100, 1
                    )

    # ── Item listesi (monthly world mentions'a göre sıralı) ─────────────
    items = []
    for c in WATCHLIST:
        cid = c["id"]
        samples = [topic_display[cid][key]
                   for key, _ in topic_counter[cid].most_common(5)]
        items.append({
            "id": cid,
            "name_tr": c["name_tr"],
            "name_en": c["name_en"],
            "group": c["group"],
            "metrics": metrics[cid],
            "sample_topics": samples,
        })
    items.sort(key=lambda it: (-it["metrics"]["monthly"]["world"]["mentions"], it["id"]))

    # ── v2: ülke-bazlı harita bloğu ─────────────────────────────────────
    countries = _build_countries(country_counts)
    logger.info(f"countries: {len(countries)} ülke → {', '.join(sorted(countries))}")

    return {
        "schema_version": 3,
        "generated_at": now.isoformat(),
        "windows": {
            w: {"since": v["since"].isoformat(), "until": v["until"].isoformat()}
            for w, v in windows.items()
        },
        "items": items,
        "countries": countries,
    }


# ── v3: Google Trends geo katmanı ───────────────────────────────────────
GEO_NOTE = ("Google Trends interest_by_region • timeframe: now 7-d • "
            "0-100 göreli ilgi endeksi")
GEO_TIMEFRAME = "now 7-d"
GEO_BATCH = 12   # her çalıştırmada tazelenecek en bayat/eksik kavram sayısı
GEO_SLEEP = 3    # istekler arası bekleme (saniye) — rate-limit güvenliği


def geo_term_for(concept: dict) -> str:
    """Kavramın Google Trends sorgu terimini seç.

    Öncelik: watchlist'teki opsiyonel "geo_term" alanı. Yoksa İngilizce-uygun
    (ASCII) ilk varyant kullanılır ('*' ek-toleransı işareti soyulmuş);
    hiç ASCII varyant yoksa ilk varyanta düşülür.
    """
    term = concept.get("geo_term")
    if term:
        return term
    variants = [v.rstrip("*").strip() for v in concept["variants"]]
    for v in variants:
        if v.isascii():
            return v
    return variants[0]


def _df_to_interest(df, term: str) -> dict[str, int]:
    """interest_by_region DataFrame'ini {ISO2: endeks>0} sözlüğüne çevir.

    inc_geo_code=True çıktısında 'geoCode' kolonu ISO2 ülke kodu, `term`
    kolonu 0-100 göreli ilgi endeksidir. Yalnız endeksi >0 olan ve geçerli
    ISO2 kodu taşıyan satırlar alınır; bozuk satırlar sessizce atlanır.
    """
    out: dict[str, int] = {}
    if df is None or getattr(df, "empty", True):
        return out
    if "geoCode" not in df.columns or term not in df.columns:
        return out
    for code, value in zip(df["geoCode"], df[term]):
        iso = _norm_country(code if isinstance(code, str) else None)
        if iso is None:
            continue
        try:
            val = int(value)
        except (TypeError, ValueError):
            continue  # NaN / sayı olmayan değer
        if val > 0:
            out[iso] = val
    return out


def _load_previous_geo(path: Path) -> dict:
    """Mevcut kahve.json'dan geo bloğunu oku (carry-forward tabanı).

    Dosya yoksa / bozuksa / geo alanı yoksa boş iskelet döner — asla exception
    fırlatmaz (v2→v3 geçişinde geo alanı henüz yok).
    """
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        concepts = (prev.get("geo") or {}).get("concepts")
        if isinstance(concepts, dict):
            return {"note": GEO_NOTE, "concepts": dict(concepts)}
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Önceki geo bloğu okunamadı ({path}): {e}")
    return {"note": GEO_NOTE, "concepts": {}}


def _stalest_concepts(prev_concepts: dict, batch: int = GEO_BATCH) -> list[dict]:
    """Bu turda tazelenecek kavramları seç (rotasyon).

    Sıralama: geo verisi hiç olmayanlar önce, sonra updated_at'i en eski
    olanlar (ISO8601 string'ler kronolojik sıralanır). En bayat `batch`
    kavram döner → ~10 saatte tüm watchlist bir tur tazelenmiş olur.
    """
    def staleness(c: dict) -> str:
        entry = prev_concepts.get(c["id"])
        if not isinstance(entry, dict):
            return ""  # eksik/bozuk kayıt → en bayat
        val = entry.get("updated_at")
        # str değilse (bozuk/elle düzenlenmiş dosya) sorted() TypeError'la
        # patlayıp geo tazelemeyi kalıcı öldürmesin → en bayat say
        return val if isinstance(val, str) else ""
    return sorted(WATCHLIST, key=staleness)[:batch]


def build_geo(prev_geo: dict, now: datetime) -> dict:
    """Google Trends "geo" bloğunu üret (rotasyon + carry-forward).

    En bayat GEO_BATCH kavram pytrends ile tazelenir; kalanlar ve başarısız
    çekimler (429/timeout/bağlantı/boş sonuç) önceki değerleriyle AYNEN
    taşınır. pytrends import edilemiyor ya da Trends'e ulaşılamıyorsa blok
    olduğu gibi döner — bu fonksiyon rollup'ı asla düşürmez.
    """
    geo = {"note": GEO_NOTE, "concepts": dict(prev_geo.get("concepts") or {})}

    try:
        from pytrends.request import TrendReq
    except Exception as e:
        logger.warning(f"geo: pytrends import edilemedi — carry-forward: {e}")
        return geo

    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
    except Exception as e:
        logger.warning(f"geo: TrendReq kurulamadı — carry-forward: {e}")
        return geo

    targets = _stalest_concepts(geo["concepts"])
    logger.info(f"geo: {len(targets)} kavram tazelenecek → "
                f"{', '.join(c['id'] for c in targets)}")
    refreshed = 0
    for i, c in enumerate(targets):
        if i:
            time.sleep(GEO_SLEEP)
        term = geo_term_for(c)
        try:
            pt.build_payload([term], timeframe=GEO_TIMEFRAME)
            df = pt.interest_by_region(
                resolution="COUNTRY", inc_low_vol=True, inc_geo_code=True)
        except Exception as e:
            logger.warning(f"geo: {c['id']} ({term!r}) çekilemedi, atlandı: {e}")
            continue  # eski veri carry-forward ile korunur
        interest = _df_to_interest(df, term)
        if not interest:
            logger.warning(f"geo: {c['id']} ({term!r}) boş sonuç — eski veri korunuyor")
            continue
        geo["concepts"][c["id"]] = {
            "term": term,
            "updated_at": now.isoformat(),
            "interest": interest,
        }
        refreshed += 1
    logger.info(f"geo: {refreshed}/{len(targets)} kavram tazelendi, "
                f"toplam {len(geo['concepts'])} kavramda geo verisi var")
    return geo


def _self_test() -> None:
    """Ağ gerektirmeyen birim testler — pytrends mock'lanmaz, sahte DataFrame
    ile df→interest dönüşümü + terim seçimi + rotasyon + carry-forward tabanı
    doğrulanır."""
    import tempfile

    import pandas as pd

    # ── _df_to_interest: interest_by_region(inc_geo_code=True) örnek kopyası ─
    df = pd.DataFrame(
        {"geoCode": ["US", "JP", "tr", "XKX", "", None],
         "matcha": [87, 72, 5, 50, 10, 3]},
        index=pd.Index(["United States", "Japan", "Türkiye",
                        "Kosovo", "?", "?"], name="geoName"),
    )
    assert _df_to_interest(df, "matcha") == {"US": 87, "JP": 72, "TR": 5}, \
        "geçerli ISO2 + >0 satırlar alınmalı, küçük harf normalize edilmeli"
    df0 = pd.DataFrame({"geoCode": ["US", "JP"], "salep": [0, 0]})
    assert _df_to_interest(df0, "salep") == {}, "0 endeksli satırlar elenmeli"
    dfnan = pd.DataFrame({"geoCode": ["US"], "salep": [float("nan")]})
    assert _df_to_interest(dfnan, "salep") == {}, "NaN sessizce atlanmalı"
    assert _df_to_interest(df, "yok-boyle-kolon") == {}, "term kolonu yoksa boş"
    assert _df_to_interest(pd.DataFrame({"matcha": [5]}), "matcha") == {}, \
        "geoCode kolonu yoksa boş"
    assert _df_to_interest(pd.DataFrame(), "matcha") == {}
    assert _df_to_interest(None, "matcha") == {}

    # ── geo_term_for: opsiyonel geo_term > ASCII ilk varyant ────────────
    by_id = {c["id"]: c for c in WATCHLIST}
    assert geo_term_for(by_id["magnolia"]) == "magnolia dessert"
    assert geo_term_for(by_id["turk-kahvesi"]) == "turkish coffee"
    assert geo_term_for(by_id["sutlac"]) == "rice pudding"
    assert geo_term_for(by_id["matcha"]) == "matcha"
    assert geo_term_for(by_id["baklava"]) == "baklava"       # '*' soyulur
    assert geo_term_for(by_id["creme-brulee"]) == "creme brulee"  # ASCII ilk
    assert all(geo_term_for(c).strip() for c in WATCHLIST)

    # ── _stalest_concepts: eksikler önce, sonra en eski updated_at ──────
    ids = [c["id"] for c in WATCHLIST]
    # İlk 4 kavramın geo verisi yok; kalanların updated_at'i liste sırasıyla artar
    prev = {cid: {"updated_at": f"2026-07-15T00:{n:02d}:00+00:00", "term": "x",
                  "interest": {"US": 1}}
            for n, cid in enumerate(ids[4:])}
    picked = [c["id"] for c in _stalest_concepts(prev)]
    assert len(picked) == GEO_BATCH
    assert picked[:4] == ids[:4], "geo verisi olmayanlar önce tazelenmeli"
    assert picked[4:] == ids[4:GEO_BATCH], \
        "kalan slotlar en eski updated_at sırasıyla dolmalı"
    # Bozuk carry-forward kaydı (dict değil / updated_at str değil) rotasyonu
    # düşürmemeli — 'hiç veri yok' gibi en bayat sayılır
    corrupt = dict(prev)
    corrupt[ids[4]] = "bozuk-kayit"
    corrupt[ids[5]] = {"updated_at": 12345}
    picked2 = [c["id"] for c in _stalest_concepts(corrupt)]
    assert picked2[:6] == ids[:6], \
        "bozuk kayıtlar en bayat sayılmalı (exception yok, rotasyon sürer)"

    # ── _load_previous_geo: yok/bozuk/geo'suz dosya → boş iskelet ───────
    assert _load_previous_geo(Path("/yok/boyle/bir/kahve.json")) == \
        {"note": GEO_NOTE, "concepts": {}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write("{bozuk json")
        broken = Path(f.name)
    assert _load_previous_geo(broken) == {"note": GEO_NOTE, "concepts": {}}
    broken.write_text(json.dumps({"schema_version": 2, "items": []}), encoding="utf-8")
    assert _load_previous_geo(broken) == {"note": GEO_NOTE, "concepts": {}}
    sample = {"matcha": {"term": "matcha",
                         "updated_at": "2026-07-15T00:00:00+00:00",
                         "interest": {"US": 87, "JP": 72}}}
    broken.write_text(json.dumps({"schema_version": 3,
                                  "geo": {"note": "eski not", "concepts": sample}}),
                      encoding="utf-8")
    assert _load_previous_geo(broken)["concepts"] == sample, \
        "mevcut geo.concepts AYNEN taşınmalı"
    broken.unlink()

    print("self-test OK — geo katmanı birim testleri geçti")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kahve & Tatlı radar rollup → kahve.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"Çıktı JSON yolu (varsayılan: {DEFAULT_OUT})")
    parser.add_argument("--self-test", action="store_true",
                        help="Ağ gerektirmeyen geo birim testlerini çalıştır ve çık")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    now = datetime.now(timezone.utc).replace(microsecond=0)
    logger.info(f"Rollup başlıyor — {len(WATCHLIST)} kavram, {len(all_variants())} varyant")

    try:
        payload = build_rollup(now)
    except Exception as e:
        logger.error(f"Rollup başarısız: {e}")
        sys.exit(1)

    # ── v3: geo katmanı — hangi hata olursa olsun rollup düşmez,
    # mevcut kahve.json'daki geo bloğu asla silinmez/boşaltılmaz.
    prev_geo = _load_previous_geo(args.out)
    try:
        payload["geo"] = build_geo(prev_geo, now)
    except Exception as e:
        logger.warning(f"geo: beklenmedik hata — carry-forward: {e}")
        payload["geo"] = prev_geo

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"Çıktı yazılamadı ({args.out}): {e}")
        sys.exit(1)

    nonzero = sum(
        1 for it in payload["items"]
        if it["metrics"]["monthly"]["world"]["mentions"] > 0
        or it["metrics"]["monthly"]["world"]["appearances"] > 0
    )
    logger.info(f"kahve.json yazıldı → {args.out} "
                f"({len(payload['items'])} kavram, {nonzero} tanesinde monthly veri var)")


if __name__ == "__main__":
    main()
