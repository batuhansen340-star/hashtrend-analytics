"""GitHub Trending Collector — GitHub'un trending repolarini toplar."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class GitHubCollector(BaseCollector):
    SOURCE_NAME = "github"
    COLLECT_INTERVAL_MINUTES = 120

    LANGUAGES = [None, "python", "javascript", "typescript", "rust", "go"]

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        })

        for lang in self.LANGUAGES:
            try:
                url = "https://github.com/trending"
                if lang:
                    url += f"/{lang}"
                url += "?since=daily"

                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.select("article.Box-row")

                for art in articles[:10]:
                    h2 = art.select_one("h2")
                    if not h2:
                        continue
                    a_tag = h2.select_one("a")
                    if not a_tag:
                        continue

                    repo_name = a_tag.text.strip().replace("\n", "").replace(" ", "")
                    repo_name = " / ".join(p.strip() for p in repo_name.split("/") if p.strip())

                    desc_p = art.select_one("p")
                    description = desc_p.text.strip() if desc_p else ""

                    stars_el = art.select_one("span.d-inline-block.float-sm-right")
                    stars = 0
                    if stars_el:
                        s_text = stars_el.text.strip().replace(",", "").replace(".", "")
                        s_text = "".join(c for c in s_text if c.isdigit())
                        stars = int(s_text) if s_text else 0

                    topic = repo_name
                    if description:
                        topic = f"{repo_name}: {description[:80]}"

                    mentions.append(RawMention(
                        topic=topic,
                        source=self.SOURCE_NAME,
                        mention_count=max(stars, 100),
                        url=f"https://github.com/{a_tag.get('href', '').strip('/')}",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {lang or 'all'}: {min(len(articles), 10)} repo")
                import time
                time.sleep(1)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {lang} hata: {e}")
                continue

        return mentions
