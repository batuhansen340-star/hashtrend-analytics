"""
trends24.in/turkey Collector — Twitter TR trending hashtag scraping.

X resmi API'sinin pay-per-use modeline alternatif olarak unofficial aggregator.
Trend Radar'dan port edildi.
"""

import time
import requests
from bs4 import BeautifulSoup
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


class Trends24Collector(BaseCollector):
    SOURCE_NAME = "trends24"
    COLLECT_INTERVAL_MINUTES = 30

    URL = "https://trends24.in/turkey/"
    HEADERS = {
        "User-Agent": (
            "HashTrend/2.0 (TR trend monitoring; +hashtrend.app)"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9",
    }
    MAX_ITEMS = 25

    def collect(self) -> list[RawMention]:
        try:
            time.sleep(2.0)
            resp = requests.get(self.URL, headers=self.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"[trends24] status {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.content, "html.parser")
            first_card = (
                soup.select_one("div.trend-card ol")
                or soup.select_one(".trend-card__list")
                or soup.select_one(".list-container ol")
            )
            if not first_card:
                logger.warning("[trends24] selector eski olabilir")
                return []

            items = first_card.select("li a")[: self.MAX_ITEMS]
            if not items:
                return []

            mentions: list[RawMention] = []
            for rank, a in enumerate(items, start=1):
                text = a.get_text(strip=True)
                if not text:
                    continue
                # rank-based mention_count: top trend → 25, bottom → 1
                mc = max(self.MAX_ITEMS - rank + 1, 1)
                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=text,
                    mention_count=mc,
                    country="TR",
                    raw_data={
                        "rank": rank,
                        "metric": "rank-derived",
                        "platform": "twitter_x",
                    },
                    collected_at=self.collected_at,
                ))

            return mentions
        except Exception as e:
            logger.error(f"[trends24] collect failed: {e}")
            return []
