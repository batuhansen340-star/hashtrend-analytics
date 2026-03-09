"""
HashTrend Cache — In-memory TTL cache.

Redis'e ihtiyaç duymadan basit ama etkili cache.
Trend verisi saatte 1 kez değişiyor → 60sn TTL ile
DB yükünü %95+ azaltır.

Thread-safe: asyncio ortamında sorunsuz çalışır.
"""

import time
import hashlib
import json
from typing import Any, Optional
from loguru import logger


class TTLCache:
    """Simple in-memory cache with per-key TTL."""

    def __init__(self, default_ttl: int = 60):
        """
        Args:
            default_ttl: Varsayılan cache süresi (saniye).
        """
        self._store: dict[str, tuple[Any, float]] = {}  # {key: (value, expires_at)}
        self.default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Cache'ten oku. Süresi dolmuşsa None döner."""
        if key in self._store:
            value, expires_at = self._store[key]
            if time.time() < expires_at:
                self._hits += 1
                return value
            else:
                # Süresi dolmuş — sil
                del self._store[key]

        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Cache'e yaz."""
        ttl = ttl or self.default_ttl
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> bool:
        """Cache'ten sil."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def invalidate_pattern(self, prefix: str) -> int:
        """Belirli prefix ile başlayan tüm key'leri sil."""
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    def clear(self) -> None:
        """Tüm cache'i temizle."""
        self._store.clear()

    def cleanup_expired(self) -> int:
        """Süresi dolmuş tüm entry'leri temizle."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def stats(self) -> dict:
        """Cache istatistikleri."""
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "0%",
        }


def make_cache_key(prefix: str, **params) -> str:
    """
    Deterministik cache key oluştur.
    Aynı parametreler her zaman aynı key'i üretir.
    """
    # None değerleri filtrele ve sırala
    filtered = {k: v for k, v in sorted(params.items()) if v is not None}
    param_str = json.dumps(filtered, sort_keys=True, default=str)
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"{prefix}:{param_hash}"


# Singleton — tüm uygulama genelinde tek cache instance
cache = TTLCache(default_ttl=60)

# Cache süreleri (saniye)
CACHE_TTL = {
    "trends": 60,         # Trend listesi: 1 dakika
    "trend_detail": 120,  # Tek konu detayı: 2 dakika
    "categories": 300,    # Kategoriler: 5 dakika (nadiren değişir)
    "search": 30,         # Arama: 30 saniye (daha dinamik)
    "burst": 45,          # Burst: 45 saniye (kritik, taze olmalı)
}
