"""Stack Overflow Collector — En populer soru ve tag'leri toplar. Ucretsiz API."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class StackOverflowCollector(BaseCollector):
    SOURCE_NAME = "stackoverflow"
    COLLECT_INTERVAL_MINUTES = 120
    BASE_URL = "https://api.stackexchange.com/2.3"

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()

        # 1. Hot questions (en populer sorular)
        try:
            resp = session.get(f"{self.BASE_URL}/questions", params={
                "order": "desc",
                "sort": "hot",
                "site": "stackoverflow",
                "pagesize": 20,
                "filter": "default",
            }, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", [])[:20]:
                    title = item.get("title", "")
                    score = item.get("score", 0)
                    views = item.get("view_count", 0)
                    tags = item.get("tags", [])

                    if not title:
                        continue

                    # HTML entities decode
                    import html
                    title = html.unescape(title)

                    tag_str = ", ".join(tags[:3]) if tags else ""
                    topic = f"{title}"
                    if tag_str:
                        topic = f"[{tag_str}] {title}"

                    mentions.append(RawMention(
                        topic=topic,
                        source=self.SOURCE_NAME,
                        mention_count=max(views, score * 10, 100),
                        url=f"https://stackoverflow.com/q/{item.get('question_id', '')}",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {len(data.get('items', [])[:20])} hot question")

        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] questions hata: {e}")

        # 2. Trending tags (son 24 saat en cok soru acilan tag'ler)
        try:
            resp = session.get(f"{self.BASE_URL}/tags", params={
                "order": "desc",
                "sort": "popular",
                "site": "stackoverflow",
                "pagesize": 15,
                "filter": "default",
            }, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", [])[:15]:
                    tag_name = item.get("name", "")
                    count = item.get("count", 0)

                    if not tag_name:
                        continue

                    mentions.append(RawMention(
                        topic=f"StackOverflow Tag: {tag_name}",
                        source=self.SOURCE_NAME,
                        mention_count=count,
                        url=f"https://stackoverflow.com/questions/tagged/{tag_name}",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {len(data.get('items', [])[:15])} popular tag")

        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] tags hata: {e}")

        return mentions
