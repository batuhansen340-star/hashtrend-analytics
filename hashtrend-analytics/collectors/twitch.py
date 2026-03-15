"""Twitch Collector — En populer canli yayinlar ve oyunlar. Scrape."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class TwitchCollector(BaseCollector):
    SOURCE_NAME = "twitch"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        })

        try:
            # SullyGnome - Twitch analytics (public)
            resp = session.get("https://sullygnome.com/api/tables/channeltables/getchannels/30/0/0/3/desc/0/20", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data:
                    for ch in data["data"][:15]:
                        name = ch.get("displayname", "")
                        viewers = ch.get("viewerminutes", 0)
                        if name:
                            mentions.append(RawMention(
                                topic=f"Twitch: {name}",
                                source=self.SOURCE_NAME,
                                mention_count=max(viewers, 1000),
                                url=f"https://www.twitch.tv/{name.lower()}",
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
        except Exception:
            pass

        # Fallback: Twitch tracker top games
        if not mentions:
            try:
                resp = session.get("https://twitchtracker.com/statistics/games", timeout=10)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    rows = soup.select("table tbody tr")
                    for row in rows[:15]:
                        cells = row.select("td")
                        if len(cells) >= 2:
                            name = cells[0].text.strip()
                            if name and len(name) > 2:
                                mentions.append(RawMention(
                                    topic=f"Twitch Game: {name}",
                                    source=self.SOURCE_NAME,
                                    mention_count=1000,
                                    url=f"https://www.twitch.tv/directory/game/{name.replace(' ', '%20')}",
                                    collected_at=self.collected_at,
                                    country="GLOBAL",
                                ))
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] fallback hata: {e}")

        logger.debug(f"[{self.SOURCE_NAME}] {len(mentions)} stream/game")
        return mentions
