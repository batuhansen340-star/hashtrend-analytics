"""
rollup_food geo katmanı birim testleri — KAYITLI GERÇEK pytrends yanıtı ile.

Fixture: tests/fixtures/interest_by_region_matcha.json — 2026-07-16'da canlı
pytrends 4.9.2 interest_by_region(resolution='COUNTRY', inc_low_vol=True,
inc_geo_code=True, timeframe='now 7-d', term='matcha') çıktısının kaydı
(orient='split'). Testler AĞ KULLANMAZ: TrendReq mock'lanır, bu ağda
trends.google.com her zaman erişilebilir olmayabilir (canlı çekim CI'da).

Kapsanan hata yolları (hepsi graceful — rollup asla düşmez, geo silinmez):
    * pytrends kurulamadı / TrendReq patladı  → tam carry-forward
    * istek exception'ı (429/timeout/ağ)      → kavram bazlı carry-forward
    * boş / kolonsuz DataFrame                → kavram bazlı carry-forward

Çalıştırma (paket kökünden):
    ./venv/bin/python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

import pandas as pd  # noqa: E402  (pytrends bağımlılığı, venv'de kurulu)

import rollup_food as rf  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "interest_by_region_matcha.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
NOW = datetime(2026, 7, 16, 9, 0, 0, tzinfo=timezone.utc)


def fixture_df(term: str = "matcha") -> pd.DataFrame:
    """Kayıtlı yanıtı pytrends'in döndürdüğü DataFrame biçiminde kur."""
    df = pd.DataFrame(
        FIXTURE["data"],
        index=pd.Index(FIXTURE["index"], name="geoName"),
        columns=FIXTURE["columns"],
    )
    if term != "matcha":
        df = df.rename(columns={"matcha": term})
    return df


class FakeTrendReq:
    """Ağsız TrendReq: kayıtlı fixture'ı döndürür (istenirse patlar/boş döner)."""

    calls: list[str] = []          # build_payload'a gelen terimler (sınıf bazlı)
    mode = "ok"                    # "ok" | "raise" | "empty"

    def __init__(self, *a, **kw):
        self._term = None

    def build_payload(self, kw_list, timeframe=None, **kw):
        if self.mode == "raise":
            raise ConnectionError("trends.google.com erişilemedi (simülasyon)")
        self._term = kw_list[0]
        FakeTrendReq.calls.append(self._term)

    def interest_by_region(self, **kw):
        if self.mode == "empty":
            return pd.DataFrame()
        return fixture_df(self._term)


def patched_build_geo(prev_geo: dict, mode: str = "ok") -> dict:
    """build_geo'yu ağsız (mock TrendReq + uyutmasız) çalıştır."""
    FakeTrendReq.calls = []
    FakeTrendReq.mode = mode
    with patch("pytrends.request.TrendReq", FakeTrendReq), \
         patch("rollup_food.time.sleep"):
        return rf.build_geo(prev_geo, NOW)


class TestFixtureParse(unittest.TestCase):
    """_df_to_interest × kayıtlı gerçek yanıt."""

    def test_gercek_yanit_sozlesmeye_uyar(self):
        interest = rf._df_to_interest(fixture_df(), "matcha")
        self.assertTrue(interest, "gerçek yanıttan boş interest çıkmamalı")
        # Kayıt anındaki tepe değer: Singapur = 100
        self.assertEqual(interest.get("SG"), 100)
        for iso, val in interest.items():
            self.assertRegex(iso, r"^[A-Z]{2}$", f"ISO2 değil: {iso}")
            self.assertIsInstance(val, int)
            self.assertTrue(0 < val <= 100, f"{iso}: aralık dışı {val}")
        # 0 endeksli satırlar elenmiş olmalı (250 ülkenin hepsi >0 değil)
        self.assertLess(len(interest), len(FIXTURE["index"]))

    def test_bos_ve_bozuk_girdiler(self):
        self.assertEqual(rf._df_to_interest(None, "matcha"), {})
        self.assertEqual(rf._df_to_interest(pd.DataFrame(), "matcha"), {})
        self.assertEqual(rf._df_to_interest(fixture_df(), "yok-kolon"), {})
        no_geocode = fixture_df().drop(columns=["geoCode"])
        self.assertEqual(rf._df_to_interest(no_geocode, "matcha"), {})


class TestBuildGeo(unittest.TestCase):
    """build_geo: taze çekim + rotasyon + tüm carry-forward yolları."""

    PREV = {
        "note": rf.GEO_NOTE,
        "concepts": {
            "matcha": {
                "term": "matcha",
                "updated_at": "2026-07-10T00:00:00+00:00",
                "interest": {"JP": 95, "US": 87},
            }
        },
    }

    def test_taze_cekim(self):
        geo = patched_build_geo({"note": rf.GEO_NOTE, "concepts": {}})
        self.assertEqual(geo["note"], rf.GEO_NOTE)
        self.assertEqual(len(FakeTrendReq.calls), rf.GEO_BATCH,
                         "koşu başına tam GEO_BATCH kavram sorgulanmalı")
        self.assertEqual(len(geo["concepts"]), rf.GEO_BATCH)
        for cid, entry in geo["concepts"].items():
            self.assertEqual(entry["updated_at"], NOW.isoformat())
            self.assertTrue(entry["interest"], f"{cid}: interest boş")
            self.assertTrue(entry["term"])

    def test_ag_hatasi_tam_carry_forward(self):
        geo = patched_build_geo(json.loads(json.dumps(self.PREV)), mode="raise")
        self.assertEqual(geo["concepts"], self.PREV["concepts"],
                         "ağ hatasında önceki geo AYNEN taşınmalı")

    def test_bos_sonuc_eskiyi_ezmez(self):
        geo = patched_build_geo(json.loads(json.dumps(self.PREV)), mode="empty")
        self.assertEqual(geo["concepts"]["matcha"], self.PREV["concepts"]["matcha"],
                         "boş DataFrame eski interest'i silmemeli")

    def test_pytrends_kurulamazsa_carry_forward(self):
        def boom(*a, **kw):
            raise RuntimeError("TrendReq kurulamadı (simülasyon)")
        with patch("pytrends.request.TrendReq", boom), \
             patch("rollup_food.time.sleep"):
            geo = rf.build_geo(json.loads(json.dumps(self.PREV)), NOW)
        self.assertEqual(geo["concepts"], self.PREV["concepts"])

    def test_rotasyon_eskisi_once(self):
        # matcha'nın verisi taze DEĞİL ama diğerlerinden yeni olsun →
        # önce hiç verisi olmayanlar sorgulanır, matcha en sona kalır.
        prev = {"note": rf.GEO_NOTE, "concepts": {
            "matcha": {"term": "matcha",
                       "updated_at": "2099-01-01T00:00:00+00:00",
                       "interest": {"JP": 95}},
        }}
        patched_build_geo(prev)
        matcha_term = rf.geo_term_for(
            next(c for c in rf.WATCHLIST if c["id"] == "matcha"))
        self.assertNotIn(matcha_term, FakeTrendReq.calls,
                         "en taze kavram bu turda sorgulanmamalı")


if __name__ == "__main__":
    unittest.main()
