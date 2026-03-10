"""
HashTrend Pipeline — Ana orkestrasyon scripti.

Bu script tüm adımları sırasıyla çalıştırır:
1. Collector'ları çalıştır (Google Trends, Reddit, HN)
2. Ham verileri normalize et
3. Kategorize et (Claude API)
4. Trend skorla (CTS)
5. Veritabanına kaydet
6. Telegram'a rapor gönder (opsiyonel)

GitHub Actions cron job'ı bu scripti çalıştırır.
"""

import sys
import json
from datetime import datetime
from loguru import logger

from collectors.google_trends import GoogleTrendsCollector
from collectors.reddit import RedditCollector
from collectors.hackernews import HackerNewsCollector
from collectors.wikipedia import WikipediaCollector
from core.normalizer import Normalizer
from core.scorer import TrendScorer
from core.categorizer import Categorizer
from core.models import TrendReport, TrendScore
from config.settings import settings


# Loglama ayarı
logger.remove()
logger.add(sys.stderr, level=settings.LOG_LEVEL)
logger.add("logs/pipeline_{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days")


class Pipeline:
    """HashTrend ana pipeline — collector'dan rapora kadar tüm akış."""

    def __init__(self, use_db: bool = True, send_telegram: bool = True):
        self.use_db = use_db
        self.send_telegram = send_telegram
        self.normalizer = Normalizer()
        self.categorizer = Categorizer()
        self.scorer = TrendScorer()

    def run(self) -> TrendReport:
        """
        Tüm pipeline'ı çalıştır.
        Returns: TrendReport objesi
        """
        start_time = datetime.utcnow()
        logger.info("=" * 60)
        logger.info("HashTrend Pipeline başlatıldı")
        logger.info("=" * 60)

        # ─── ADIM 1: VERİ TOPLAMA ───────────────────────────
        logger.info("Adım 1/5: Veri toplama...")
        all_mentions = []

        collectors = [
            ("Google Trends", GoogleTrendsCollector),
            ("Hacker News", HackerNewsCollector),
            ("Wikipedia", WikipediaCollector),
        ]

        # Reddit sadece credentials varsa çalış
        if settings.REDDIT_CLIENT_ID:
            collectors.append(("Reddit", RedditCollector))
        else:
            logger.warning("Reddit credentials yok — atlanıyor")

        for name, CollectorClass in collectors:
            try:
                collector = CollectorClass()
                mentions = collector.run()
                all_mentions.extend(mentions)
                logger.info(f"  ✓ {name}: {len(mentions)} mention")
            except Exception as e:
                logger.error(f"  ✗ {name} hatası: {e}")
                continue

        if not all_mentions:
            logger.warning("Hiç veri toplanamadı — pipeline durduruluyor")
            return TrendReport()

        logger.info(f"  Toplam: {len(all_mentions)} ham mention")

        # ─── ADIM 2: NORMALİZASYON ──────────────────────────
        logger.info("Adım 2/5: Normalizasyon...")
        topics = self.normalizer.normalize(all_mentions)
        logger.info(f"  {len(all_mentions)} mention → {len(topics)} benzersiz konu")

        # ─── ADIM 3: KATEGORİZASYON ─────────────────────────
        logger.info("Adım 3/5: Kategorizasyon...")
        topic_names = [t.canonical_name for t in topics]
        categories = self.categorizer.categorize(topic_names)

        for topic in topics:
            topic.category = categories.get(topic.canonical_name, "Other")

        logger.info(f"  {len(categories)} konu kategorize edildi")

        # ─── ADIM 4: SKORLAMA ───────────────────────────────
        logger.info("Adım 4/5: Trend skorlama (CTS)...")
        scores = self.scorer.score_topics(topics)
        logger.info(
            f"  {len(scores)} skor hesaplandı, "
            f"{sum(1 for s in scores if s.is_burst)} burst"
        )

        # ─── ADIM 5: KAYDET + RAPORLA ───────────────────────
        logger.info("Adım 5/5: Kayıt ve raporlama...")

        # Veritabanına kaydet
        if self.use_db:
            try:
                from core.database import db
                db.insert_raw_mentions(all_mentions)
                db.insert_trend_scores(scores)
                logger.info("  ✓ Veritabanına kaydedildi")
            except Exception as e:
                logger.error(f"  ✗ DB kayıt hatası: {e}")

        # Rapor oluştur
        report = self._build_report(scores)

        # Telegram'a gönder
        if self.send_telegram and settings.TELEGRAM_BOT_TOKEN:
            try:
                self._send_telegram(report)
                logger.info("  ✓ Telegram raporu gönderildi")
            except Exception as e:
                logger.error(f"  ✗ Telegram hatası: {e}")

        # Konsola özet
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"\nPipeline tamamlandı — {elapsed:.1f} saniye")
        self._print_summary(report)

        return report

    def _build_report(self, scores: list[TrendScore]) -> TrendReport:
        """Skorlardan rapor oluştur."""
        # Kategori dağılımı
        cat_summary = {}
        for s in scores:
            cat = s.category or "Other"
            cat_summary[cat] = cat_summary.get(cat, 0) + 1

        return TrendReport(
            total_topics=len(scores),
            burst_count=sum(1 for s in scores if s.is_burst),
            top_trends=scores[:20],
            new_entries=[s for s in scores if len(s.source_breakdown) >= 2][:10],
            category_summary=cat_summary,
        )

    def _send_telegram(self, report: TrendReport):
        """Telegram'a trend raporu gönder."""
        import requests

        # Mesaj formatla
        lines = [
            "🔥 *HashTrend Günlük Rapor*",
            f"📊 Toplam: {report.total_topics} konu",
            f"💥 Burst: {report.burst_count} patlama",
            "",
            "*Top 10 Trend:*",
        ]

        for i, trend in enumerate(report.top_trends[:10], 1):
            burst_icon = "💥" if trend.is_burst else "📈"
            cat = trend.category or "?"
            lines.append(
                f"{i}. {burst_icon} *{trend.topic_name[:50]}*\n"
                f"   CTS: {trend.cts_score} | {cat} | "
                f"Kaynaklar: {', '.join(trend.source_breakdown.keys())}"
            )

        # Kategori özeti
        if report.category_summary:
            lines.append("\n*Kategori Dağılımı:*")
            for cat, count in sorted(
                report.category_summary.items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                lines.append(f"  • {cat}: {count}")

        message = "\n".join(lines)

        # Telegram API ile gönder
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }

        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Telegram API hatası: {response.text}")

    def _print_summary(self, report: TrendReport):
        """Konsola özet yazdır."""
        print(f"\n{'='*60}")
        print(f"  HASHTREND RAPOR — {report.generated_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Toplam: {report.total_topics} konu | Burst: {report.burst_count}")
        print(f"{'='*60}\n")

        for i, trend in enumerate(report.top_trends[:15], 1):
            burst = "🔥" if trend.is_burst else "  "
            sources = ", ".join(trend.source_breakdown.keys())
            cat = f"[{trend.category}]" if trend.category else ""
            print(
                f"  {burst} {i:2d}. CTS:{trend.cts_score:5.1f} "
                f"{cat:15} {trend.topic_name[:50]}"
            )
            print(f"        Kaynaklar: {sources}")

        print()


# ─── ÇALIŞTIRMA ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HashTrend Pipeline")
    parser.add_argument("--no-db", action="store_true", help="DB kayıt yapma")
    parser.add_argument("--no-telegram", action="store_true", help="Telegram gönderme")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    pipeline = Pipeline(
        use_db=not args.no_db,
        send_telegram=not args.no_telegram,
    )

    report = pipeline.run()

    if args.json:
        # JSON çıktı (diğer sistemlerle entegrasyon için)
        output = {
            "generated_at": report.generated_at.isoformat(),
            "total_topics": report.total_topics,
            "burst_count": report.burst_count,
            "top_trends": [
                {
                    "name": t.topic_name,
                    "cts_score": t.cts_score,
                    "category": t.category,
                    "is_burst": t.is_burst,
                    "sources": list(t.source_breakdown.keys()),
                }
                for t in report.top_trends
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
