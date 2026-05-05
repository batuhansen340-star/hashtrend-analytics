"""
TikTok Collector — Apify clockworks/tiktok-scraper trending mode.

Eski TikTokApi (David Teather) kütüphanesi GHA runner'da Playwright session
30s timeout'una takılıyordu (production'da hep 0 video). Apify actor stable
ve proxy/IP rotation Apify tarafında.

Strateji: TR-spesifik hashtag'lerden top trending video'ları çek.
  • 5 TR popüler hashtag: kesfet, fyp, gündem, türkiye, mizah
  • Her hashtag için 10 top video
  • Günde 1 run (24h interval) — maliyet kontrolü

Maliyet: 50 video/gün × 30 × $0.0003 = ~$0.45/ay (free tier)
Env: APIFY_TOKEN (GHA secret).
"""

import os
import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


APIFY_ACTOR = "apidojo~tiktok-scraper"
APIFY_BASE = "https://api.apify.com/v2"

# TR Tiktok'ta popüler keşfet hashtag'leri
TR_HASHTAGS = ["kesfet", "fyp", "gündem", "türkiye", "mizah"]
MAX_VIDEOS_PER_HASHTAG = 10
MIN_PLAY_COUNT = 1000


class TikTokCollector(BaseCollector):
    SOURCE_NAME = "tiktok"
    # Günde 1 run — Apify Pay-per-event maliyet kontrolü
    COLLECT_INTERVAL_MINUTES = 1440

    def __init__(self):
        super().__init__()
        self.token = os.environ.get("APIFY_TOKEN", "").strip()

    def collect(self) -> list[RawMention]:
        if not self.token:
            logger.warning("[tiktok] APIFY_TOKEN yok — collector atlandı")
            return []
        try:
            return self._run_apify()
        except Exception as e:
            logger.error(f"[tiktok] collect failed: {e}")
            return []

    def _run_apify(self) -> list[RawMention]:
        url = f"{APIFY_BASE}/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
        params = {"token": self.token, "timeout": 180}
        # clockworks/tiktok-scraper input format
        body = {
            "hashtags": TR_HASHTAGS,
            "resultsPerPage": MAX_VIDEOS_PER_HASHTAG,
            # HARD CAP: maliyet kontrolü
            "maxItems": MAX_VIDEOS_PER_HASHTAG * len(TR_HASHTAGS),
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        }
        resp = requests.post(url, params=params, json=body, timeout=300)
        if resp.status_code != 200:
            logger.warning(f"[tiktok] Apify HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        items = resp.json()
        if not isinstance(items, list):
            logger.warning(f"[tiktok] beklenmedik response: {str(items)[:200]}")
            return []
        return self._parse_videos(items)

    def _parse_videos(self, items: list[dict]) -> list[RawMention]:
        mentions = []
        for it in items:
            text = (it.get("text") or it.get("desc") or "").strip()
            if not text or len(text) < 5:
                continue
            play_count = int(it.get("playCount") or it.get("viewCount") or 0)
            if play_count < MIN_PLAY_COUNT:
                continue
            engagement = (
                int(it.get("diggCount") or it.get("likeCount") or 0)
                + int(it.get("shareCount") or 0)
                + int(it.get("commentCount") or 0)
            )
            topic = text[:200].replace("\n", " ").strip()
            url = it.get("webVideoUrl") or it.get("url") or ""
            author = (it.get("authorMeta") or {}).get("name") or it.get("author") or ""
            # Hashtag bilgisi varsa raw_data'ya
            hashtag = (it.get("searchHashtag") or {}).get("name") or it.get("hashtag") or ""
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=topic,
                mention_count=engagement or play_count // 100,
                country="TR",  # TR hashtag'lerinden gelir
                url=url,
                raw_data={
                    "playCount": play_count,
                    "likes": it.get("diggCount", 0),
                    "shares": it.get("shareCount", 0),
                    "comments": it.get("commentCount", 0),
                    "author": author,
                    "hashtag": hashtag,
                    "type": "tiktok_video",
                },
            ))
        logger.info(f"[tiktok] Apify: {len(items)} video → {len(mentions)} mention")
        return mentions


if __name__ == "__main__":
    c = TikTokCollector()
    ms = c.collect()
    print(f"Toplam {len(ms)} TikTok mention")
    for m in ms[:5]:
        print(f"  [{m.country}] eng={m.mention_count} {m.topic[:80]}")
