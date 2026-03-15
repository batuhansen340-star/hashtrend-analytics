"""Yahoo Finance Collector — Trending stocks, crypto ve finans haberleri."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class YahooFinanceCollector(BaseCollector):
    SOURCE_NAME = "yahoo_finance"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. Yahoo Finance Trending Tickers
        try:
            resp = session.get("https://query1.finance.yahoo.com/v1/finance/trending/US?count=20", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                quotes = data.get("finance", {}).get("result", [])
                if quotes:
                    for q in quotes[0].get("quotes", [])[:20]:
                        symbol = q.get("symbol", "")
                        if symbol:
                            mentions.append(RawMention(
                                topic=f"${symbol}",
                                source=self.SOURCE_NAME,
                                mention_count=5000,
                                url=f"https://finance.yahoo.com/quote/{symbol}",
                                collected_at=self.collected_at,
                                country="US",
                            ))
                    logger.debug(f"[{self.SOURCE_NAME}] trending tickers: {len(quotes[0].get('quotes', [])[:20])}")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] trending tickers hata: {e}")

        # 2. Yahoo Finance Most Active
        try:
            resp = session.get("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=10", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("finance", {}).get("result", [])
                if results:
                    quotes = results[0].get("quotes", [])
                    for q in quotes[:10]:
                        symbol = q.get("symbol", "")
                        name = q.get("shortName", symbol)
                        volume = q.get("regularMarketVolume", 0)
                        if symbol:
                            mentions.append(RawMention(
                                topic=f"{name} (${symbol})",
                                source=self.SOURCE_NAME,
                                mention_count=max(volume, 1000),
                                url=f"https://finance.yahoo.com/quote/{symbol}",
                                collected_at=self.collected_at,
                                country="US",
                            ))
                    logger.debug(f"[{self.SOURCE_NAME}] most active: {len(quotes[:10])}")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] most active hata: {e}")

        # 3. Crypto trending
        try:
            resp = session.get("https://query1.finance.yahoo.com/v1/finance/trending/US?count=10&queryTicker=true&useQuotes=true&lang=en-US&region=US", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Also get crypto
                resp2 = session.get("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=all_cryptocurrencies_us&count=10", timeout=10)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    results = data2.get("finance", {}).get("result", [])
                    if results:
                        for q in results[0].get("quotes", [])[:10]:
                            symbol = q.get("symbol", "")
                            name = q.get("shortName", symbol)
                            if symbol and not any(symbol in m.topic for m in mentions):
                                mentions.append(RawMention(
                                    topic=f"Crypto: {name} ({symbol})",
                                    source=self.SOURCE_NAME,
                                    mention_count=3000,
                                    url=f"https://finance.yahoo.com/quote/{symbol}",
                                    collected_at=self.collected_at,
                                    country="GLOBAL",
                                ))
                        logger.debug(f"[{self.SOURCE_NAME}] crypto: {len(results[0].get('quotes', [])[:10])}")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] crypto hata: {e}")

        return mentions
