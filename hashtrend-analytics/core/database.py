"""
HashTrend Analytics — Supabase veritabanı istemcisi.
Tüm DB operasyonları bu modül üzerinden yapılır.

Supabase'de aşağıdaki tabloları oluşturman gerekiyor:
SQL'leri supabase_schema.sql dosyasında bulabilirsin.
"""

from datetime import datetime, timedelta
from typing import Optional
from loguru import logger

from config.settings import settings
from core.models import RawMention, NormalizedTopic, TrendScore


class Database:
    """Supabase veritabanı işlemleri."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy initialization — ilk kullanımda bağlan."""
        if self._client is None:
            from supabase import create_client
            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            logger.info("Supabase bağlantısı kuruldu")
        return self._client

    # ─── RAW MENTIONS ────────────────────────────────────────

    def insert_raw_mentions(self, mentions: list[RawMention]) -> int:
        """Ham bahsedilmeleri toplu olarak kaydet."""
        if not mentions:
            return 0

        rows = [
            {
                "id": m.id,
                "source": m.source,
                "topic": m.topic,
                "mention_count": m.mention_count,
                "raw_data": m.raw_data,
                "collected_at": m.collected_at.isoformat(),
                "country": m.country,
                "url": m.url,
            }
            for m in mentions
        ]

        try:
            result = self.client.table("raw_mentions").insert(rows).execute()
            count = len(result.data) if result.data else 0
            logger.info(f"{count} raw mention kaydedildi")
            return count
        except Exception as e:
            logger.error(f"raw_mentions insert hatası: {e}")
            return 0

    def get_raw_mentions(
        self,
        source: Optional[str] = None,
        hours: int = 24,
        limit: int = 1000
    ) -> list[dict]:
        """Belirli zaman aralığındaki ham bahsedilmeleri getir."""
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        query = (
            self.client.table("raw_mentions")
            .select("*")
            .gte("collected_at", since)
            .order("collected_at", desc=True)
            .limit(limit)
        )

        if source:
            query = query.eq("source", source)

        try:
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"raw_mentions select hatası: {e}")
            return []

    # ─── NORMALIZED TOPICS ───────────────────────────────────

    def upsert_normalized_topic(self, topic: NormalizedTopic) -> bool:
        """Normalize edilmiş konuyu ekle veya güncelle."""
        row = {
            "id": topic.id,
            "canonical_name": topic.canonical_name,
            "category": topic.category,
            "first_seen": topic.first_seen.isoformat(),
            "last_seen": topic.last_seen.isoformat(),
            "total_mentions": topic.total_mentions,
            "sources": topic.sources,
            "country": topic.country,
        }

        try:
            self.client.table("normalized_topics").upsert(
                row, on_conflict="canonical_name"
            ).execute()
            return True
        except Exception as e:
            logger.error(f"normalized_topics upsert hatası: {e}")
            return False

    def get_normalized_topics(self, hours: int = 24) -> list[dict]:
        """Son N saatteki normalize konuları getir."""
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        try:
            result = (
                self.client.table("normalized_topics")
                .select("*")
                .gte("last_seen", since)
                .order("total_mentions", desc=True)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"normalized_topics select hatası: {e}")
            return []

    def find_topic_by_name(self, name: str) -> Optional[dict]:
        """Konu adına göre ara."""
        try:
            result = (
                self.client.table("normalized_topics")
                .select("*")
                .eq("canonical_name", name)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"topic arama hatası: {e}")
            return None

    # ─── TREND SCORES ────────────────────────────────────────

    def insert_trend_scores(self, scores: list[TrendScore]) -> int:
        """Trend skorlarını toplu kaydet."""
        if not scores:
            return 0

        rows = [
            {
                "id": s.id,
                "topic_id": s.topic_id,
                "topic_name": s.topic_name,
                "category": s.category,
                "cts_score": s.cts_score,
                "platform_coverage": s.platform_coverage,
                "velocity": s.velocity,
                "volume": s.volume,
                "recency": s.recency,
                "is_burst": s.is_burst,
                "source_breakdown": s.source_breakdown,
                "scored_at": s.scored_at.isoformat(),
            }
            for s in scores
        ]

        try:
            result = self.client.table("trend_scores").insert(rows).execute()
            count = len(result.data) if result.data else 0
            logger.info(f"{count} trend skoru kaydedildi")
            return count
        except Exception as e:
            logger.error(f"trend_scores insert hatası: {e}")
            return 0

    def get_latest_scores(
        self,
        category: Optional[str] = None,
        min_score: float = 0,
        limit: int = 50
    ) -> list[dict]:
        """En güncel trend skorlarını getir."""
        try:
            query = (
                self.client.table("trend_scores")
                .select("*")
                .gte("cts_score", min_score)
                .order("cts_score", desc=True)
                .limit(limit)
            )

            if category:
                query = query.eq("category", category)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"trend_scores select hatası: {e}")
            return []

    def get_historical_scores(self, topic_name: str, days: int = 30) -> list[dict]:
        """Bir konunun tarihsel skorlarını getir (zaman serisi için)."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()

        try:
            result = (
                self.client.table("trend_scores")
                .select("*")
                .eq("topic_name", topic_name)
                .gte("scored_at", since)
                .order("scored_at", desc=True)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"historical scores hatası: {e}")
            return []


# Singleton instance
db = Database()
