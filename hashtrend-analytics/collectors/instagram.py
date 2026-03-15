"""Instagram Collector — Trending hashtag ve explore icerikleri."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class InstagramCollector(BaseCollector):
    SOURCE_NAME = "instagram"
    COLLECT_INTERVAL_MINUTES = 120

    # Populer hashtag kategorileri
    SEED_TAGS = [
        "trending", "viral", "explore", "fyp",
        "ai", "tech", "crypto", "fitness",
        "fashion", "food", "travel", "business",
        "news", "music", "art", "sports",
    ]

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "X-IG-App-ID": "936619743392459",
        })

        # 1. Instagram hashtag search (public endpoint)
        for tag in self.SEED_TAGS:
            try:
                resp = session.get(
                    f"https://www.instagram.com/api/v1/tags/web_info/?tag_name={tag}",
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("data", {}).get("media_count", 0)
                    name = data.get("data", {}).get("name", tag)

                    if name:
                        mentions.append(RawMention(
                            topic=f"#{name}",
                            source=self.SOURCE_NAME,
                            mention_count=count if count else 5000,
                            url=f"https://www.instagram.com/explore/tags/{name}/",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))

                import time
                time.sleep(1.5)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] tag {tag} hata: {e}")

        # 2. Instagram top search suggestions
        try:
            resp = session.get(
                "https://www.instagram.com/web/search/topsearch/?query=trending",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                hashtags = data.get("hashtags", [])
                for h in hashtags[:10]:
                    ht = h.get("hashtag", {})
                    name = ht.get("name", "")
                    count = ht.get("media_count", 0)
                    if name:
                        mentions.append(RawMention(
                            topic=f"#{name}",
                            source=self.SOURCE_NAME,
                            mention_count=count if count else 1000,
                            url=f"https://www.instagram.com/explore/tags/{name}/",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] topsearch: {len(hashtags[:10])} hashtag")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] topsearch hata: {e}")

        # 3. Fallback: display purposes (public hashtag analytics)
        if len(mentions) < 5:
            try:
                resp = session.get("https://displaypurposes.com/api/tag/trending", timeout=10)
                if resp.status_code == 200:
                    tags = resp.json()
                    if isinstance(tags, list):
                        for t in tags[:20]:
                            name = t.get("tag", "") if isinstance(t, dict) else str(t)
                            if name:
                                mentions.append(RawMention(
                                    topic=f"#{name}",
                                    source=self.SOURCE_NAME,
                                    mention_count=5000,
                                    url=f"https://www.instagram.com/explore/tags/{name}/",
                                    collected_at=self.collected_at,
                                    country="GLOBAL",
                                ))
                    logger.debug(f"[{self.SOURCE_NAME}] displaypurposes: {min(len(tags), 20)} tag")
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] displaypurposes hata: {e}")

        logger.debug(f"[{self.SOURCE_NAME}] toplam: {len(mentions)} mention")
        return mentions
