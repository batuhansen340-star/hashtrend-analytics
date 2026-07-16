"""
Bluesky Collector — AT Protocol public search API.

Bluesky X'in (Twitter) modern alternatifi; AT Protocol açık + free, auth
gerektirmez (public search). X scraping'in yerine geçer — milyonlarca eski
Twitter kullanıcısı buraya göç etti.

Strateji: trending hashtag'ler için arama + popüler keyword'ler.
Endpoint: https://api.bsky.app/xrpc/app.bsky.feed.searchPosts
Rate limit: ~3000 req/5min, anonim kullanım için yeterli.
"""

import time
from itertools import zip_longest

import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


# Trending probe keyword'leri — Bluesky'da popüler post bulmak için sorgular.
# İki grup ayrı tutulur ve aşağıda DÖNÜŞÜMLÜ dizilir: rate limit hangi
# noktada keserse kessin iki gruptan da veri gelsin.

# Kahve & tatlı radarı probe'ları (EN + TR)
_FOOD_PROBES = [
    "matcha", "dubai chocolate", "pistachio latte", "cold brew",
    "tiramisu", "croissant", "cheesecake", "iced coffee",
    "specialty coffee", "boba", "crookie", "banana pudding", "tanghulu",
    # "san sebastian" TR sorgusu DEĞİL (İspanya şehri) — nitelikli EN kalıp
    "san sebastian cheesecake",
    # TR sorguları — TR_QUERIES ile çakışır, country='TR' set edilir
    "kahve", "tatlı", "künefe", "trileçe",
    "dubai çikolatası", "türk kahvesi",
]

# Genel probe'lar — tech, kültür, gündem, TR, eğlence
_GENERAL_PROBES = [
    "ai", "crypto", "election",
    "openai", "google", "apple",
    "startup", "design",
    "tech", "music", "movie",
    "trump", "ukraine", "climate",
    # TR sinyali veren query'ler
    "türkiye", "istanbul", "ankara", "izmir",
    "gündem", "ekonomi", "spor", "magazin",
    "galatasaray", "fenerbahçe",
]


def _interleave(a: list[str], b: list[str]) -> list[str]:
    """İki listeyi dönüşümlü diz (a0, b0, a1, b1, ...); uzun olanın artığı sona."""
    out = []
    for x, y in zip_longest(a, b):
        if x is not None:
            out.append(x)
        if y is not None:
            out.append(y)
    return out


PROBE_QUERIES = _interleave(_FOOD_PROBES, _GENERAL_PROBES)

# Sorgular arası nezaket beklemesi — art arda ~10 sorgudan sonra API 403
# (rate limit) döndürüyordu; 2s aralık limiti tetiklemiyor.
QUERY_SLEEP = 2.0
# 403 sonrası soğuma beklemesi (tek yeniden deneme hakkı)
RATE_LIMIT_COOLDOWN = 30


class _RateLimited(Exception):
    """Aynı sorguda art arda iki 403 — bu run için kalan sorgular atlanır."""

# TR sinyali veren query'ler — bu sorgularla bulunan post'lar country='TR' işaretlenir.
TR_QUERIES = frozenset({
    "türkiye", "istanbul", "ankara", "izmir",
    "gündem", "ekonomi", "spor", "magazin",
    "galatasaray", "fenerbahçe",
    # Kahve & tatlı radarı — TR sorguları
    "kahve", "tatlı", "künefe", "trileçe",
    "dubai çikolatası", "türk kahvesi",
})


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
        for i, q in enumerate(PROBE_QUERIES):
            if i:
                time.sleep(QUERY_SLEEP)  # rate limit önleme
            try:
                mentions = self._search(q)
                all_mentions.extend(mentions)
            except _RateLimited:
                remaining = len(PROBE_QUERIES) - i - 1
                logger.warning(
                    f"[bluesky] '{q}' ikinci 403 — rate limit kalıcı, "
                    f"kalan {remaining} sorgu bu run için atlandı"
                )
                break
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
        if resp.status_code == 403:
            # Rate limit: soğu, BİR kez yeniden dene; ikinci 403 run'ı keser
            logger.warning(
                f"[bluesky] '{query}' HTTP 403 — {RATE_LIMIT_COOLDOWN}s "
                f"bekleyip yeniden denenecek"
            )
            time.sleep(RATE_LIMIT_COOLDOWN)
            resp = self.session.get(self.BASE_URL, params=params, timeout=15)
            if resp.status_code == 403:
                raise _RateLimited(query)
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
            country = "TR" if query in TR_QUERIES else None
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=topic,
                mention_count=engagement,
                country=country,
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
