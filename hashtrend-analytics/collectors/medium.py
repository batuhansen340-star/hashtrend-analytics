"""Medium Collector — Medium trending makaleleri. Tag bazli RSS."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class MediumCollector(BaseCollector):
    SOURCE_NAME = "medium"
    COLLECT_INTERVAL_MINUTES = 120

    TAGS = [
        "artificial-intelligence", "machine-learning", "programming",
        "technology", "startup", "data-science", "cryptocurrency",
        "business", "science", "psychology", "productivity",
        "self-improvement", "design", "education", "finance",
    ]

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/rss+xml, text/xml",
        })

        for tag in self.TAGS:
            try:
                url = f"https://medium.com/feed/tag/{tag}"
                resp = session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "xml")
                items = soup.find_all("item")

                for item in items[:5]:
                    title_el = item.find("title")
                    link_el = item.find("link")

                    if not title_el:
                        continue

                    title = title_el.text.strip()
                    if not title or len(title) < 5:
                        continue

                    mentions.append(RawMention(
                        topic=title,
                        source=self.SOURCE_NAME,
                        mention_count=500,
                        url=link_el.text.strip() if link_el else "",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {tag}: {min(len(items), 5)} article")
                import time
                time.sleep(0.5)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {tag} hata: {e}")

        return mentions
