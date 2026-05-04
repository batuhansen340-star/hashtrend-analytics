"""
Bluesky Collector — AT Protocol public search API.

Bluesky X'in (Twitter) modern alternatifi; AT Protocol açık + free, auth
gerektirmez (public search). X scraping'in yerine geçer — milyonlarca eski
Twitter kullanıcısı buraya göç etti.

Strateji: trending hashtag'ler için arama + popüler keyword'ler.
Endpoint: https://api.bsky.app/xrpc/app.bsky.feed.searchPosts
Rate limit: ~3000 req/5min, anonim kullanım için yeterli.
"""

import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


# Trending probe keyword'leri — Bluesky'da popüler post bulmak için sorgular.
# Çeşitlilik: tech, kültür, gündem, TR, eğlence.
PROBE_QUERIES = [
    "ai", "crypto", "election",
    "openai", "google", "apple",
    "startup", "design",
    "tech", "music", "movie",
    "türkiye", "istanbul", "spor",
    "trump", "ukraine", "climate",
]


class BlueskyCollector(BaseCollector):
    SOURCE_NAME = "bluesky"
    COLLECT_INTERVAL_MINUTES = 120

    BASE_URL = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HashTrendAnalytics/2.0 (https://hashtrend.app)",
            "Accept": "application/json",
        })

    def collect(self) -> list[RawMention]:
        all_mentions = []
        for q in PROBE_QUERIES:
            try:
                mentions = self._search(q)
                all_mentions.extend(mentions)
            except Exception as e:
                logger.warning(f"[bluesky] '{q}' fetch hatasi: {e}")
        return all_mentions

    def _search(self, query: str, limit: int = 25) -> list[RawMention]:
        """Bluesky search; sort=top son 24 saatin popülerini döndürür."""
        params = {
            "q": query,
            "sort": "top",
            "limit": limit,
        }
        resp = self.session.get(self.BASE_URL, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[bluesky] '{query}' HTTP {resp.status_code}")
            return []
        data = resp.json()
        posts = data.get("posts", [])
        mentions = []
        for p in posts:
            record = p.get("record") or {}
            text = (record.get("text") or "").strip()
            if not text or len(text) < 10:
                continue
            # Engagement = like + repost + quote (top sort zaten popüleri verir)
            engagement = (
                int(p.get("likeCount") or 0)
                + int(p.get("repostCount") or 0)
                + int(p.get("quoteCount") or 0)
            )
            if engagement < 5:
                continue
            # İlk 200 karakter topic — uzun post'larda öz alır
            topic = text[:200].replace("\n", " ").strip()
            handle = (p.get("author") or {}).get("handle", "")
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=topic,
                mention_count=engagement,
                url=f"https://bsky.app/profile/{handle}/post/{(p.get('uri') or '').rsplit('/', 1)[-1]}" if handle else None,
                raw_data={
                    "query": query,
                    "likes": p.get("likeCount", 0),
                    "reposts": p.get("repostCount", 0),
                    "quotes": p.get("quoteCount", 0),
                    "replies": p.get("replyCount", 0),
                    "author": handle,
                    "type": "bluesky_post",
                },
            ))
        logger.info(f"[bluesky] '{query}': {len(mentions)} post")
        return mentions


if __name__ == "__main__":
    collector = BlueskyCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} Bluesky mention")
    for m in mentions[:10]:
        eng = m.mention_count
        print(f"  [{eng:>5}] {m.topic[:80]}")
