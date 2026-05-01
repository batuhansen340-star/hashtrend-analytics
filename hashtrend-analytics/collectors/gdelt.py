"""
GDELT Collector — Türkiye haber akışı (sourcecountry:TU, son 4 saat).

Trend Radar'dan port edildi. TR pazarı için en güçlü genel haber sinyali.
GDELT Project: https://www.gdeltproject.org/
"""

import re
import time
import requests
from collections import Counter
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


_STOP = {
    "ve", "ile", "için", "bir", "bu", "şu", "çok", "ancak",
    "the", "a", "an", "of", "to", "in", "on", "for", "with", "is", "at",
    "etti", "etmiş", "ediyor", "edecek", "oldu", "olmuş", "yaptı", "yapıyor",
    "geldi", "gidiyor", "verdi", "aldı", "kaldı", "ran", "ler", "lar",
}


class GDELTCollector(BaseCollector):
    SOURCE_NAME = "gdelt"
    COLLECT_INTERVAL_MINUTES = 15

    API = "https://api.gdeltproject.org/api/v2/doc/doc"
    MAX_RECORDS = 250
    MIN_PHRASE_OCCURRENCE = 3

    def _phrases(self, title: str) -> list[str]:
        if not title:
            return []
        title_lower = re.sub(r"[^\w\s]", " ", title.lower())
        words = [w for w in title_lower.split() if w not in _STOP and len(w) > 2]
        out = list(words)
        for i in range(len(words) - 1):
            out.append(f"{words[i]} {words[i+1]}")
        return out

    def collect(self) -> list[RawMention]:
        try:
            time.sleep(1.0)
            params = {
                "query": "sourcecountry:TU",
                "mode": "artlist",
                "format": "json",
                "timespan": "4h",
                "maxrecords": self.MAX_RECORDS,
                "sort": "hybridrel",
            }
            resp = requests.get(self.API, params=params, timeout=30)
            if resp.status_code != 200:
                logger.warning(f"[gdelt] status {resp.status_code}")
                return []

            articles = resp.json().get("articles", []) or []
            if not articles:
                return []

            counter: Counter[str] = Counter()
            domain_per_phrase: dict[str, set] = {}
            for art in articles:
                title = art.get("title") or ""
                domain = art.get("domain") or ""
                for ph in self._phrases(title):
                    counter[ph] += 1
                    domain_per_phrase.setdefault(ph, set()).add(domain)

            mentions: list[RawMention] = []
            for phrase, count in counter.most_common(40):
                if count < self.MIN_PHRASE_OCCURRENCE:
                    break
                n_outlets = len(domain_per_phrase.get(phrase, set()))
                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=phrase,
                    mention_count=count,
                    country="TR",
                    raw_data={
                        "n_outlets": n_outlets,
                        "metric": "articles",
                    },
                    collected_at=self.collected_at,
                ))

            return mentions
        except Exception as e:
            logger.error(f"[gdelt] collect failed: {e}")
            return []
