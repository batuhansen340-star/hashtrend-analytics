"""
HashTrend Analytics — Merkezi konfigürasyon.
Tüm ayarlar .env dosyasından okunur.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Reddit
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "HashTrend/1.0")

    # NewsAPI
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

    # Genel
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Trend Skorlama Ağırlıkları (CTS formülü)
    WEIGHT_PLATFORM_COVERAGE: float = 0.35
    WEIGHT_VELOCITY: float = 0.30
    WEIGHT_VOLUME: float = 0.20
    WEIGHT_RECENCY: float = 0.15

    # Burst Detection eşiği (z-score)
    BURST_THRESHOLD: float = 2.0

    # Aktif kaynak sayısı (CTS hesabında kullanılır)
    TOTAL_SOURCES: int = 3  # MVP: google_trends, reddit, hackernews

    # Kategoriler
    CATEGORIES: list = [
        "Technology", "Finance", "Health", "Politics",
        "Entertainment", "Education", "Science", "Sports", "Other"
    ]


settings = Settings()
