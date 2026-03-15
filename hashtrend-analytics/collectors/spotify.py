"""Spotify Collector — Podcast ve muzik chart'lari."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class SpotifyCollector(BaseCollector):
    SOURCE_NAME = "spotify"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # Spotify Charts (podcastindex.org - free API)
        try:
            resp = session.get("https://api.podcastindex.org/api/v1/podcasts/trending?max=20&lang=en",
                             headers={"X-Auth-Key": "public"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                feeds = data.get("feeds", [])
                for feed in feeds[:15]:
                    title = feed.get("title", "")
                    trend_score = feed.get("trendScore", 0)
                    if title:
                        mentions.append(RawMention(
                            topic=f"Podcast: {title}",
                            source=self.SOURCE_NAME,
                            mention_count=max(int(trend_score), 100),
                            url=feed.get("link", ""),
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] podcasts: {min(len(feeds), 15)} trending")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] podcast hata: {e}")

        # Spotify Charts page scrape (top songs)
        try:
            resp = session.get("https://spotifycharts.com/regional/global/daily/latest", timeout=10)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                entries = soup.select("td.chart-table-track")
                for i, entry in enumerate(entries[:15]):
                    strong = entry.select_one("strong")
                    span = entry.select_one("span")
                    if strong:
                        song = strong.text.strip()
                        artist = span.text.strip().lstrip("by ") if span else ""
                        topic = f"{song} - {artist}" if artist else song
                        mentions.append(RawMention(
                            topic=topic,
                            source=self.SOURCE_NAME,
                            mention_count=10000 - (i * 500),
                            url="https://open.spotify.com",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] songs: {min(len(entries), 15)}")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] charts hata: {e}")

        return mentions
