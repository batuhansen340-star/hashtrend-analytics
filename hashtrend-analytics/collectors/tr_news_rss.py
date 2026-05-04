"""
TR Gündem RSS Collector — Türkiye haber kaynakları RSS feed'leri.

Hürriyet, Onedio gibi TR ana haber sitelerinin RSS feed'lerinden gündem
haberleri çekilir. TikTok/Instagram'dan veri alamadığımız için TR pazar
derinliğini bu kaynaklarla artırıyoruz.

Strateji: feedparser ile RSS XML parse et, başlık + tarih → RawMention.
Sadece son 24 saat içindeki haberler alınır (gündem-spesifik).
"""

import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import requests
import xml.etree.ElementTree as ET
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


# Aktif feed'ler — 2026-05-05 health check'inde 200 + valid XML + >=10 item dönen
# kaynaklar. Onedio /rss endpoint'i HTML dönmeye başladı (kapatmış olabilirler) —
# bu liste yerine 7 ana akım TR haber kaynağına genişletildi (~300 mention/run).
RSS_FEEDS = [
    ("hurriyet",   "https://www.hurriyet.com.tr/rss/anasayfa"),
    ("milliyet",   "https://www.milliyet.com.tr/rss/rssNew/gundemRss.xml"),
    ("sabah",      "https://www.sabah.com.tr/rss/anasayfa.xml"),
    ("haberturk",  "https://www.haberturk.com/rss"),
    ("cumhuriyet", "https://www.cumhuriyet.com.tr/rss/1.xml"),
    ("cnnturk",    "https://www.cnnturk.com/feed/rss/all/news"),
    ("trthaber",   "https://www.trthaber.com/sondakika.rss"),
    ("aa",         "https://www.aa.com.tr/tr/rss/default?cat=guncel"),
]

# Recency cutoff — son N saat içindeki haberleri al
HOURS_BACK = 24


class TRNewsRSSCollector(BaseCollector):
    SOURCE_NAME = "tr_news_rss"
    COLLECT_INTERVAL_MINUTES = 120

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
        for source_id, url in RSS_FEEDS:
            try:
                mentions = self._fetch_feed(source_id, url, cutoff)
                all_mentions.extend(mentions)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[tr_news_rss] {source_id} hatasi: {e}")
        return all_mentions

    def _fetch_feed(self, source_id: str, url: str, cutoff: datetime) -> list[RawMention]:
        """RSS XML'i parse et, son N saat içindeki başlıkları RawMention olarak döndür."""
        resp = self.session.get(url, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"[tr_news_rss] {source_id} HTTP {resp.status_code}")
            return []
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning(f"[tr_news_rss] {source_id} XML parse fail: {e}")
            return []
        # RSS 2.0 formatı: channel > item > title/pubDate/link
        items = root.findall(".//item")
        mentions = []
        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            date_el = item.find("pubDate")
            if title_el is None or not (title_el.text or "").strip():
                continue
            title = title_el.text.strip()
            link = (link_el.text or "").strip() if link_el is not None else None
            # pubDate: "Sun, 04 May 2026 10:00:00 +0300" formatı
            pub_dt = None
            if date_el is not None and date_el.text:
                try:
                    pub_dt = parsedate_to_datetime(date_el.text.strip())
                    # tz-aware → naive UTC
                    if pub_dt.tzinfo:
                        pub_dt = pub_dt.astimezone().replace(tzinfo=None)
                except Exception:
                    pub_dt = None
            if pub_dt and pub_dt < cutoff:
                continue
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=title,
                mention_count=1,  # RSS'de score yok; eşit ağırlık
                country="TR",
                url=link,
                raw_data={
                    "feed": source_id,
                    "type": "tr_news_rss",
                    "pub_date": pub_dt.isoformat() if pub_dt else None,
                },
            ))
        logger.info(f"[tr_news_rss] {source_id}: {len(mentions)} haber")
        return mentions


if __name__ == "__main__":
    collector = TRNewsRSSCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} TR haber")
    for m in mentions[:15]:
        feed = m.raw_data.get("feed", "?")
        print(f"  [{feed:>10}] {m.topic[:80]}")
