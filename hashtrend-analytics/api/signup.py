import os
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/api/v1", tags=["Auth"])

STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

stripe = None
if STRIPE_SECRET:
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET
        stripe = _stripe
    except ImportError:
        pass

PRICE_IDS = {
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
    "business": os.getenv("STRIPE_PRICE_BUSINESS", ""),
}

class SignupRequest(BaseModel):
    email: str
    name: Optional[str] = None

class SignupResponse(BaseModel):
    api_key: str
    tier: str
    daily_limit: int
    message: str

class CheckoutRequest(BaseModel):
    email: str
    plan: str

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

TIER_LIMITS = {"free": 100, "starter": 2000, "pro": 20000, "business": 100000}

def generate_api_key():
    return f"ht_live_{uuid.uuid4().hex[:24]}"

def _get_db():
    from core.database import Database
    return Database()

@router.post("/signup", response_model=SignupResponse)
async def signup(req: SignupRequest):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Geçersiz e-posta")
    db = _get_db()
    try:
        existing = db.client.table("api_keys").select("api_key,tier,daily_limit").eq("user_email", email).limit(1).execute()
        if existing.data:
            r = existing.data[0]
            return SignupResponse(api_key=r["api_key"], tier=r["tier"], daily_limit=r["daily_limit"], message="Mevcut key döndürüldü.")
    except Exception:
        pass
    api_key = generate_api_key()
    try:
        db.client.table("api_keys").insert({"id": str(uuid.uuid4()), "api_key": api_key, "key_prefix": api_key[:8], "user_email": email, "tier": "free", "daily_limit": 100, "is_active": True}).execute()
        return SignupResponse(api_key=api_key, tier="free", daily_limit=100, message="API key oluşturuldu! 100 req/gün.")
    except Exception as e:
        raise HTTPException(500, f"Kayıt hatası: {e}")

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(req: CheckoutRequest):
    if not stripe:
        raise HTTPException(501, "Ödeme sistemi henüz aktif değil.")
    plan = req.plan.lower()
    if plan not in PRICE_IDS or not PRICE_IDS[plan]:
        raise HTTPException(400, f"Geçersiz plan: {plan}")
    try:
        session = stripe.checkout.Session.create(payment_method_types=["card"], mode="subscription", customer_email=req.email, line_items=[{"price": PRICE_IDS[plan], "quantity": 1}], success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}", cancel_url=f"{FRONTEND_URL}/pricing", metadata={"email": req.email, "plan": plan})
        return CheckoutResponse(checkout_url=session.url, session_id=session.id)
    except Exception as e:
        raise HTTPException(500, f"Stripe hatası: {e}")

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not stripe or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(501, "Webhook yapılandırılmadı")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Doğrulama başarısız")
    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        email = s.get("metadata", {}).get("email", "")
        plan = s.get("metadata", {}).get("plan", "")
        if email and plan:
            db = _get_db()
            try:
                db.client.table("api_keys").update({"tier": plan, "daily_limit": TIER_LIMITS.get(plan, 100)}).eq("user_email", email).execute()
            except Exception:
                pass
    return {"status": "ok"}
