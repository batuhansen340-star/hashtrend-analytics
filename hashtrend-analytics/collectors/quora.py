"""Quora + Telegram Collector — Quora trending sorular ve Telegram public kanal trendleri."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class QuoraCollector(BaseCollector):
    SOURCE_NAME = "quora"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # Quora Trending/Popular topics
        try:
            resp = session.get("https://www.quora.com/", timeout=15)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract question titles
                import re
                questions = re.findall(r'"text":"([^"]{15,200})\?"', resp.text)
                seen = set()
                for q in questions[:20]:
                    q_clean = q.strip() + "?"
                    if q_clean not in seen and len(q_clean) > 15:
                        seen.add(q_clean)
                        mentions.append(RawMention(
                            topic=q_clean,
                            source=self.SOURCE_NAME,
                            mention_count=1000,
                            url=f"https://www.quora.com/search?q={q_clean[:50].replace(' ', '+')}",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))

                logger.debug(f"[{self.SOURCE_NAME}] {len(seen)} question")

        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] hata: {e}")

        # Quora Spaces/Topics trending
        topics = ["technology", "science", "business", "politics", "health", "education"]
        for topic in topics:
            try:
                resp = session.get(f"https://www.quora.com/topic/{topic.title()}", timeout=10)
                if resp.status_code == 200:
                    import re
                    questions = re.findall(r'"text":"([^"]{15,150})\?"', resp.text)
                    for q in questions[:3]:
                        q_clean = q.strip() + "?"
                        if not any(m.topic == q_clean for m in mentions):
                            mentions.append(RawMention(
                                topic=q_clean,
                                source=self.SOURCE_NAME,
                                mention_count=800,
                                url=f"https://www.quora.com/topic/{topic.title()}",
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
                import time
                time.sleep(1)
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] topic {topic} hata: {e}")

        return mentions
