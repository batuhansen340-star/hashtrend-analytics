"""
HashTrend Analytics API — FastAPI ile RESTful endpoint'ler.

Kullanım:
  uvicorn api.main:app --reload --port 8000

Docs:
  http://localhost:8000/docs (Swagger UI)
  http://localhost:8000/redoc (ReDoc)
"""

from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings

app = FastAPI(
    title="HashTrend Analytics API",
    description="Global Trend Intelligence Platform — çapraz platform trend verisi",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — dashboard'dan erişim için
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production'da spesifik domain yaz
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── RESPONSE MODELLERİ ─────────────────────────────────────

class TrendItem(BaseModel):
    topic_name: str
    cts_score: float
    category: Optional[str] = None
    is_burst: bool = False
    platform_coverage: float = 0.0
    velocity: float = 0.0
    sources: list[str] = []
    scored_at: Optional[str] = None


class TrendsResponse(BaseModel):
    status: str = "ok"
    count: int
    trends: list[TrendItem]


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


# ─── ENDPOINT'LER ────────────────────────────────────────────

@app.get("/", response_model=HealthResponse)
async def root():
    """API sağlık kontrolü."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/api/v1/trends", response_model=TrendsResponse)
async def get_trends(
    category: Optional[str] = Query(None, description="Kategori filtresi"),
    min_score: float = Query(0, description="Minimum CTS skoru", ge=0, le=100),
    burst_only: bool = Query(False, description="Sadece burst konular"),
    limit: int = Query(50, description="Sonuç limiti", ge=1, le=200),
):
    """
    Güncel trend listesi.
    Filtreler: kategori, min skor, sadece burst, limit.
    """
    try:
        from core.database import db
        raw_scores = db.get_latest_scores(
            category=category, min_score=min_score, limit=limit
        )
    except Exception:
        # DB bağlantısı yoksa boş dön
        raw_scores = []

    trends = []
    for row in raw_scores:
        if burst_only and not row.get("is_burst", False):
            continue

        trends.append(TrendItem(
            topic_name=row.get("topic_name", ""),
            cts_score=row.get("cts_score", 0),
            category=row.get("category"),
            is_burst=row.get("is_burst", False),
            platform_coverage=row.get("platform_coverage", 0),
            velocity=row.get("velocity", 0),
            sources=list(row.get("source_breakdown", {}).keys()),
            scored_at=row.get("scored_at"),
        ))

    return TrendsResponse(count=len(trends), trends=trends[:limit])


@app.get("/api/v1/trends/burst", response_model=TrendsResponse)
async def get_burst_trends(
    limit: int = Query(20, ge=1, le=100),
):
    """Şu anda patlama yapan konular."""
    return await get_trends(burst_only=True, limit=limit)


@app.get("/api/v1/categories")
async def get_categories():
    """Mevcut kategoriler ve açıklamaları."""
    return {
        "status": "ok",
        "categories": settings.CATEGORIES,
    }


@app.get("/api/v1/history/{topic_name}")
async def get_history(
    topic_name: str,
    days: int = Query(30, ge=1, le=365),
):
    """Bir konunun tarihsel trend verisi (zaman serisi)."""
    try:
        from core.database import db
        history = db.get_historical_scores(topic_name, days=days)
    except Exception:
        history = []

    return {
        "status": "ok",
        "topic": topic_name,
        "days": days,
        "data_points": len(history),
        "history": history,
    }


@app.get("/api/v1/search")
async def search_trends(
    q: str = Query(..., description="Arama terimi", min_length=2),
    limit: int = Query(20, ge=1, le=100),
):
    """Konu arama (basit text match)."""
    try:
        from core.database import db
        # Supabase'de ilike ile arama
        result = (
            db.client.table("trend_scores")
            .select("*")
            .ilike("topic_name", f"%{q}%")
            .order("cts_score", desc=True)
            .limit(limit)
            .execute()
        )
        data = result.data or []
    except Exception:
        data = []

    return {
        "status": "ok",
        "query": q,
        "count": len(data),
        "results": data,
    }


# ─── API INIT ────────────────────────────────────────────────

@app.get("/api/v1/run-pipeline")
async def trigger_pipeline():
    """
    Pipeline'ı manuel tetikle (geliştirme/test için).
    Production'da bu endpoint kaldırılacak veya auth eklenecek.
    """
    if settings.ENVIRONMENT != "development":
        raise HTTPException(403, "Pipeline sadece development'ta tetiklenebilir")

    from pipeline import Pipeline

    pipeline = Pipeline(use_db=True, send_telegram=False)
    report = pipeline.run()

    return {
        "status": "ok",
        "total_topics": report.total_topics,
        "burst_count": report.burst_count,
        "top_5": [
            {"name": t.topic_name, "cts": t.cts_score, "burst": t.is_burst}
            for t in report.top_trends[:5]
        ],
    }
