"""
Hacker News Collector — Resmi Firebase API ile.

Toplanan veriler:
- Top Stories (en popüler haberler)
- Best Stories (en iyi puanlı)
- New Stories (yeni eklenen)

Rate limit: Limitsiz (makul kullanım). API tamamen ücretsiz.
HN API: https://github.com/HackerNews/API
"""

import aiohttp
import asyncio
from datetime import datetime
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


class HackerNewsCollector(BaseCollector):
    SOURCE_NAME = "hackernews"
    COLLECT_INTERVAL_MINUTES = 30

    BASE_URL = "https://hacker-news.firebaseio.com/v0"
    TOP_STORIES_LIMIT = 30  # İlk 30 top story
    BEST_STORIES_LIMIT = 20  # İlk 20 best story

    def collect(self) -> list[RawMention]:
        """Senkron wrapper — asyncio event loop ile çalıştır."""
        return asyncio.run(self._async_collect())

    async def _async_collect(self) -> list[RawMention]:
        """Top ve best story'leri paralel topla."""
        all_mentions = []

        async with aiohttp.ClientSession() as session:
            # Top ve Best story ID'lerini paralel çek
            top_ids, best_ids = await asyncio.gather(
                self._fetch_story_ids(session, "topstories"),
                self._fetch_story_ids(session, "beststories"),
            )

            # Benzersiz ID'leri birleştir
            unique_ids = list(dict.fromkeys(
                top_ids[:self.TOP_STORIES_LIMIT]
                + best_ids[:self.BEST_STORIES_LIMIT]
            ))

            # Story detaylarını paralel çek (batch halinde)
            batch_size = 15
            for i in range(0, len(unique_ids), batch_size):
                batch = unique_ids[i : i + batch_size]
                stories = await asyncio.gather(
                    *[self._fetch_story(session, sid) for sid in batch]
                )

                for story in stories:
                    if story:
                        all_mentions.append(story)

        return all_mentions

    async def _fetch_story_ids(
        self, session: aiohttp.ClientSession, endpoint: str
    ) -> list[int]:
        """Story ID listesini çek."""
        url = f"{self.BASE_URL}/{endpoint}.json"

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning(f"[hackernews] {endpoint} ID listesi hatası: {e}")

        return []

    async def _fetch_story(
        self, session: aiohttp.ClientSession, story_id: int
    ) -> RawMention | None:
        """Tek bir story'nin detayını çek."""
        url = f"{self.BASE_URL}/item/{story_id}.json"

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                if not data or data.get("type") != "story":
                    return None

                title = data.get("title", "").strip()
                if not title:
                    return None

                score = data.get("score", 0)
                comments = data.get("descendants", 0)
                # HN popülerlik: score + yorum sayısı
                popularity = score + (comments * 1.5)

                return RawMention(
                    source=self.SOURCE_NAME,
                    topic=title,
                    mention_count=int(popularity),
                    raw_data={
                        "hn_id": story_id,
                        "score": score,
                        "descendants": comments,
                        "by": data.get("by", ""),
                        "time": data.get("time", 0),
                        "url": data.get("url", ""),
                        "type": data.get("type", ""),
                    },
                    url=data.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                )

        except Exception as e:
            logger.debug(f"[hackernews] Story {story_id} hatası: {e}")
            return None


# Standalone çalıştırma
if __name__ == "__main__":
    collector = HackerNewsCollector()
    mentions = collector.run()

    print(f"\n{'='*60}")
    print(f"Toplam {len(mentions)} Hacker News mention toplandı")
    print(f"{'='*60}\n")

    sorted_mentions = sorted(
        mentions, key=lambda m: m.mention_count, reverse=True
    )
    for m in sorted_mentions[:15]:
        score = m.raw_data.get("score", 0)
        comments = m.raw_data.get("descendants", 0)
        print(f"  [{score}↑ {comments}💬] {m.topic[:80]}")
