"""
HashTrend Analytics — Veri modelleri.
Tüm collector'lar bu modellere normalize eder.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class RawMention(BaseModel):
    """Collector'lardan gelen ham veri."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str  # google_trends, reddit, hackernews, wikipedia, github, news
    topic: str  # Ham konu başlığı
    mention_count: int = 1  # Bahsedilme sayısı veya popülerlik skoru
    raw_data: dict = {}  # Kaynaktan gelen ek veri
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    country: Optional[str] = None  # ISO ülke kodu (TR, US, vb.)
    url: Optional[str] = None  # Kaynak URL


class NormalizedTopic(BaseModel):
    """Normalize edilmiş konu — birden fazla kaynaktan gelen bahsedilmelerin birleşimi."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_name: str  # Normalize edilmiş konu adı
    category: Optional[str] = None  # AI tarafından atanan kategori
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    total_mentions: int = 0
    sources: list[str] = []  # Bu konuyu raporlayan kaynaklar
    country: Optional[str] = None
    summary: str = ""


class TrendScore(BaseModel):
    """Composite Trend Score (CTS) — her konu için hesaplanan skor."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic_id: str
    topic_name: str
    category: Optional[str] = None
    cts_score: float = 0.0  # 0-100 arası
    platform_coverage: float = 0.0  # 0-1 arası (kaç kaynakta geçiyor)
    velocity: float = 0.0  # Büyüme hızı
    volume: float = 0.0  # Normalize edilmiş hacim
    recency: float = 0.0  # Tazelik skoru
    is_burst: bool = False  # Patlama tespiti
    source_breakdown: dict = {}  # Kaynak bazlı mention count
    country: Optional[str] = None
    summary: str = ""
    scored_at: datetime = Field(default_factory=datetime.utcnow)


class TrendReport(BaseModel):
    """Telegram veya API'ye gönderilecek trend raporu."""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_topics: int = 0
    burst_count: int = 0
    top_trends: list[TrendScore] = []
    new_entries: list[TrendScore] = []  # Son 24 saatte ilk kez görülenler
    category_summary: dict = {}  # Kategori bazlı konu sayısı
