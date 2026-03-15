"""IMDb Collector — Populer film ve diziler."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class IMDbCollector(BaseCollector):
    SOURCE_NAME = "imdb"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # IMDb Most Popular Movies
        urls = [
            ("https://www.imdb.com/chart/moviemeter/", "movie"),
            ("https://www.imdb.com/chart/tvmeter/", "tv"),
        ]

        for url, content_type in urls:
            try:
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")

                # Try JSON-LD data first
                import json
                import re
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        items = data.get("itemListElement", [])
                        for item in items[:15]:
                            inner = item.get("item", {})
                            name = inner.get("name", "")
                            url_path = inner.get("url", "")
                            if name:
                                mentions.append(RawMention(
                                    topic=f"{name} ({content_type})",
                                    source=self.SOURCE_NAME,
                                    mention_count=5000 - (item.get("position", 1) * 100),
                                    url=f"https://www.imdb.com{url_path}" if url_path.startswith("/") else url_path,
                                    collected_at=self.collected_at,
                                    country="GLOBAL",
                                ))
                    except json.JSONDecodeError:
                        continue

                # Fallback: title extraction
                if not any(m.source == self.SOURCE_NAME for m in mentions):
                    titles = soup.select("h3.ipc-title__text")
                    for i, t in enumerate(titles[:15]):
                        name = t.text.strip()
                        name = re.sub(r'^\d+\.\s*', '', name)
                        if name and len(name) > 2:
                            mentions.append(RawMention(
                                topic=f"{name} ({content_type})",
                                source=self.SOURCE_NAME,
                                mention_count=5000 - (i * 100),
                                url=url,
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))

                logger.debug(f"[{self.SOURCE_NAME}] {content_type}: {len([m for m in mentions if content_type in m.topic])} item")
                import time
                time.sleep(1)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {content_type} hata: {e}")

        return mentions
