t = open('api/main.py').read()

feeds_code = '''

# ─── USER FEEDS (Kaydedilmis Aramalar) ──────────────────────

@app.post("/api/v2/feeds", tags=["User Feeds"])
async def create_feed(
    auth: dict = Depends(verify_api_key),
    feed_name: str = Query(..., min_length=1, max_length=100, description="Feed adi (MMA Trendleri, Kripto, vb.)"),
    keywords: str = Query(..., description="Aranacak kelimeler, virgul ile (MMA,UFC,fighting)"),
    countries: str = Query(None, description="Ulke kodlari, virgul ile (US,TR)"),
    min_score: float = Query(0, ge=0, le=100),
    min_engagement: int = Query(0, ge=0),
    edu_only: bool = Query(False),
    alert_email: str = Query(None, description="Bildirim email adresi"),
):
    """Kisisel feed olustur — kaydedilmis arama."""
    try:
        from core.database import db
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        co_list = [c.strip().upper() for c in countries.split(",") if c.strip()] if countries else []

        result = db.client.table("user_feeds").insert({
            "user_email": auth.get("email", ""),
            "api_key": auth.get("api_key", ""),
            "feed_name": feed_name,
            "keywords": kw_list,
            "countries": co_list,
            "min_score": min_score,
            "min_engagement": min_engagement,
            "edu_only": edu_only,
            "alert_enabled": bool(alert_email),
            "alert_email": alert_email or "",
        }).execute()

        feed = result.data[0] if result.data else {}
        return {
            "message": "Feed olusturuldu",
            "feed": {
                "id": feed.get("id"),
                "name": feed_name,
                "keywords": kw_list,
                "countries": co_list,
            }
        }
    except Exception as e:
        logger.error(f"Feed olusturma hatasi: {e}")
        raise HTTPException(status_code=500, detail="Feed olusturulamadi")


@app.get("/api/v2/feeds", tags=["User Feeds"])
async def list_feeds(auth: dict = Depends(verify_api_key)):
    """Kullanicinin tum kaydedilmis feed'lerini listele."""
    try:
        from core.database import db
        result = db.client.table("user_feeds").select("*").eq(
            "api_key", auth.get("api_key", "")
        ).order("created_at", desc=True).execute()

        feeds = []
        for f in (result.data or []):
            feeds.append({
                "id": f.get("id"),
                "name": f.get("feed_name"),
                "keywords": f.get("keywords", []),
                "countries": f.get("countries", []),
                "minScore": f.get("min_score", 0),
                "minEngagement": f.get("min_engagement", 0),
                "eduOnly": f.get("edu_only", False),
                "alertEnabled": f.get("alert_enabled", False),
                "alertEmail": f.get("alert_email", ""),
                "createdAt": f.get("created_at", ""),
            })

        return {"feeds": feeds, "total": len(feeds)}
    except Exception as e:
        logger.error(f"Feed listeleme hatasi: {e}")
        return {"feeds": [], "total": 0}


@app.get("/api/v2/feeds/{feed_id}/results", tags=["User Feeds"])
async def get_feed_results(
    feed_id: str,
    auth: dict = Depends(verify_api_key),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    """Kaydedilmis feed'in sonuclarini getir — tum keyword'leri arar."""
    try:
        from core.database import db

        # Feed'i bul
        feed_result = db.client.table("user_feeds").select("*").eq(
            "id", feed_id
        ).eq("api_key", auth.get("api_key", "")).execute()

        if not feed_result.data:
            raise HTTPException(status_code=404, detail="Feed bulunamadi")

        feed = feed_result.data[0]
        keywords = feed.get("keywords", [])
        countries = feed.get("countries", [])
        min_score = feed.get("min_score", 0)
        edu_only = feed.get("edu_only", False)

        # Her keyword icin arama yap
        all_results = {}
        for kw in keywords:
            query = db.client.table("latest_trend_scores").select("*")
            query = query.or_(
                f"topic_name.ilike.%{kw}%,summary.ilike.%{kw}%,category.ilike.%{kw}%,course_idea.ilike.%{kw}%"
            )
            if min_score > 0:
                query = query.gte("cts_score", min_score)
            if edu_only:
                query = query.gte("edu_score", 6)
            query = query.order("cts_score", desc=True).limit(100)

            result = query.execute()
            for row in (result.data or []):
                tid = row.get("id")
                if tid not in all_results:
                    all_results[tid] = row

        # Country filtrele
        rows = list(all_results.values())
        if countries:
            rows = [r for r in rows if r.get("country", "GLOBAL") in countries or "GLOBAL" in countries]

        # Engagement filtrele
        min_eng = feed.get("min_engagement", 0)
        if min_eng > 0:
            def total_eng(r):
                sb = r.get("source_breakdown", {}) or {}
                return sum(v for v in sb.values() if isinstance(v, (int, float)))
            rows = [r for r in rows if total_eng(r) >= min_eng]

        # Sirala
        rows.sort(key=lambda r: r.get("cts_score", 0), reverse=True)

        # Pagination
        offset = (page - 1) * limit
        page_rows = rows[offset:offset + limit]

        trends = [row_to_trend_item(row) for row in page_rows]

        return {
            "feed": {
                "id": feed.get("id"),
                "name": feed.get("feed_name"),
                "keywords": keywords,
            },
            "data": trends,
            "meta": make_meta(
                request_id=auth["request_id"],
                total=len(trends),
                page=page,
                limit=limit,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feed results hatasi: {e}")
        return {"feed": {}, "data": [], "meta": {}}


@app.delete("/api/v2/feeds/{feed_id}", tags=["User Feeds"])
async def delete_feed(
    feed_id: str,
    auth: dict = Depends(verify_api_key),
):
    """Kaydedilmis feed'i sil."""
    try:
        from core.database import db
        result = db.client.table("user_feeds").delete().eq(
            "id", feed_id
        ).eq("api_key", auth.get("api_key", "")).execute()

        if result.data:
            return {"message": "Feed silindi", "id": feed_id}
        else:
            raise HTTPException(status_code=404, detail="Feed bulunamadi")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feed silme hatasi: {e}")
        raise HTTPException(status_code=500, detail="Feed silinemedi")

'''

# BURST TRENDS'den once ekle
t = t.replace('# ─── BURST TRENDS', feeds_code + '\n# ─── BURST TRENDS')
open('api/main.py', 'w').write(t)
print('User Feeds endpoints added!')
