"""
Base Collector — Tüm collector'ların miras aldığı temel sınıf.
Her yeni kaynak bu sınıfı extend eder.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.models import RawMention


class BaseCollector(ABC):
    """Tüm collector'lar bu sınıftan türer."""

    # Alt sınıflar bu değerleri override eder
    SOURCE_NAME: str = "unknown"
    COLLECT_INTERVAL_MINUTES: int = 60  # Ne sıklıkla çalışacak

    def __init__(self):
        self.collected_at = datetime.utcnow()
        logger.info(f"[{self.SOURCE_NAME}] Collector başlatıldı")

    @abstractmethod
    def collect(self) -> list[RawMention]:
        """
        Ana toplama metodu. Alt sınıflar bunu implement eder.
        Returns: RawMention listesi
        """
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def safe_collect(self) -> list[RawMention]:
        """
        Retry mekanizmalı toplama.
        Rate limit veya geçici hatalarda 3 kez dener.
        """
        try:
            mentions = self.collect()
            logger.info(
                f"[{self.SOURCE_NAME}] {len(mentions)} mention toplandı"
            )
            return mentions
        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Toplama hatası: {e}")
            raise

    def run(self) -> list[RawMention]:
        """
        Collector'ı çalıştır ve sonuçları döndür.
        Pipeline'dan çağrılacak ana metod.
        """
        logger.info(f"[{self.SOURCE_NAME}] Çalıştırılıyor...")
        mentions = self.safe_collect()
        logger.info(
            f"[{self.SOURCE_NAME}] Tamamlandı — {len(mentions)} sonuç"
        )
        return mentions
