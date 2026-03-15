"""Regional Search Collector — Naver (Kore), Yandex (Rusya) trending aramalari."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class RegionalSearchCollector(BaseCollector):
    SOURCE_NAME = "regional_search"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 1. Naver Realtime Search (Korea)
        try:
            resp = session.get("https://www.naver.com/", timeout=10)
            if resp.status_code == 200:
                import re
                # Naver real-time trending keywords
                keywords = re.findall(r'"keyword":"([^"]{2,40})"', resp.text)
                seen = set()
                for kw in keywords[:20]:
                    if kw not in seen and len(kw) > 1:
                        seen.add(kw)
                        mentions.append(RawMention(
                            topic=kw,
                            source=self.SOURCE_NAME,
                            mention_count=5000,
                            url=f"https://search.naver.com/search.naver?query={kw}",
                            collected_at=self.collected_at,
                            country="KR",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Naver: {len(seen)} keyword")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Naver hata: {e}")

        # 2. Naver DataLab (trending searches)
        try:
            resp = session.get("https://datalab.naver.com/keyword/realtimeList.naver", timeout=10)
            if resp.status_code == 200:
                import re
                keywords = re.findall(r'"keyword[Nn]ame":"([^"]{2,40})"', resp.text)
                for kw in keywords[:10]:
                    if not any(m.topic == kw for m in mentions):
                        mentions.append(RawMention(
                            topic=kw,
                            source=self.SOURCE_NAME,
                            mention_count=3000,
                            url=f"https://search.naver.com/search.naver?query={kw}",
                            collected_at=self.collected_at,
                            country="KR",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Naver DataLab: {len(keywords[:10])} keyword")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Naver DataLab hata: {e}")

        # 3. Yandex Trending (Russia)
        try:
            resp = session.get("https://yandex.com/news/", timeout=10,
                             headers={"Accept-Language": "ru-RU,ru;q=0.9"})
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                stories = soup.select("a.mg-card__link, h2.mg-card__title")
                seen = set()
                for s in stories[:15]:
                    title = s.text.strip()
                    if title and len(title) > 5 and title not in seen:
                        seen.add(title)
                        mentions.append(RawMention(
                            topic=title,
                            source=self.SOURCE_NAME,
                            mention_count=2000,
                            url="https://yandex.com/news/",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
                logger.debug(f"[{self.SOURCE_NAME}] Yandex: {len(seen)} story")
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Yandex hata: {e}")

        # 4. Yandex Wordstat trending (search volume)
        try:
            resp = session.get("https://wordstat.yandex.com/", timeout=10)
            if resp.status_code == 200:
                import re
                keywords = re.findall(r'"text":"([^"]{3,50})"', resp.text)
                for kw in keywords[:10]:
                    if not any(m.topic == kw for m in mentions):
                        mentions.append(RawMention(
                            topic=kw,
                            source=self.SOURCE_NAME,
                            mention_count=1500,
                            url=f"https://yandex.com/search/?text={kw}",
                            collected_at=self.collected_at,
                            country="GLOBAL",
                        ))
        except Exception as e:
            logger.debug(f"[{self.SOURCE_NAME}] Yandex wordstat hata: {e}")

        return mentions
