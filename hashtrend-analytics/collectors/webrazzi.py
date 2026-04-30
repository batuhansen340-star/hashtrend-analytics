"""
Webrazzi RSS Collector — TR startup ekosistemi haberleri.

Trend Radar'dan port edildi. TR'nin en yoğun startup haber akışı.
"""

import re
import feedparser
from collections import Counter
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


_STOP = {
    "ve", "ile", "için", "bir", "bu", "haber", "haberi", "açıkladı",
    "açıklama", "ilk", "son", "milyon", "dolar", "milyar", "şirket",
    "etti", "ediyor", "oldu", "olmuş", "yaptı", "geliyor", "olduğu",
}


class WebrazziCollector(BaseCollector):
    SOURCE_NAME = "webrazzi"
    COLLECT_INTERVAL_MINUTES = 60

    URL = "https://webrazzi.com/feed/"
    MAX_ENTRIES = 40

    def _phrases(self, title: str, summary: str) -> list[str]:
        text = re.sub(r"[^\w\s]", " ", f"{title} {summary}".lower())
        words = [w for w in text.split() if w not in _STOP and len(w) > 2]
        out = list(words)
        for i in range(len(words) - 1):
            out.append(f"{words[i]} {words[i+1]}")
        return out

    def collect(self) -> list[RawMention]:
        try:
            feed = feedparser.parse(self.URL)
            entries = feed.entries[: self.MAX_ENTRIES] if feed and feed.entries else []
            if not entries:
                logger.warning("[webrazzi] RSS boş")
                return []

            counter: Counter[str] = Counter()
            urls_per_phrase: dict[str, set] = {}
            for e in entries:
                title = e.get("title") or ""
                summary = e.get("summary", "") or e.get("description", "") or ""
                link = e.get("link") or ""
                for ph in self._phrases(title, summary):
                    counter[ph] += 1
                    urls_per_phrase.setdefault(ph, set()).add(link)

            mentions: list[RawMention] = []
            for phrase, count in counter.most_common(35):
                if count < 1:
                    break
                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=phrase,
                    mention_count=max(count, 1),
                    country="TR",
                    raw_data={
                        "n_articles": len(urls_per_phrase.get(phrase, set())),
                        "metric": "articles",
                    },
                    collected_at=self.collected_at,
                ))

            return mentions
        except Exception as e:
            logger.error(f"[webrazzi] collect failed: {e}")
            return []
