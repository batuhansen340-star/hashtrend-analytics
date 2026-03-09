"""
Trend Scoring Engine — Composite Trend Score (CTS) hesaplayıcı.

CTS = (Platform_Coverage × 0.35) + (Velocity × 0.30) + (Volume × 0.20) + (Recency × 0.15)

Bu modül sistemin kalbi — çapraz platform korelasyonla "gerçek trend" tespiti yapar.
"""

import math
from datetime import datetime, timedelta
from loguru import logger

from config.settings import settings
from core.models import NormalizedTopic, TrendScore


class TrendScorer:
    """CTS (Composite Trend Score) hesaplayıcı."""

    def __init__(
        self,
        historical_data: dict[str, list[int]] | None = None
    ):
        """
        Args:
            historical_data: Geçmiş mention verileri (burst detection için).
                             Format: {"topic_name": [mention_count_day1, day2, ...]}
        """
        self.historical = historical_data or {}

    def score_topics(
        self, topics: list[NormalizedTopic]
    ) -> list[TrendScore]:
        """
        Tüm normalize konuları skorla.
        Returns: CTS skoruna göre sıralı TrendScore listesi.
        """
        if not topics:
            return []

        # Tüm konulardaki max mention (Volume normalizasyonu için)
        max_mentions = max(t.total_mentions for t in topics) if topics else 1

        scores = []
        for topic in topics:
            score = self._calculate_cts(topic, max_mentions)
            scores.append(score)

        # CTS skoruna göre sırala (yüksekten düşüğe)
        scores.sort(key=lambda s: s.cts_score, reverse=True)

        logger.info(
            f"Skorlama tamamlandı: {len(scores)} konu, "
            f"burst: {sum(1 for s in scores if s.is_burst)}"
        )
        return scores

    def _calculate_cts(
        self, topic: NormalizedTopic, max_mentions: int
    ) -> TrendScore:
        """Tek bir konu için CTS hesapla."""

        # 1. Platform Coverage (0-1): Kaç farklı kaynakta geçiyor?
        platform_coverage = len(topic.sources) / settings.TOTAL_SOURCES

        # 2. Velocity (0-1): Büyüme hızı
        velocity = self._calculate_velocity(topic)

        # 3. Volume (0-1): Normalize edilmiş hacim (logaritmik)
        if max_mentions > 1 and topic.total_mentions > 0:
            volume = math.log(topic.total_mentions + 1) / math.log(max_mentions + 1)
        else:
            volume = 0.0

        # 4. Recency (0-1): Ne kadar taze?
        recency = self._calculate_recency(topic)

        # CTS hesapla (0-100 ölçeğinde)
        cts = (
            (platform_coverage * settings.WEIGHT_PLATFORM_COVERAGE)
            + (velocity * settings.WEIGHT_VELOCITY)
            + (volume * settings.WEIGHT_VOLUME)
            + (recency * settings.WEIGHT_RECENCY)
        ) * 100

        # Burst detection
        is_burst = self._detect_burst(topic)

        # Kaynak bazlı dağılım
        source_breakdown = {}
        # Not: Gerçek implementasyonda her kaynak için ayrı mention_count tutulacak
        for src in topic.sources:
            source_breakdown[src] = topic.total_mentions // len(topic.sources)

        return TrendScore(
            topic_id=topic.id,
            topic_name=topic.canonical_name,
            category=topic.category,
            cts_score=round(min(cts, 100), 2),
            platform_coverage=round(platform_coverage, 2),
            velocity=round(velocity, 4),
            volume=round(volume, 2),
            recency=round(recency, 2),
            is_burst=is_burst,
            source_breakdown=source_breakdown,
        )

    def _calculate_velocity(self, topic: NormalizedTopic) -> float:
        """
        Büyüme hızı hesapla.
        Geçmiş veri varsa: (şimdiki - önceki) / önceki
        Yoksa: kaynak sayısına göre tahmin.
        """
        name = topic.canonical_name

        if name in self.historical and len(self.historical[name]) >= 2:
            prev = self.historical[name][-2]
            curr = self.historical[name][-1]

            if prev > 0:
                raw_velocity = (curr - prev) / prev
                # 0-1 arasına normalize (sigmoid benzeri)
                return min(1.0, max(0.0, raw_velocity / (1 + abs(raw_velocity))))

        # Geçmiş veri yoksa: çoklu kaynak = yüksek velocity varsayımı
        # İlk kez 3 kaynakta birden görünüyorsa hızlı büyüyen bir konu
        return min(1.0, len(topic.sources) * 0.25)

    def _calculate_recency(self, topic: NormalizedTopic) -> float:
        """
        Tazelik skoru: Son görülme ne kadar yakın?
        Son 1 saat = 1.0, 24 saat öncesi = 0.0
        """
        now = datetime.utcnow()
        hours_ago = (now - topic.last_seen).total_seconds() / 3600

        if hours_ago <= 0:
            return 1.0
        elif hours_ago >= 24:
            return 0.0
        else:
            return 1.0 - (hours_ago / 24.0)

    def _detect_burst(self, topic: NormalizedTopic) -> bool:
        """
        Patlama tespiti: z-score bazlı anomali detection.
        z_score = (current - mean) / std
        z_score > BURST_THRESHOLD ise burst = True
        """
        name = topic.canonical_name

        if name not in self.historical or len(self.historical[name]) < 3:
            # Yeterli geçmiş yok — çoklu kaynak + yüksek mention = burst varsay
            return (
                len(topic.sources) >= 2
                and topic.total_mentions > 500
            )

        history = self.historical[name]
        current = topic.total_mentions

        # Ortalama ve standart sapma
        mean_val = sum(history) / len(history)
        variance = sum((x - mean_val) ** 2 for x in history) / len(history)
        std_val = math.sqrt(variance) if variance > 0 else 1.0

        z_score = (current - mean_val) / std_val

        return z_score > settings.BURST_THRESHOLD


# Standalone test
if __name__ == "__main__":
    scorer = TrendScorer(
        historical_data={
            "GPT-5 Released by OpenAI": [100, 150, 200, 300, 5000],
        }
    )

    test_topics = [
        NormalizedTopic(
            canonical_name="GPT-5 Released by OpenAI",
            sources=["google_trends", "reddit", "hackernews"],
            total_mentions=5800,
            last_seen=datetime.utcnow(),
        ),
        NormalizedTopic(
            canonical_name="Bitcoin crashes below 50k",
            sources=["google_trends", "reddit"],
            total_mentions=3085,
            last_seen=datetime.utcnow() - timedelta(hours=2),
        ),
        NormalizedTopic(
            canonical_name="Show HN: New programming language",
            sources=["hackernews"],
            total_mentions=200,
            last_seen=datetime.utcnow() - timedelta(hours=6),
        ),
    ]

    scores = scorer.score_topics(test_topics)

    print(f"\n{'='*60}")
    print("TREND SKORLARI (CTS)")
    print(f"{'='*60}\n")

    for s in scores:
        burst = "🔥 BURST" if s.is_burst else ""
        print(f"  CTS: {s.cts_score:5.1f} | {s.topic_name[:50]}")
        print(f"         Coverage: {s.platform_coverage:.2f} | "
              f"Velocity: {s.velocity:.4f} | "
              f"Volume: {s.volume:.2f} | "
              f"Recency: {s.recency:.2f} {burst}")
        print()
