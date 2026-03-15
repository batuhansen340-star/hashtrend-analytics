"""YouTube Trending Collector — YouTube'un trending videolarını toplar."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class YouTubeCollector(BaseCollector):
    SOURCE_NAME = "youtube"
    COLLECT_INTERVAL_MINUTES = 120

    COUNTRIES = {
        "US": "US", "GB": "GB", "DE": "DE", "TR": "TR", "FR": "FR",
        "BR": "BR", "IN": "IN", "JP": "JP", "KR": "KR", "CA": "CA",
        "AU": "AU", "ES": "ES", "IT": "IT", "MX": "MX", "ID": "ID",
    }

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

        for country_code, geo in self.COUNTRIES.items():
            try:
                url = f"https://www.youtube.com/feed/trending?gl={geo}&hl=en"
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue

                text = resp.text
                import re
                titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]{5,120})"\}', text)
                view_counts = re.findall(r'"viewCountText":\{"simpleText":"([\d,\.]+\s*\w*)\s*views?"', text)

                seen = set()
                for i, title in enumerate(titles[:10]):
                    if title in seen:
                        continue
                    seen.add(title)
                    views = 0
                    if i < len(view_counts):
                        v_str = view_counts[i].replace(",", "").replace(".", "")
                        v_str = "".join(c for c in v_str if c.isdigit())
                        views = int(v_str) if v_str else 0

                    mentions.append(RawMention(
                        topic=title,
                        source=self.SOURCE_NAME,
                        mention_count=max(views, 1000),
                        url=f"https://www.youtube.com/results?search_query={title.replace(' ', '+')}",
                        collected_at=self.collected_at,
                        country=country_code,
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {country_code}: {len(seen)} video")
                import time
                time.sleep(1)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {country_code} hata: {e}")
                continue

        return mentions
