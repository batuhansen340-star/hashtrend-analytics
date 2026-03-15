"""Product Hunt Collector — Gunun en populer urunlerini toplar."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class ProductHuntCollector(BaseCollector):
    SOURCE_NAME = "producthunt"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        })

        try:
            resp = session.get("https://www.producthunt.com/", timeout=15)
            if resp.status_code != 200:
                logger.debug(f"[{self.SOURCE_NAME}] HTTP {resp.status_code}")
                return mentions

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Product Hunt ana sayfasindan urun isimlerini cek
            # data-test attribute veya meta tag'lardan
            import re
            import json

            # Script tag'larinda JSON veri arama
            scripts = soup.find_all("script")
            for script in scripts:
                text = script.string or ""
                # Product isimlerini bul
                names = re.findall(r'"name":"([^"]{3,80})"[^}]*"tagline":"([^"]{3,120})"', text)
                votes = re.findall(r'"votesCount":(\d+)', text)

                for i, (name, tagline) in enumerate(names[:15]):
                    vote_count = int(votes[i]) if i < len(votes) else 100
                    topic = f"{name}: {tagline}"

                    mentions.append(RawMention(
                        topic=topic,
                        source=self.SOURCE_NAME,
                        mention_count=max(vote_count, 50),
                        url=f"https://www.producthunt.com/search?q={name.replace(' ', '+')}",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                if names:
                    break

            # Fallback: basit link extraction
            if not mentions:
                links = soup.select("a[href*='/posts/']")
                seen = set()
                for link in links[:15]:
                    title = link.text.strip()
                    if len(title) < 3 or title in seen:
                        continue
                    seen.add(title)
                    mentions.append(RawMention(
                        topic=title,
                        source=self.SOURCE_NAME,
                        mention_count=100,
                        url="https://www.producthunt.com" + link.get("href", ""),
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

            logger.debug(f"[{self.SOURCE_NAME}] {len(mentions)} urun")

        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] hata: {e}")

        return mentions
