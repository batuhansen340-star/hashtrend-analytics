"""
Twitter / X Collector — Apify üzerinden apidojo/twitter-scraper-lite actor'u.

X (Twitter) resmi API'sı $100/ay basic tier'a çıktı (free tier kapatıldı 2023).
snscrape deprecated. Apify Twitter scraper actor'u $0.25/1000 tweet, free
$5/ay = ~20K tweet, scrape proxy/IP rotation Apify tarafında çözülüyor.

Strateji: TR + global trend keyword'leri için Top tweet'leri çek (engagement
filter Apify tarafında 'sort=Top' ile yapılıyor). Her tweet bir RawMention.

Env: APIFY_TOKEN (Railway → Variables; .env'e koymak yerine production'da
secret manager kullan).

Maliyet: 12 keyword × 50 tweet × 12 run/gün ≈ 7K tweet/gün ≈ $1.75/ay (free
tier'da kalır).
"""

import os
import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


# Apify actor: apidojo/twitter-scraper-lite
APIFY_ACTOR = "apidojo~twitter-scraper-lite"
APIFY_BASE = "https://api.apify.com/v2"

# Probe keyword'leri — global tech + TR sinyali
PROBE_QUERIES = [
    # Global tech / gündem
    "#AI", "#crypto", "#openai",
    # TR sinyali (TR_QUERIES ile çakışır → country='TR')
    "türkiye", "ekonomi", "gündem",
    "galatasaray", "fenerbahçe",
    "istanbul", "ankara",
]

# country='TR' işaretlenecek query'ler (Bluesky pattern)
TR_QUERIES = frozenset({
    "türkiye", "ekonomi", "gündem",
    "galatasaray", "fenerbahçe",
    "istanbul", "ankara",
})

# Run başına kaç tweet
MAX_PER_QUERY = 50
# Engagement minimum (like + retweet + reply)
MIN_ENGAGEMENT = 5


class TwitterCollector(BaseCollector):
    SOURCE_NAME = "twitter"
    COLLECT_INTERVAL_MINUTES = 120

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
        run-sync-get-dataset-items: actor'ü çalıştırır, dataset'i döner.
        """
        url = f"{APIFY_BASE}/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
        params = {"token": self.token, "timeout": 120}
        body = {
            "searchTerms": list(PROBE_QUERIES),
            "sort": "Top",
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
