"""Fediverse Collector — Mastodon trending + Bluesky trending. Tamamen ucretsiz API."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class FediverseCollector(BaseCollector):
    SOURCE_NAME = "fediverse"
    COLLECT_INTERVAL_MINUTES = 120

    MASTODON_INSTANCES = [
        "https://mastodon.social",
        "https://mas.to",
        "https://hachyderm.io",
    ]

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. Mastodon Trending Tags
        for instance in self.MASTODON_INSTANCES:
            try:
                resp = session.get(f"{instance}/api/v1/trends/tags", timeout=10)
                if resp.status_code != 200:
                    continue
                tags = resp.json()
                for tag in tags[:10]:
                    name = tag.get("name", "")
                    uses_today = 0
                    history = tag.get("history", [])
                    if history:
                        uses_today = int(history[0].get("uses", 0))
                    if name:
                        mentions.append(RawMention(
                            topic=f"#{name}",
                            source=self.SOURCE_NAME,
                            mention_count=max(uses_today, 10),
                            url=f"{instance}/tags/{name}",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Mastodon {instance.split('//')[1]}: {min(len(tags), 10)} tag")
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] Mastodon {instance} hata: {e}")

        # 2. Mastodon Trending Statuses
        try:
            resp = session.get(f"{self.MASTODON_INSTANCES[0]}/api/v1/trends/statuses", timeout=10)
            if resp.status_code == 200:
                statuses = resp.json()
                for status in statuses[:10]:
                    content = status.get("content", "")
                    from bs4 import BeautifulSoup
                    text = BeautifulSoup(content, "html.parser").get_text()[:120]
                    favs = status.get("favourites_count", 0)
                    reblogs = status.get("reblogs_count", 0)
                    if text and len(text) > 10:
                        mentions.append(RawMention(
                            topic=text,
                            source=self.SOURCE_NAME,
                            mention_count=favs + reblogs,
                            url=status.get("url", ""),
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Mastodon trending: {min(len(statuses), 10)} status")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Mastodon statuses hata: {e}")

        # 3. Bluesky Trending (public API)
        try:
            resp = session.get("https://public.api.bsky.app/xrpc/app.bsky.unspecced.getPopularFeedGenerators",
                             params={"limit": 15}, timeout=10)
            if resp.status_code == 200:
                feeds = resp.json().get("feeds", [])
                for feed in feeds[:15]:
                    name = feed.get("displayName", "")
                    likes = feed.get("likeCount", 0)
                    if name:
                        mentions.append(RawMention(
                            topic=f"Bluesky: {name}",
                            source=self.SOURCE_NAME,
                            mention_count=max(likes, 10),
                            url=f"https://bsky.app",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Bluesky: {min(len(feeds), 15)} feed")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Bluesky hata: {e}")

        return mentions
