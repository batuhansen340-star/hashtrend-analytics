"""
Webrazzi RSS Collector — TR startup ekosistemi haberleri.

Her haber başlığı tek bir mention olarak gönderilir. Normalizer cross-source
clustering yapıyor zaten (Webrazzi haberi + diğer haber sitelerindeki aynı
haber otomatik gruplanır). Eski Trend Radar pattern (keyword frequency)
HashTrend'e uygun değildi: "göre", "satın" gibi tek kelimeler en sık tekrar
edilenler olarak topa çıkıyordu.
"""

import feedparser
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


class WebrazziCollector(BaseCollector):
    SOURCE_NAME = "webrazzi"
    COLLECT_INTERVAL_MINUTES = 60

    URL = "https://webrazzi.com/feed/"
    MAX_ENTRIES = 40

    def collect(self) -> list[RawMention]:
        try:
            feed = feedparser.parse(self.URL)
            entries = feed.entries[: self.MAX_ENTRIES] if feed and feed.entries else []
            if not entries:
                logger.warning("[webrazzi] RSS boş")
                return []

            mentions: list[RawMention] = []
            for e in entries:
                title = (e.get("title") or "").strip()
                if not title or len(title) < 10:
                    continue
                link = e.get("link") or ""
                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=title,
                    mention_count=1,
                    country="TR",
                    url=link,
                    raw_data={
                        "type": "webrazzi_article",
                        "summary": (e.get("summary") or "")[:300],
                    },
                    collected_at=self.collected_at,
                ))
            logger.info(f"[webrazzi] {len(mentions)} haber")
            return mentions
        except Exception as e:
            logger.error(f"[webrazzi] collect failed: {e}")
            return []
