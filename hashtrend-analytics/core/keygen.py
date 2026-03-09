"""
API Key Generator — Yeni kullanıcı API key'i oluştur.

Format: ht_live_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX (36 karakter)
Prefix: ht_live_ (production) veya ht_test_ (development)

Kullanım:
  python -m core.keygen --email user@example.com --tier pro
"""

import secrets
import hashlib
import argparse
from loguru import logger

from config.settings import settings


def generate_api_key(tier: str = "free") -> tuple[str, str]:
    """
    Yeni API key oluştur.
    Returns: (full_key, key_prefix)

    Key format: ht_{env}_{random_hex}
    Toplam: 44 karakter
    """
    env = "live" if settings.ENVIRONMENT == "production" else "test"
    random_part = secrets.token_hex(16)  # 32 hex karakter
    full_key = f"ht_{env}_{random_part}"
    prefix = full_key[:12]  # "ht_test_XXXX" — debug için gösterilebilir
    return full_key, prefix


def hash_key(api_key: str) -> str:
    """
    API key'i hash'le (DB'de saklama için).
    Not: Şimdilik plaintext saklıyoruz (Supabase RLS ile koruma).
    Production'da bcrypt veya SHA-256 kullan.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_key_in_db(email: str, tier: str = "free") -> dict:
    """DB'de yeni API key oluştur."""
    from core.database import db

    full_key, prefix = generate_api_key(tier)

    # Tier bazlı limitler
    tier_limits = {
        "free": {"daily": 100, "monthly": 3000},
        "pro": {"daily": 5000, "monthly": 150000},
        "business": {"daily": 50000, "monthly": 1500000},
        "enterprise": {"daily": 500000, "monthly": 15000000},
    }

    limits = tier_limits.get(tier, tier_limits["free"])

    row = {
        "user_email": email,
        "api_key": full_key,
        "key_prefix": prefix,
        "tier": tier,
        "daily_limit": limits["daily"],
        "monthly_limit": limits["monthly"],
        "is_active": True,
    }

    try:
        result = db.client.table("api_keys").insert(row).execute()
        if result.data:
            logger.info(f"API key oluşturuldu: {prefix}... ({tier}) → {email}")
            return {
                "api_key": full_key,
                "prefix": prefix,
                "tier": tier,
                "email": email,
                "daily_limit": limits["daily"],
            }
    except Exception as e:
        logger.error(f"API key oluşturma hatası: {e}")

    return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HashTrend API Key Generator")
    parser.add_argument("--email", required=True, help="Kullanıcı e-postası")
    parser.add_argument("--tier", default="free", choices=["free", "pro", "business", "enterprise"])
    parser.add_argument("--dry-run", action="store_true", help="DB'ye kaydetme, sadece key üret")
    args = parser.parse_args()

    if args.dry_run:
        key, prefix = generate_api_key(args.tier)
        print(f"\n  API Key: {key}")
        print(f"  Prefix:  {prefix}")
        print(f"  Tier:    {args.tier}")
        print(f"  Email:   {args.email}")
        print(f"\n  ⚠️  Dry run — DB'ye kaydedilmedi.\n")
    else:
        result = create_key_in_db(args.email, args.tier)
        if result:
            print(f"\n  ✅ API Key oluşturuldu!")
            print(f"  Key:   {result['api_key']}")
            print(f"  Tier:  {result['tier']}")
            print(f"  Limit: {result['daily_limit']} req/gün\n")
        else:
            print("\n  ❌ API key oluşturulamadı.\n")
