"""App Trends Collector — App Store ve Google Play trending uygulamalar."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class AppTrendsCollector(BaseCollector):
    SOURCE_NAME = "apptrends"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. Google Play Store Trending (RSS/scrape)
        try:
            resp = session.get("https://play.google.com/store/apps/trending", timeout=15)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                apps = soup.select("div.Vpfmgd, span.DdYX5, c-wiz a[href*='/store/apps/details']")
                titles = set()
                for app in apps[:20]:
                    title = app.text.strip()
                    if title and len(title) > 2 and title not in titles:
                        titles.add(title)
                        mentions.append(RawMention(
                            topic=f"App: {title}",
                            source=self.SOURCE_NAME,
                            mention_count=2000,
                            url="https://play.google.com/store/apps",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Play Store: {len(titles)} app")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Play Store hata: {e}")

        # 2. AlternativeTo trending (what people are searching for)
        try:
            resp = session.get("https://alternativeto.net/trending/", timeout=15)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("a.app-card-link, h2.app-card-name, [data-testid='app-name']")
                if not items:
                    items = soup.select("a[href*='/software/'] h2, a[href*='/software/'] span.name")
                seen = set()
                for item in items[:15]:
                    name = item.text.strip()
                    if name and len(name) > 2 and name not in seen:
                        seen.add(name)
                        mentions.append(RawMention(
                            topic=f"Software: {name}",
                            source=self.SOURCE_NAME,
                            mention_count=1000,
                            url=f"https://alternativeto.net/software/{name.lower().replace(' ', '-')}/",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] AlternativeTo: {len(seen)} software")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] AlternativeTo hata: {e}")

        return mentions
