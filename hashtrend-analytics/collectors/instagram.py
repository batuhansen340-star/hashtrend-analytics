"""
Instagram Collector — Apify apify/instagram-hashtag-scraper.

IG'de "trending hashtags" resmi listesi yok. Yaklaşım: TR pazarında popüler
sabit hashtag setini günde 1 kez tara, son post'ların engagement'ı ile
hangi hashtag'in patladığını yakala.

Strateji:
  • 10 sabit TR popüler hashtag (keşfet, türkiye, istanbul, moda, vs.)
  • Her hashtag için top 5 son post
  • Günde 1 run (24h interval)
  • Her post bir mention; hashtag = topic clusterı için sinyal

Maliyet: 50 post/gün × 30 × $0.0023 = ~$3.45/ay (Apify free tier'da)
Env: APIFY_TOKEN (GHA secret).
"""

import os
import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


APIFY_ACTOR = "apify~instagram-hashtag-scraper"
APIFY_BASE = "https://api.apify.com/v2"

# TR pazarında popüler sabit hashtag'ler — engagement değişkenleri trend sinyali
TR_HASHTAGS = [
    "kesfet", "türkiye", "istanbul", "ankara", "moda",
    "yemektarifi", "spor", "futbol", "müzik", "mizah",
]
RESULTS_PER_HASHTAG = 5
MIN_LIKES = 100


class InstagramCollector(BaseCollector):
    SOURCE_NAME = "instagram"
    # Günde 1 run — Apify maliyet kontrolü
    COLLECT_INTERVAL_MINUTES = 1440

    def __init__(self):
        super().__init__()
        self.token = os.environ.get("APIFY_TOKEN", "").strip()

    def collect(self) -> list[RawMention]:
        if not self.token:
            logger.warning("[instagram] APIFY_TOKEN yok — collector atlandı")
            return []
        try:
            return self._run_apify()
        except Exception as e:
            logger.error(f"[instagram] collect failed: {e}")
            return []

    def _run_apify(self) -> list[RawMention]:
        url = f"{APIFY_BASE}/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
        params = {"token": self.token, "timeout": 180}
        body = {
            "hashtags": TR_HASHTAGS,
            "resultsLimit": RESULTS_PER_HASHTAG,
            # HARD CAP: maliyet
            "maxItems": RESULTS_PER_HASHTAG * len(TR_HASHTAGS),
        }
        resp = requests.post(url, params=params, json=body, timeout=300)
        if resp.status_code != 200:
            logger.warning(f"[instagram] Apify HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        items = resp.json()
        if not isinstance(items, list):
            logger.warning(f"[instagram] beklenmedik response: {str(items)[:200]}")
            return []
        return self._parse_posts(items)

    def _parse_posts(self, items: list[dict]) -> list[RawMention]:
        mentions = []
        for it in items:
            caption = (it.get("caption") or it.get("text") or "").strip()
            if not caption or len(caption) < 10:
                continue
            likes = int(it.get("likesCount") or it.get("likes") or 0)
            if likes < MIN_LIKES:
                continue
            engagement = (
                likes
                + int(it.get("commentsCount") or it.get("comments") or 0) * 3
                + int(it.get("videoViewCount") or 0) // 100
            )
            topic = caption[:200].replace("\n", " ").strip()
            url = it.get("url") or it.get("displayUrl") or ""
            owner = (it.get("ownerUsername") or it.get("username") or "")
            hashtag = it.get("searchHashtag") or it.get("hashtag") or ""
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=topic,
                mention_count=engagement,
                country="TR",
                url=url,
                raw_data={
                    "likes": likes,
                    "comments": it.get("commentsCount", 0),
                    "videoViews": it.get("videoViewCount", 0),
                    "owner": owner,
                    "hashtag": hashtag,
                    "type": "instagram_post",
                },
            ))
        logger.info(f"[instagram] Apify: {len(items)} post → {len(mentions)} mention")
        return mentions


if __name__ == "__main__":
    c = InstagramCollector()
    ms = c.collect()
    print(f"Toplam {len(ms)} IG mention")
    for m in ms[:5]:
        print(f"  [{m.country}] eng={m.mention_count} {m.topic[:80]}")
