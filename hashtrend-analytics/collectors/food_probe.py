"""
Food Probe Collector — Google News RSS'ten kahve/tatlı watchlist sinyali.

Yemek terimleri organik akışta seyrek görünür; bu collector watchlist'teki
(config/food_watchlist.py) HER kavram için Google News aramasını iki
edisyonda (EN/US + TR) sorgulayarak sinyal yoğunluğunu garanti eder.
Veri %100 gerçek haber başlığıdır — sentetik hiçbir şey üretilmez.

Kaynak: https://news.google.com/rss/search?q=<term> — auth yok, ücretsiz.
Her (kavram × edisyon) için son 48 saatteki haber sayısı = mention_count,
topic = en güncel başlık (rollup'ın concept_for eşleşmesi için gerekirse
kavramın birincil varyantı öne eklenir).

Nezaket: istekler arası 0.5-1s bekleme, feed başına 10s timeout.
~57 kavram × 2 edisyon ≈ 114 istek ≈ +2 dk pipeline süresi — kabul edildi.
"""

import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests
from loguru import logger

from collectors.base import BaseCollector
from config.food_watchlist import WATCHLIST, concept_for
from core.models import RawMention
from rollup_food import geo_term_for  # sorgu terimi mantığı tek kaynaktan

# Google News edisyonları: (etiket, URL query eki, RawMention.country)
# EN edisyonu global sinyal sayılır → country=None (GLOBAL).
EDITIONS = [
    ("EN", "hl=en-US&gl=US&ceid=US:en", None),
    ("TR", "hl=tr&gl=TR&ceid=TR:tr", "TR"),
]

# Recency cutoff — yalnız son N saat içindeki haberler sayılır
HOURS_BACK = 48


def tr_term_for(concept: dict) -> str:
    """Kavramın TR edisyonu sorgu terimini seç.

    Öncelik: '*' işaretli (Türkçe ek toleranslı → Türkçe yazımlı) ilk
    varyant > ASCII olmayan (Türkçe karakterli) ilk varyant > name_tr
    (parantez ve '/' kuyruğu temizlenmiş) — AMA yalnız bir varyantla
    birebir örtüşüyorsa. Aksi halde EN terimine düşülür: kısaltılmış
    name_tr fazla muğlak olabiliyor (ör. 'Yuzu' → Google News TR aksan
    normalizasyonuyla 'yüzü' kelimesine, yani %100 yanlış-pozitife çakışır).
    """
    for v in concept["variants"]:
        if v.endswith("*"):
            return v.rstrip("*").strip()
    for v in concept["variants"]:
        if not v.isascii():
            return v.strip()
    name = re.sub(r"\s*\(.*?\)", "", concept["name_tr"]).split("/")[0].strip()
    if name.lower() in {v.rstrip("*").strip().lower() for v in concept["variants"]}:
        return name
    return geo_term_for(concept)


class FoodProbeCollector(BaseCollector):
    SOURCE_NAME = "food_probe"
    COLLECT_INTERVAL_MINUTES = 720  # pipeline zaten günde iki kez çalışıyor

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HashTrendAnalytics/2.0 (https://hashtrend.app)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        })

    def collect(self) -> list[RawMention]:
        all_mentions = []
        cutoff = datetime.utcnow() - timedelta(hours=HOURS_BACK)
        for concept in WATCHLIST:
            for edition, url_params, country in EDITIONS:
                term = geo_term_for(concept) if edition == "EN" else tr_term_for(concept)
                try:
                    mention = self._probe(concept, term, edition, url_params, country, cutoff)
                    if mention:
                        all_mentions.append(mention)
                except Exception as e:
                    # Tek kavram düşerse kalanlar toplanmaya devam eder
                    logger.warning(f"[food_probe] {concept['id']}/{edition} hatasi: {e}")
                time.sleep(random.uniform(0.5, 1.0))  # nezaket beklemesi
        return all_mentions

    def _probe(self, concept: dict, term: str, edition: str, url_params: str,
               country: str | None, cutoff: datetime) -> RawMention | None:
        """Tek (kavram × edisyon) sorgusu → son 48h haber sayısı + en güncel başlık."""
        url = f"{self.BASE_URL}?q={quote_plus(term)}&{url_params}"
        resp = self.session.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"[food_probe] {concept['id']}/{edition} HTTP {resp.status_code}")
            return None
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning(f"[food_probe] {concept['id']}/{edition} XML parse fail: {e}")
            return None

        # RSS 2.0: channel > item > title/pubDate/link
        recent: list[tuple[datetime, str, str]] = []
        for item in root.findall(".//item"):
            title_el = item.find("title")
            date_el = item.find("pubDate")
            link_el = item.find("link")
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not title:
                continue
            pub_dt = None
            if date_el is not None and date_el.text:
                try:
                    pub_dt = parsedate_to_datetime(date_el.text.strip())
                    if pub_dt.tzinfo:  # tz-aware → naive UTC
                        pub_dt = pub_dt.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    pub_dt = None
            if pub_dt is None or pub_dt < cutoff:
                continue
            link = (link_el.text or "").strip() if link_el is not None else ""
            recent.append((pub_dt, title, link))

        if not recent:
            logger.debug(f"[food_probe] {concept['id']}/{edition} '{term}': 0 haber ({HOURS_BACK}h)")
            return None

        recent.sort(key=lambda r: r[0], reverse=True)
        newest_dt, newest_title, newest_link = recent[0]

        # topic rollup'ın concept_for eşleşmesine girer — kavramı GERÇEKTEN
        # yakalayan en güncel başlığı seç (exclude'a takılanlar elenir);
        # hiçbiri yakalamıyorsa en güncel başlığın önüne birincil varyantı ekle.
        topic, link = None, None
        for _, title, item_link in recent:
            if concept_for(title) == concept["id"]:
                topic, link = title, item_link
                break
        if topic is None:
            primary = concept["variants"][0].rstrip("*").strip()
            topic, link = f"{primary} — {newest_title}", newest_link

        logger.info(f"[food_probe] {concept['id']}/{edition} '{term}': {len(recent)} haber")
        return RawMention(
            source=self.SOURCE_NAME,
            topic=topic,
            mention_count=len(recent),
            country=country,
            url=link or None,
            raw_data={
                "concept_id": concept["id"],
                "term": term,
                "edition": edition,
                "newest_pub": newest_dt.isoformat(),
                "type": "food_probe",
            },
        )


if __name__ == "__main__":
    collector = FoodProbeCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} food probe mention")
    for m in mentions[:10]:
        ed = m.raw_data.get("edition", "?")
        print(f"  [{ed}] [{m.mention_count:>3}] {m.topic[:90]}")
