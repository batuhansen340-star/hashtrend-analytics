"""LinkedIn Collector — Trending haberler ve populer konular."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class LinkedInCollector(BaseCollector):
    SOURCE_NAME = "linkedin"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })

        # 1. LinkedIn News (public RSS)
        try:
            resp = session.get("https://www.linkedin.com/pulse/trending", timeout=15)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.select("article, h3, .news-module__headline")
                seen = set()
                for art in articles[:15]:
                    title = art.text.strip()
                    if title and len(title) > 10 and title not in seen:
                        seen.add(title)
                        mentions.append(RawMention(
                            topic=title,
                            source=self.SOURCE_NAME,
                            mention_count=2000,
                            url="https://www.linkedin.com/pulse/trending",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] pulse: {len(seen)} article")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] pulse hata: {e}")

        # 2. LinkedIn trending topics via Google
        trending_keywords = [
            "site:linkedin.com/pulse trending",
            "linkedin trending topics today",
        ]
        for kw in trending_keywords:
            try:
                resp = session.get(
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}&num=10&tbs=qdr:d",
                    timeout=10
                )
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    results = soup.select("h3")
                    for r in results[:5]:
                        title = r.text.strip()
                        if title and len(title) > 10:
                            mentions.append(RawMention(
                                topic=title,
                                source=self.SOURCE_NAME,
                                mention_count=1500,
                                url="https://www.linkedin.com",
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
                import time
                time.sleep(1)
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] google hata: {e}")

        return mentions
