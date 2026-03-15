"""Commerce Collector — Amazon bestseller + Goodreads trending kitaplar."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class CommerceCollector(BaseCollector):
    SOURCE_NAME = "commerce"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # 1. Amazon Movers & Shakers / Bestsellers
        amazon_cats = [
            ("https://www.amazon.com/gp/bestsellers/books/", "books"),
            ("https://www.amazon.com/gp/bestsellers/electronics/", "electronics"),
            ("https://www.amazon.com/gp/bestsellers/software/", "software"),
        ]

        for url, cat in amazon_cats:
            try:
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")

                items = soup.select("div.p13n-sc-uncoverable-faceout span.a-size-medium")
                if not items:
                    items = soup.select("span.zg-text-center-align span.p13n-sc-truncated")
                if not items:
                    items = soup.select("[class*='truncat'] span, .a-truncate-cut")

                for i, item in enumerate(items[:10]):
                    title = item.text.strip()
                    if title and len(title) > 3:
                        mentions.append(RawMention(
                            topic=f"Amazon {cat}: {title}",
                            source=self.SOURCE_NAME,
                            mention_count=5000 - (i * 300),
                            url=url,
                            collected_at=self.collected_at,
                            country="US",
                        ))

                logger.debug(f"[{self.SOURCE_NAME}] Amazon {cat}: {min(len(items), 10)} item")
                import time
                time.sleep(1)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] Amazon {cat} hata: {e}")

        # 2. Goodreads Most Read This Week
        try:
            resp = session.get("https://www.goodreads.com/book/most_read", timeout=15)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                books = soup.select("a.bookTitle")
                for i, book in enumerate(books[:15]):
                    title = book.text.strip()
                    href = book.get("href", "")
                    if title and len(title) > 2:
                        mentions.append(RawMention(
                            topic=f"Book: {title}",
                            source=self.SOURCE_NAME,
                            mention_count=3000 - (i * 150),
                            url=f"https://www.goodreads.com{href}" if href.startswith("/") else href,
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Goodreads: {min(len(books), 15)} book")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Goodreads hata: {e}")

        return mentions
