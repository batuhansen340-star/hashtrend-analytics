"""
TikTok Collector v2 — TikTokApi (David Teather) ile reverse engineered access.

Eski v1 (basit requests + regex) 0 mention çekiyordu çünkü TikTok client-side
render eder (SPA), HTML'de hashtag yok. v2 TikTokApi'nin Playwright tabanlı
signature generation'ı ile mobile API endpoint'lerine erişir.

Bakım maliyeti: TikTok signature algoritması her güncellediğinde TikTokApi
maintainer patch atar (genelde 2-3 haftada bir). Bu collector graceful fail
yapar — TikTokApi import edilmezse veya çağrı patlasa pipeline durmaz, sadece
0 mention döner.

GitHub: https://github.com/davidteather/TikTok-Api
"""

import asyncio
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


# Trending fetch parametreleri
VIDEO_COUNT = 30          # TikTok trending feed'inden kaç video al
MIN_PLAY_COUNT = 10_000   # Aşağısı noise sayılır, atlanır
TOPIC_MAX_LEN = 200       # video açıklamasını kırp


class TikTokCollector(BaseCollector):
    SOURCE_NAME = "tiktok"
    COLLECT_INTERVAL_MINUTES = 120

    def collect(self) -> list[RawMention]:
        """
        Senkron BaseCollector.collect() interface'ini sağla.
        İçeride asyncio.run() ile async TikTokApi'yi sar.
        Hata yutar — pipeline'ı durdurmaz.
        """
        try:
            return asyncio.run(self._collect_async())
        except Exception as e:
            logger.warning(f"[tiktok] async run hatası ({type(e).__name__}): {e}")
            return []

    async def _collect_async(self) -> list[RawMention]:
        """TikTokApi async session — trending feed'den video çek."""
        try:
            from TikTokApi import TikTokApi  # noqa: F401  (lazy import)
        except ImportError:
            logger.warning("[tiktok] TikTokApi kütüphanesi yüklü değil — atlanıyor")
            return []

        from TikTokApi import TikTokApi
        mentions: list[RawMention] = []

        async with TikTokApi() as api:
            try:
                # Headless chromium session aç + ms_token + signature gen
                await api.create_sessions(
                    num_sessions=1,
                    sleep_after=3,
                    headless=True,
                    browser="chromium",
                )
            except Exception as e:
                logger.warning(f"[tiktok] session oluşturulamadı: {e}")
                return []

            try:
                async for video in api.trending.videos(count=VIDEO_COUNT):
                    mention = self._video_to_mention(video)
                    if mention is not None:
                        mentions.append(mention)
            except Exception as e:
                logger.warning(f"[tiktok] trending fetch hatası: {e}")

        logger.info(f"[tiktok] {len(mentions)} trending video toplandı")
        return mentions

    def _video_to_mention(self, video) -> RawMention | None:
        """TikTokApi Video objesini RawMention'a çevir. Geçersizse None."""
        try:
            info = getattr(video, "as_dict", None) or {}
        except Exception:
            return None

        desc = (info.get("desc") or "").strip()
        if not desc or len(desc) < 5:
            return None

        stats = info.get("stats") or info.get("statsV2") or {}
        # statsV2 string olarak döndürebilir, int'e çevir
        try:
            play_count = int(stats.get("playCount") or 0)
        except (TypeError, ValueError):
            play_count = 0

        if play_count < MIN_PLAY_COUNT:
            return None

        topic = desc[:TOPIC_MAX_LEN].replace("\n", " ").strip()
        author_id = ((info.get("author") or {}).get("uniqueId") or "").strip()
        video_id = (info.get("id") or "").strip()
        url = (
            f"https://www.tiktok.com/@{author_id}/video/{video_id}"
            if author_id and video_id else None
        )

        def _safe_int(v):
            try:
                return int(v or 0)
            except (TypeError, ValueError):
                return 0

        return RawMention(
            source=self.SOURCE_NAME,
            topic=topic,
            mention_count=play_count,
            country="GLOBAL",
            url=url,
            raw_data={
                "type": "tiktok_trending",
                "play_count": play_count,
                "like_count": _safe_int(stats.get("diggCount")),
                "comment_count": _safe_int(stats.get("commentCount")),
                "share_count": _safe_int(stats.get("shareCount")),
                "video_id": video_id,
                "author": author_id,
            },
        )


if __name__ == "__main__":
    collector = TikTokCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} TikTok video")
    for m in mentions[:10]:
        play = m.raw_data.get("play_count", 0)
        author = m.raw_data.get("author", "?")
        print(f"  [{play:>10,}] @{author}: {m.topic[:80]}")
