"""
Google Trends Collector — pytrends kütüphanesi ile.

Toplanan veriler:
- Trending searches (ülke bazlı, real-time)
- Related queries (ilgili arama terimleri)

Rate limit: ~100 istek/saat — sleep ile yönetilir.
"""

import time
from datetime import datetime
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


class GoogleTrendsCollector(BaseCollector):
    SOURCE_NAME = "google_trends"
    COLLECT_INTERVAL_MINUTES = 60  # Saatte bir çalış

    # Takip edilecek ülkeler
    COUNTRIES = {
        "turkey": "TR",
        "united_states": "US",
        "united_kingdom": "GB",
        "germany": "DE",
    }

    def __init__(self):
        super().__init__()
        from pytrends.request import TrendReq
        self.pytrends = TrendReq(
            hl="en-US",
            tz=180,  # Türkiye UTC+3
            timeout=(10, 25),
            retries=3,
            backoff_factor=0.5,
        )

    def collect(self) -> list[RawMention]:
        """Tüm ülkelerden trending searches topla."""
        all_mentions = []

        for country_name, country_code in self.COUNTRIES.items():
            try:
                mentions = self._collect_trending(country_name, country_code)
                all_mentions.extend(mentions)
                # Rate limit koruması: istekler arası bekleme
                time.sleep(2)
            except Exception as e:
                logger.warning(
                    f"[google_trends] {country_name} hatası: {e}"
                )
                continue

        # Global trending (real-time)
        try:
            global_mentions = self._collect_realtime_trends()
            all_mentions.extend(global_mentions)
        except Exception as e:
            logger.warning(f"[google_trends] Realtime trends hatası: {e}")

        return all_mentions

    def _collect_trending(
        self, country_name: str, country_code: str
    ) -> list[RawMention]:
        """Belirli bir ülkenin trending aramalarını topla."""
        mentions = []

        try:
            # Günlük trending aramalar
            df = self.pytrends.trending_searches(pn=country_name)

            for idx, row in df.iterrows():
                topic = str(row[0]).strip()
                if not topic or len(topic) < 2:
                    continue

                mentions.append(
                    RawMention(
                        source=self.SOURCE_NAME,
                        topic=topic,
                        mention_count=100 - idx,  # Sıralama bazlı skor (1. = 100)
                        country=country_code,
                        raw_data={
                            "rank": int(idx) + 1,
                            "country": country_code,
                            "type": "daily_trending",
                        },
                    )
                )

            logger.debug(
                f"[google_trends] {country_code}: {len(mentions)} trend"
            )

        except Exception as e:
            logger.warning(f"[google_trends] {country_code} trending hatası: {e}")

        return mentions

    def _collect_realtime_trends(self) -> list[RawMention]:
        """Real-time trending konuları topla (global)."""
        mentions = []

        try:
            df = self.pytrends.realtime_trending_searches(pn="US")

            if df is not None and not df.empty:
                for idx, row in df.head(20).iterrows():
                    # realtime_trending_searches farklı kolonlar döner
                    title = str(row.get("title", row.get("entityNames", "")))
                    if not title or len(title) < 2:
                        continue

                    mentions.append(
                        RawMention(
                            source=self.SOURCE_NAME,
                            topic=title,
                            mention_count=80,  # Realtime = yüksek skor
                            country="GLOBAL",
                            raw_data={
                                "type": "realtime_trending",
                                "rank": int(idx) + 1,
                            },
                        )
                    )

        except Exception as e:
            # realtime_trending_searches bazen çalışmıyor — critical değil
            logger.debug(f"[google_trends] Realtime trends mevcut değil: {e}")

        return mentions

    def collect_interest(self, keywords: list[str]) -> dict:
        """
        Belirli keyword'lerin popülerliğini kontrol et.
        Normalizasyon aşamasında kullanılabilir.
        Returns: {keyword: interest_score}
        """
        results = {}

        try:
            self.pytrends.build_payload(
                keywords[:5],  # Max 5 keyword
                timeframe="now 7-d",
                geo="",
            )
            df = self.pytrends.interest_over_time()

            if not df.empty:
                for kw in keywords[:5]:
                    if kw in df.columns:
                        results[kw] = int(df[kw].mean())

        except Exception as e:
            logger.warning(f"[google_trends] Interest sorgusu hatası: {e}")

        return results


# Standalone çalıştırma
if __name__ == "__main__":
    collector = GoogleTrendsCollector()
    mentions = collector.run()

    print(f"\n{'='*60}")
    print(f"Toplam {len(mentions)} Google Trends mention toplandı")
    print(f"{'='*60}\n")

    for m in mentions[:15]:
        print(f"  [{m.country}] {m.topic} (skor: {m.mention_count})")
