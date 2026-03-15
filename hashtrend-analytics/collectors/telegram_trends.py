"""Telegram Collector — Public kanal ve grup trendleri. Tgstat.com uzerinden."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class TelegramCollector(BaseCollector):
    SOURCE_NAME = "telegram"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. TGStat top channels (public analytics)
        categories = ["technology", "news", "cryptocurrency", "education", "business"]
        for cat in categories:
            try:
                resp = session.get(f"https://tgstat.com/en/ratings/channels/{cat}", timeout=10)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    channels = soup.select("a.channel-card__title, .channel-card__name")
                    for ch in channels[:5]:
                        name = ch.text.strip()
                        if name and len(name) > 2:
                            mentions.append(RawMention(
                                topic=f"Telegram: {name} ({cat})",
                                source=self.SOURCE_NAME,
                                mention_count=2000,
                                url=f"https://t.me/{name.lower().replace(' ', '')}",
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
                    logger.debug(f"[{self.SOURCE_NAME}] tgstat {cat}: {min(len(channels), 5)} channel")
                import time
                time.sleep(1)
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] tgstat {cat} hata: {e}")

        # 2. Telemetr.io trending posts
        try:
            resp = session.get("https://telemetr.io/en/trending", timeout=10)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                posts = soup.select("div.post-text, a.channel-name")
                seen = set()
                for p in posts[:15]:
                    text = p.text.strip()[:120]
                    if text and len(text) > 10 and text not in seen:
                        seen.add(text)
                        mentions.append(RawMention(
                            topic=text,
                            source=self.SOURCE_NAME,
                            mention_count=1500,
                            url="https://telemetr.io/en/trending",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] telemetr: {len(seen)} post")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] telemetr hata: {e}")

        return mentions
