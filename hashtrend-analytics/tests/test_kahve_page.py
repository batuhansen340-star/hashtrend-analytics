"""
docs/kahve.html yapısal testleri — HTMLParser ile tag dengesi + v3 sözleşme
metinleri + 'dış istek yok' garantisi.

Çalıştırma (paket kökünden):
    ./venv/bin/python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "docs" / "kahve.html"
DATA_PATH = REPO / "docs" / "data" / "kahve.json"

# İçeriği olmayan (kendini kapatan) HTML elementleri
_VOID = {"meta", "br", "link", "img", "input", "hr", "source", "wbr"}


class _BalanceParser(HTMLParser):
    """Aç/kapa tag dengesini doğrulayan basit parser (script/style CDATA'dır)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if not self.stack:
            self.errors.append(f"kapanış fazlası: </{tag}>")
            return
        if self.stack[-1] != tag:
            self.errors.append(
                f"tag uyumsuz: </{tag}> geldi, <{self.stack[-1]}> açıktı")
        else:
            self.stack.pop()


class TestKahveHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    def test_tag_dengesi(self):
        p = _BalanceParser()
        p.feed(self.html)
        p.close()
        self.assertEqual(p.errors, [], "HTML tag dengesi bozuk")
        self.assertEqual(p.stack, [], f"kapanmamış tag(lar): {p.stack}")

    def test_metodoloji_google_trends_paragrafi(self):
        self.assertIn(
            "Harita ayrıca Google Trends ülke ilgi endeksi (0-100, son 7 gün, "
            "göreli) kullanır — bahsetme sayısı değildir, o ülkedeki arama "
            "ilgisinin görece gücüdür",
            self.html,
            "metodoloji kutusunda Google Trends paragrafı olmalı",
        )

    def test_dis_istek_yok(self):
        # Sayfa yalnız ./data/kahve.json ve ./assets/world.svg çeker;
        # hiçbir mutlak http(s) URL'si olmamalı (CDN/analytics/font dahil).
        self.assertNotIn("https://", self.html)
        self.assertNotIn("http://", self.html)

    def test_v3_sozlesme_parcalari(self):
        # schema v3 kabulü + tek sinyal koşulu + geo katmanı fonksiyonları
        for needle in (
            "j.schema_version!==3",
            "function hasSignal(m)",
            "function geoConcepts()",
            "function mapValues(",
            "function mapChipHtml()",
            "bu kavram için henüz geo verisi yok",
            "Google Trends ilgisi (son 7 gün)",
            "bahsetme + Google Trends ilgisi (7g)",
            "📈 Google Trends ilgisi",
            "💬 Bahsetmeler",
        ):
            self.assertIn(needle, self.html, f"eksik: {needle!r}")

    def test_kahve_json_gecerli(self):
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        self.assertIn(data.get("schema_version"), (1, 2, 3))
        self.assertIsInstance(data.get("items"), list)
        # v3 verisi geldiyse geo sözleşmesini doğrula (v2'de alan hiç yok)
        geo = data.get("geo")
        if geo is not None:
            self.assertIsInstance(geo.get("concepts"), dict)
            for cid, entry in geo["concepts"].items():
                self.assertTrue(entry.get("term"), f"{cid}: term boş")
                self.assertTrue(entry.get("updated_at"), f"{cid}: updated_at boş")
                interest = entry.get("interest")
                self.assertIsInstance(interest, dict, f"{cid}: interest dict değil")
                for iso, val in interest.items():
                    self.assertRegex(iso, r"^[A-Z]{2}$", f"{cid}: ISO2 değil: {iso}")
                    self.assertIsInstance(val, int, f"{cid}/{iso}: int değil")
                    self.assertGreater(val, 0, f"{cid}/{iso}: 0 değer sızmış")


if __name__ == "__main__":
    unittest.main()
