"""
Signup & Stripe Ödeme Modülü
=============================
- POST /api/v1/signup → e-posta ile ücretsiz API key oluştur
- POST /api/v1/checkout → Stripe checkout session oluştur
- POST /api/v1/webhook/stripe → Stripe webhook (ödeme sonrası tier yükselt)
"""

import os
import uuid
import hashlib
import hmac
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from loguru import logger

router = APIRouter(prefix="/api/v1", tags=["Auth"])

# ── Stripe (opsiyonel — key yoksa sadece free tier çalışır) ──────
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

stripe = None
if STRIPE_SECRET:
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET
        stripe = _stripe
        logger.info("Stripe bağlantısı kuruldu")
    except ImportError:
        logger.warning("stripe paketi yüklü değil: pip install stripe")

# ── Stripe Price ID'leri (.env'den al) ───────────────────────────
PRICE_IDS = {
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
    "business": os.getenv("STRIPE_PRICE_BUSINESS", ""),
}

# ── Pydantic modeller ────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str  # EmailStr yerine str — basit doğrulama yeterli MVP için
    name: Optional[str] = None

class SignupResponse(BaseModel):
    api_key: str
    tier: str
    daily_limit: int
    message: str

class CheckoutRequest(BaseModel):
    email: str
    plan: str  # "starter", "pro", "business"

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


# ── API Key üretici ──────────────────────────────────────────────

def generate_api_key() -> str:
    """ht_live_ prefix'li benzersiz API key üret."""
    raw = uuid.uuid4().hex
    return f"ht_live_{raw[:24]}"


# ── Supabase bağlantısı (lazy import) ───────────────────────────

def _get_db():
    """Database client'ı döndür."""
    from core.database import HashTrendDB
    return HashTrendDB()


# ── ENDPOINTS ────────────────────────────────────────────────────

@router.post("/signup", response_model=SignupResponse)
async def signup(req: SignupRequest):
    """
    Ücretsiz API key oluştur.
    E-posta zaten kayıtlıysa mevcut key'i döndür.
    """
    email = req.email.strip().lower()

    if not email or "@" not in email:
        raise HTTPException(400, "Geçersiz e-posta adresi")

    db = _get_db()

    # Mevcut kullanıcı kontrolü
    try:
        existing = (
            db.client.table("api_keys")
            .select("key, tier, daily_limit")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            return SignupResponse(
                api_key=row["key"],
                tier=row["tier"],
                daily_limit=row["daily_limit"],
                message="Bu e-posta zaten kayıtlı. Mevcut API key'iniz döndürüldü."
            )
    except Exception as e:
        logger.debug(f"Mevcut kullanıcı sorgusu: {e}")

    # Yeni key oluştur
    api_key = generate_api_key()
    key_id = str(uuid.uuid4())

    try:
        db.client.table("api_keys").insert({
            "id": key_id,
            "key": api_key,
            "email": email,
            "name": req.name or "",
            "tier": "free",
            "daily_limit": 100,
            "is_active": True,
        }).execute()

        logger.info(f"Yeni signup: {email} → free tier")

        return SignupResponse(
            api_key=api_key,
            tier="free",
            daily_limit=100,
            message="API key'iniz oluşturuldu! 100 request/gün limiti ile başlayabilirsiniz."
        )

    except Exception as e:
        logger.error(f"Signup hatası: {e}")
        raise HTTPException(500, "Kayıt sırasında hata oluştu. Lütfen tekrar deneyin.")


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(req: CheckoutRequest):
    """
    Stripe checkout session oluştur.
    Kullanıcı ödeme yaptıktan sonra tier otomatik yükseltilir.
    """
    if not stripe:
        raise HTTPException(
            501,
            "Ödeme sistemi henüz aktif değil. Şu an sadece ücretsiz plan kullanılabilir."
        )

    plan = req.plan.lower()
    if plan not in PRICE_IDS:
        raise HTTPException(400, f"Geçersiz plan: {plan}. Seçenekler: starter, pro, business")

    price_id = PRICE_IDS[plan]
    if not price_id:
        raise HTTPException(501, f"{plan} planı henüz yapılandırılmadı.")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=req.email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/pricing",
            metadata={"email": req.email, "plan": plan},
        )

        logger.info(f"Checkout oluşturuldu: {req.email} → {plan}")

        return CheckoutResponse(
            checkout_url=session.url,
            session_id=session.id,
        )

    except Exception as e:
        logger.error(f"Stripe checkout hatası: {e}")
        raise HTTPException(500, "Ödeme oturumu oluşturulamadı.")


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook — ödeme başarılı olunca tier yükselt.
    """
    if not stripe or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(501, "Stripe webhook yapılandırılmadı")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.error(f"Webhook doğrulama hatası: {e}")
        raise HTTPException(400, "Webhook doğrulama başarısız")

    # Ödeme başarılı → tier yükselt
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("metadata", {}).get("email", "")
        plan = session.get("metadata", {}).get("plan", "")

        if email and plan:
            _upgrade_tier(email, plan)

    return {"status": "ok"}


# ── Tier güncelleme ──────────────────────────────────────────────

TIER_LIMITS = {
    "free": 100,
    "starter": 2000,
    "pro": 20000,
    "business": 100000,
}

def _upgrade_tier(email: str, plan: str):
    """Kullanıcının tier'ını güncelle."""
    db = _get_db()
    daily_limit = TIER_LIMITS.get(plan, 100)

    try:
        db.client.table("api_keys").update({
            "tier": plan,
            "daily_limit": daily_limit,
        }).eq("email", email).execute()

        logger.info(f"Tier yükseltildi: {email} → {plan} ({daily_limit} req/gün)")
    except Exception as e:
        logger.error(f"Tier güncelleme hatası: {e}")


# ── api_keys tablosu Supabase'de yoksa oluşturulacak SQL ────────
"""
Supabase SQL Editor'de çalıştır (eğer api_keys tablosu boşsa):

ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT '';
"""
