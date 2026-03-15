"""TikTok Collector — Trending hashtag ve videolar."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class TikTokCollector(BaseCollector):
    SOURCE_NAME = "tiktok"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # 1. TikTok Discover page (trending hashtags)
        try:
            resp = session.get("https://www.tiktok.com/discover", timeout=15)
            if resp.status_code == 200:
                import re
                # Extract trending topics from page
                hashtags = re.findall(r'"title":"(#?[^"]{2,60})"[^}]*"subTitle":"(\d+[^"]*)"', resp.text)
                for tag, views in hashtags[:20]:
                    view_num = 0
                    v = views.replace(",", "").upper()
                    if "B" in v:
                        view_num = int(float(v.replace("B", "").strip()) * 1e9)
                    elif "M" in v:
                        view_num = int(float(v.replace("M", "").strip()) * 1e6)
                    elif "K" in v:
                        view_num = int(float(v.replace("K", "").strip()) * 1e3)
                    else:
                        nums = "".join(c for c in v if c.isdigit())
                        view_num = int(nums) if nums else 1000

                    mentions.append(RawMention(
                        topic=tag,
                        source=self.SOURCE_NAME,
                        mention_count=max(view_num, 1000),
                        url=f"https://www.tiktok.com/tag/{tag.lstrip('#')}",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))
                logger.debug(f"[{self.SOURCE_NAME}] discover: {len(hashtags[:20])} hashtag")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] discover hata: {e}")

        # 2. TikTok Creative Center (trending keywords - public)
        try:
            resp = session.get("https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en", timeout=15)
            if resp.status_code == 200:
                import re
                tags = re.findall(r'"hashtag_name":"([^"]{2,50})"[^}]*"publish_cnt":(\d+)', resp.text)
                for tag, cnt in tags[:15]:
                    if not any(m.topic.lstrip("#").lower() == tag.lower() for m in mentions):
                        mentions.append(RawMention(
                            topic=f"#{tag}",
                            source=self.SOURCE_NAME,
                            mention_count=int(cnt) if cnt else 1000,
                            url=f"https://www.tiktok.com/tag/{tag}",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] creative center: {len(tags[:15])} hashtag")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] creative center hata: {e}")

        # 3. Fallback: tokboard.com (public TikTok analytics)
        if not mentions:
            try:
                resp = session.get("https://tokboard.com/trending", timeout=10)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.select("a[href*='tiktok.com']")
                    seen = set()
                    for item in items[:15]:
                        text = item.text.strip()
                        if text and len(text) > 2 and text not in seen:
                            seen.add(text)
                            mentions.append(RawMention(
                                topic=text,
                                source=self.SOURCE_NAME,
                                mention_count=5000,
                                url=item.get("href", ""),
                                collected_at=self.collected_at,
                                country="GLOBAL",
                            ))
                    logger.debug(f"[{self.SOURCE_NAME}] tokboard: {len(seen)} trend")
            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] tokboard hata: {e}")

        return mentions
