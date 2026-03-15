"""Arxiv Collector — En son bilimsel makaleler. Ucretsiz RSS/API."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class ArxivCollector(BaseCollector):
    SOURCE_NAME = "arxiv"
    COLLECT_INTERVAL_MINUTES = 120

    CATEGORIES = [
        "cs.AI",      # Artificial Intelligence
        "cs.LG",      # Machine Learning
        "cs.CL",      # Computation and Language (NLP)
        "cs.CV",      # Computer Vision
        "cs.CR",      # Cryptography and Security
        "cs.SE",      # Software Engineering
        "stat.ML",    # Statistics - Machine Learning
        "econ.GN",    # Economics - General
        "q-fin.ST",   # Quantitative Finance
    ]

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()

        for cat in self.CATEGORIES:
            try:
                url = f"http://export.arxiv.org/api/query?search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results=5"
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "xml")
                entries = soup.find_all("entry")

                for entry in entries[:5]:
                    title_el = entry.find("title")
                    summary_el = entry.find("summary")
                    link_el = entry.find("id")

                    if not title_el:
                        continue

                    title = title_el.text.strip().replace("\n", " ")
                    summary = summary_el.text.strip()[:100] if summary_el else ""

                    mentions.append(RawMention(
                        topic=title,
                        source=self.SOURCE_NAME,
                        mention_count=100,
                        url=link_el.text.strip() if link_el else "",
                        collected_at=self.collected_at,
                        country="GLOBAL",
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {cat}: {min(len(entries), 5)} paper")
                import time
                time.sleep(0.5)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {cat} hata: {e}")

        return mentions
