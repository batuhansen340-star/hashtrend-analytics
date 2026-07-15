"""
Kahve & Tatlı Trend Radarı — rollup script'i.

Canlı Supabase'deki raw_mentions + trend_scores tablolarından watchlist
(config/food_watchlist.py) kavramlarını çeker, daily/weekly/monthly
pencerelerinde world/TR agregasyonu yapar ve docs/data/kahve.json üretir.

Şema v2: v1 alanları aynen korunur; ek olarak ülke-bazlı "countries" bloğu
üretilir (yalnız gerçek verisi olan ISO2 ülkeler; GLOBAL harita dışıdır).

LLM çağrısı YOK — salt REST (PostgREST) agregasyon.

Kullanım:
    python3 rollup_food.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
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
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "windows": {
            w: {"since": v["since"].isoformat(), "until": v["until"].isoformat()}
            for w, v in windows.items()
        },
        "items": items,
        "countries": countries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Kahve & Tatlı radar rollup → kahve.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"Çıktı JSON yolu (varsayılan: {DEFAULT_OUT})")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    logger.info(f"Rollup başlıyor — {len(WATCHLIST)} kavram, {len(all_variants())} varyant")

    try:
        payload = build_rollup(now)
    except Exception as e:
        logger.error(f"Rollup başarısız: {e}")
        sys.exit(1)

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
