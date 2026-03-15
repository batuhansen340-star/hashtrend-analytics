"""Search Trends Collector — Bing Trending + DuckDuckGo arama trendleri."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class SearchTrendsCollector(BaseCollector):
    SOURCE_NAME = "search_trends"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. Bing Trending
        markets = ["en-US", "en-GB", "de-DE", "tr-TR", "fr-FR", "ja-JP", "ko-KR", "es-ES", "pt-BR", "it-IT"]
        country_map = {"en-US": "US", "en-GB": "GB", "de-DE": "DE", "tr-TR": "TR", "fr-FR": "FR",
                      "ja-JP": "JP", "ko-KR": "KR", "es-ES": "ES", "pt-BR": "BR", "it-IT": "IT"}

        for market in markets:
            try:
                resp = session.get(f"https://api.bing.com/osjson.aspx?query=&market={market}&count=10", timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) >= 2:
                        suggestions = data[1] if isinstance(data[1], list) else []
                        for i, term in enumerate(suggestions[:10]):
                            if term and len(term) > 2:
                                mentions.append(RawMention(
                                    topic=term,
                                    source=self.SOURCE_NAME,
                                    mention_count=1000 - (i * 80),
                                    url=f"https://www.bing.com/search?q={term.replace(' ', '+')}",
                                    collected_at=self.collected_at,
                                    country=country_map.get(market, "GLOBAL"),
                                ))
                    logger.debug(f"[{self.SOURCE_NAME}] Bing {market}: {len(suggestions[:10])} trend")
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] Bing {market} hata: {e}")

            import time
            time.sleep(0.3)

        # 2. DuckDuckGo Autocomplete (trending searches)
        try:
            seeds = ["how to", "what is", "best", "why", "new"]
            for seed in seeds:
                resp = session.get(f"https://duckduckgo.com/ac/?q={seed}&type=list", timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    suggestions = data[1] if isinstance(data, list) and len(data) >= 2 else []
                    for i, term in enumerate(suggestions[:5]):
                        if term and len(term) > 5:
                            mentions.append(RawMention(
                                topic=term,
                                source=self.SOURCE_NAME,
                                mention_count=500,
                                url=f"https://duckduckgo.com/?q={term.replace(' ', '+')}",
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
                time.sleep(0.3)
            logger.debug(f"[{self.SOURCE_NAME}] DuckDuckGo: {len(seeds)*5} suggestion")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] DuckDuckGo hata: {e}")

        return mentions
