"""Pinterest Collector — Pinterest trend aramalari ve populer pinler."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class PinterestCollector(BaseCollector):
    SOURCE_NAME = "pinterest"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. Pinterest Trends page
        try:
            resp = session.get("https://trends.pinterest.com/", timeout=15)
            if resp.status_code == 200:
                import re
                trends = re.findall(r'"keyword":"([^"]{2,60})"[^}]*"growth_percentage":(\d+)', resp.text)
                for kw, growth in trends[:20]:
                    mentions.append(RawMention(
                        topic=kw,
                        source=self.SOURCE_NAME,
                        mention_count=int(growth) * 100 if growth else 1000,
                        url=f"https://www.pinterest.com/search/pins/?q={kw.replace(' ', '+')}",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))
                logger.debug(f"[{self.SOURCE_NAME}] trends: {len(trends[:20])} keyword")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] trends hata: {e}")

        # 2. Pinterest autocomplete (trending searches)
        seeds = ["trending", "popular", "aesthetic", "DIY", "recipe", "outfit", "home decor", "workout"]
        for seed in seeds:
            try:
                resp = session.get(
                    f"https://www.pinterest.com/resource/BaseSearchResource/get/?data=%7B%22options%22%3A%7B%22query%22%3A%22{seed}%22%7D%7D",
                    timeout=8
                )
                if resp.status_code == 200:
                    import re
                    suggestions = re.findall(r'"query":"([^"]{3,50})"', resp.text)
                    for s in suggestions[:3]:
                        if not any(m.topic.lower() == s.lower() for m in mentions):
                            mentions.append(RawMention(
                                topic=s,
                                source=self.SOURCE_NAME,
                                mention_count=2000,
                                url=f"https://www.pinterest.com/search/pins/?q={s.replace(' ', '+')}",
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
                import time
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] autocomplete hata: {e}")

        return mentions
