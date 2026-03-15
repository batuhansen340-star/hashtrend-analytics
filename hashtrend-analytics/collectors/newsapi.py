"""NewsAPI Collector — Top haberlerden trend konulari toplar. Ucretsiz tier: 100 req/gun."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class NewsAPICollector(BaseCollector):
    SOURCE_NAME = "newsapi"
    COLLECT_INTERVAL_MINUTES = 120

    COUNTRIES = ["us", "gb", "de", "tr", "fr", "br", "in", "au", "ca", "it"]
    BASE_URL = "https://newsapi.org/v2/top-headlines"

    def collect(self) -> list[RawMention]:
        import os
        api_key = os.getenv("NEWS_API_KEY", "")

        # NewsAPI key yoksa ucretsiz alternatif kullan
        if not api_key or api_key == "xxxxx":
            return self._collect_free()

        mentions = []
        for country in self.COUNTRIES:
            try:
                resp = requests.get(self.BASE_URL, params={
                    "country": country,
                    "pageSize": 10,
                    "apiKey": api_key,
                }, timeout=10)

                if resp.status_code != 200:
                    continue

                articles = resp.json().get("articles", [])
                for art in articles:
                    title = art.get("title", "")
                    if not title or title == "[Removed]":
                        continue

                    mentions.append(RawMention(
                        topic=title,
                        source=self.SOURCE_NAME,
                        mention_count=1000,
                        url=art.get("url", ""),
                        collected_at=self.collected_at,
                        country=country.upper(),
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {country.upper()}: {len(articles)} haber")

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {country} hata: {e}")
                continue

        return mentions

    def _collect_free(self):
        """NewsAPI key yoksa Google News RSS kullan (ucretsiz, limitsiz)."""
        mentions = []
        countries = {
            "US": "en-US", "GB": "en-GB", "DE": "de-DE", "TR": "tr-TR",
            "FR": "fr-FR", "BR": "pt-BR", "IN": "en-IN", "AU": "en-AU",
            "CA": "en-CA", "IT": "it-IT", "JP": "ja-JP", "KR": "ko-KR",
        }

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        for country, hl in countries.items():
            try:
                url = f"https://news.google.com/rss?hl={hl}&gl={country}&ceid={country}:{hl.split('-')[0]}"
                resp = session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "xml")
                items = soup.find_all("item")

                for item in items[:10]:
                    title = item.find("title")
                    link = item.find("link")
                    if not title:
                        continue

                    mentions.append(RawMention(
                        topic=title.text.strip(),
                        source=self.SOURCE_NAME,
                        mention_count=1000,
                        url=link.text.strip() if link else "",
                        collected_at=self.collected_at,
                        country=country,
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {country}: {min(len(items), 10)} haber")
                import time
                time.sleep(0.5)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {country} hata: {e}")
                continue

        return mentions
