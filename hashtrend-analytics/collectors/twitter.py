"""
Twitter / X Collector — Apify üzerinden apidojo/twitter-scraper-lite actor'u.

⚠ MALİYET KONTROLÜ: Apify Pay-per-event modu çok pahalı. Test sırasında 2 run
$2.40/$5 free tier yedi. Bu collector aşırı kısıtlı çalışır:
  • Sadece 3 TR sinyali query (en yoğun TR audience)
  • 10 tweet/query maksimum
  • Günde 1 kez (1440 dk interval)
  • Toplam: ~30 tweet/gün ≈ 900/ay → free tier'da $1-2/ay

X verisinin hacmi düşük ama TR Twitter trend sinyali korunmuş olur.
İleride flat-rate actor (microworlds) bulunursa volume artırılabilir.

Env: APIFY_TOKEN (GHA secret olarak Railway değil GitHub Actions'a konulur).
"""

import os
import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


# Apify actor: apidojo/twitter-scraper-lite
APIFY_ACTOR = "apidojo~twitter-scraper-lite"
APIFY_BASE = "https://api.apify.com/v2"

# Probe keyword'leri — sadece en güçlü TR sinyalleri (maliyet için)
PROBE_QUERIES = [
    "türkiye", "gündem", "ekonomi",
]

# country='TR' işaretlenecek query'ler — hepsi TR
TR_QUERIES = frozenset(PROBE_QUERIES)

# Run başına query başına kaç tweet (10 × 3 = 30 tweet/run max)
MAX_PER_QUERY = 10
# Engagement minimum
MIN_ENGAGEMENT = 5


class TwitterCollector(BaseCollector):
    SOURCE_NAME = "twitter"
    # 24 saat — günde 1 kez. Pipeline 2 saatte bir çalışsa bile bu collector
    # son 24h'de çalışmadıysa atlanır (BaseCollector.run rate limit kontrolü).
    COLLECT_INTERVAL_MINUTES = 1440

    def __init__(self):
        super().__init__()
        self.token = os.environ.get("APIFY_TOKEN", "").strip()

    def collect(self) -> list[RawMention]:
        if not self.token:
            logger.warning("[twitter] APIFY_TOKEN yok — collector atlandı")
            return []
        try:
            return self._run_apify()
        except Exception as e:
            logger.error(f"[twitter] collect failed: {e}")
            return []

    def _run_apify(self) -> list[RawMention]:
        """
        Tek Apify run ile tüm query'leri batch olarak çağır.
        Kesin maliyet kontrolü: maxItems = 30 hard limit.
        """
        url = f"{APIFY_BASE}/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
        params = {"token": self.token, "timeout": 120}
        body = {
            "searchTerms": list(PROBE_QUERIES),
            "sort": "Top",
            # HARD CAP: 30 tweet — Pay-per-event maliyet kontrolü.
            # 3 query × 10 = 30 tweet/run → ~$0.10/run × 30 run/ay = $3/ay max
            "maxItems": MAX_PER_QUERY * len(PROBE_QUERIES),
        }
        resp = requests.post(url, params=params, json=body, timeout=180)
        if resp.status_code != 200:
            logger.warning(f"[twitter] Apify HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        items = resp.json()
        if not isinstance(items, list):
            logger.warning(f"[twitter] beklenmedik response: {str(items)[:200]}")
            return []
        return self._parse_tweets(items)

    def _parse_tweets(self, items: list[dict]) -> list[RawMention]:
        mentions = []
        for it in items:
            text = (it.get("text") or it.get("fullText") or "").strip()
            if not text or len(text) < 10:
                continue
            # Engagement = likes + retweets + replies + quotes
            engagement = (
                int(it.get("likeCount") or it.get("favoriteCount") or 0)
                + int(it.get("retweetCount") or 0)
                + int(it.get("replyCount") or 0)
                + int(it.get("quoteCount") or 0)
            )
            if engagement < MIN_ENGAGEMENT:
                continue
            # Hangi query'den geldi? raw'da searchQuery field'ı varsa kullan
            query = (it.get("searchQuery") or it.get("query") or "").lower().strip()
            country = "TR" if query in TR_QUERIES else None
            # tweet language hint (lang='tr' → TR)
            lang = (it.get("lang") or "").lower()
            if lang == "tr":
                country = "TR"
            topic = text[:200].replace("\n", " ").strip()
            url = it.get("url") or it.get("twitterUrl") or ""
            author = (it.get("author") or {}).get("userName") or it.get("authorUsername") or ""
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=topic,
                mention_count=engagement,
                country=country,
                url=url,
                raw_data={
                    "query": query,
                    "likes": it.get("likeCount", 0),
                    "retweets": it.get("retweetCount", 0),
                    "replies": it.get("replyCount", 0),
                    "quotes": it.get("quoteCount", 0),
                    "views": it.get("viewCount", 0),
                    "author": author,
                    "lang": lang,
                    "type": "twitter_post",
                },
            ))
        logger.info(f"[twitter] Apify: {len(items)} tweet → {len(mentions)} mention (engagement>={MIN_ENGAGEMENT})")
        return mentions


if __name__ == "__main__":
    c = TwitterCollector()
    ms = c.collect()
    print(f"Toplam {len(ms)} tweet")
    for m in ms[:10]:
        print(f"  [{m.country}] eng={m.mention_count} {m.topic[:80]}")
