"""
Ekşi Sözlük Collector — Türk gündem akışı.

`/basliklar/gundem` sayfasından top başlıklar. TR pazarı derinliği için
Trend Radar'dan port edildi.

Etik: dürüst User-Agent, 2sn rate limit.
"""

import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


class EksiSozlukCollector(BaseCollector):
    SOURCE_NAME = "eksisozluk"
    COLLECT_INTERVAL_MINUTES = 15

    URL = "https://eksisozluk.com/basliklar/gundem"
    HEADERS = {
        "User-Agent": (
            "HashTrend/2.0 (TR trend monitoring; +hashtrend.app)"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9",
    }
    MAX_TOPICS = 50

    def collect(self) -> list[RawMention]:
        try:
            time.sleep(2.0)  # politeness
            resp = requests.get(self.URL, headers=self.HEADERS, timeout=15)
            if resp.status_code == 403:
                logger.warning("[eksisozluk] 403 — Cloudflare/bot blok")
                return []
            if resp.status_code != 200:
                logger.warning(f"[eksisozluk] status {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.content, "html.parser")
            items = (
                soup.select("ul.topic-list li a")
                or soup.select(".topic-list li a")
                or soup.select("ol.topic-list li a")
            )
            items = items[: self.MAX_TOPICS]
            if not items:
                logger.warning("[eksisozluk] selector 0 sonuç verdi")
                return []

            mentions: list[RawMention] = []
            for item in items:
                small = item.select_one("small")
                try:
                    cnt = int((small.text or "0").strip()) if small else 1
                except ValueError:
                    cnt = 1

                title_full = item.get_text(strip=True)
                if small:
                    title_text = title_full.replace(
                        small.get_text(strip=True), ""
                    ).strip()
                else:
                    title_text = title_full

                if not title_text or len(title_text) < 3:
                    continue

                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=title_text,
                    mention_count=max(cnt, 1),
                    country="TR",
                    url=f"https://eksisozluk.com{item.get('href', '')}",
                    raw_data={"entry_count": cnt, "metric": "entries"},
                    collected_at=self.collected_at,
                ))

            return mentions
        except Exception as e:
            logger.error(f"[eksisozluk] collect failed: {e}")
            return []
