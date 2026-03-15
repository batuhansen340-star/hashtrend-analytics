"""Dev.to Collector — Developer community trending makaleleri."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class DevtoCollector(BaseCollector):
    SOURCE_NAME = "devto"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # Top articles (rising + popular)
        for endpoint in ["top/week", "top/day", "latest"]:
            try:
                url = f"https://dev.to/api/articles?per_page=15&{endpoint.replace('/', '&top=') if 'top' in endpoint else 'state=rising'}"
                if "top" in endpoint:
                    period = endpoint.split("/")[1]
                    url = f"https://dev.to/api/articles?per_page=15&top=1" if period == "day" else f"https://dev.to/api/articles?per_page=15&top=7"
                else:
                    url = f"https://dev.to/api/articles?per_page=15&state=rising"

                resp = session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                articles = resp.json()
                for art in articles[:15]:
                    title = art.get("title", "")
                    reactions = art.get("positive_reactions_count", 0)
                    comments = art.get("comments_count", 0)
                    tags = art.get("tag_list", [])

                    if not title:
                        continue

                    topic = title
                    engagement = reactions + (comments * 3)

                    mentions.append(RawMention(
                        topic=topic,
                        source=self.SOURCE_NAME,
                        mention_count=max(engagement, 10),
                        url=art.get("url", ""),
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {endpoint}: {min(len(articles), 15)} article")

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {endpoint} hata: {e}")

        return mentions
