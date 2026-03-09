"""
╔══════════════════════════════════════════════════════════════╗
║  HASHTREND SPRINT 1 AUDIT — API + DB + PERFORMANS          ║
║  3 Skill Perspektifinden Mevcut Kod Analizi                  ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SKILL #37 — API TASARIMI: 11 KRİTİK SORUN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 1. RESPONSE FORMATI TUTARSIZ
   Bazı endpoint'ler {"status", "count", "trends"} dönerken
   bazıları {"status", "query", "results"} dönüyor.
   → Stripe gibi tutarlı envelope: {"data", "meta", "error"}

❌ 2. AUTH YOK
   Hiçbir endpoint auth gerektirmiyor.
   Free tier bile API key istemeli — yoksa abuse kontrolü yok.
   → X-API-Key header + middleware

❌ 3. RATE LIMITING YOK
   Biri saniyede 1000 istek atabilir, DB çöker.
   → slowapi ile tier bazlı rate limit

❌ 4. PAGİNATION YOK
   /trends 200 sonuç dönebilir ama cursor yok.
   Developer "sonraki sayfa" çekemiyor.
   → cursor-based pagination (offset değil — veri değişken)

❌ 5. HATA KODLARI JENERİK
   except Exception: boş liste dön — developer ne olduğunu bilemiyor.
   → Hata taksonomisi: INVALID_API_KEY, RATE_LIMIT_EXCEEDED, vb.

❌ 6. HISTORY ENDPOINT'İ URL'DE topic_name KULLANIYOR
   /history/GPT-5 Released → URL encoding sorunu.
   → /topics/{topic_id}/history (UUID kullan)

❌ 7. FİLTRELEME YETERSİZ
   Tarih aralığı filtresi yok, çoklu kategori seçimi yok,
   kaynak bazlı filtre yok.

❌ 8. CORS allow_origins=["*"]
   Production'da wildcard CORS = güvenlik açığı.

❌ 9. run-pipeline ENDPOINT'İ GÜVENSİZ
   Development check'i kolay bypass edilir.

❌ 10. CACHING YOK
    Her istek direkt DB'ye gidiyor. Aynı veri 1 saat boyunca
    değişmiyor ama her seferinde sorgulanıyor.

❌ 11. REQUEST ID YOK
    Hata debug'ı imkansız — hangi istek hangi hatayı üretti?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SKILL #38 — DB ŞEMASI: 8 KRİTİK SORUN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 1. trend_scores TABLOSUNDA topic_name TEKRAR EDİYOR
   topic_name zaten normalized_topics'te var.
   Denormalizasyon JSONB source_breakdown için tamam ama
   topic_name + category gereksiz duplikasyon.
   → topic_id FK üzerinden JOIN yap, veya materialized view

❌ 2. trend_scores'DA ZAMAN SERİSİ İÇİN PARTİTION YOK
   30 gün × 24 saat × 200 konu = ~144K satır/ay.
   6 ayda 864K satır — scored_at filtresi full table scan.
   → RANGE partition by scored_at (aylık)

❌ 3. raw_mentions'DA topic KOLONU İNDEX'İ B-TREE
   VARCHAR(500) üzerinde B-tree verimsiz.
   → GIN trigram index (pg_trgm) ile fuzzy search

❌ 4. normalized_topics.sources TEXT[] ARRAY
   Array'de "bu kaynak var mı?" sorgusu yavaş.
   → Ayrı tablo: topic_sources (topic_id, source, mention_count)
   Bu aynı zamanda source_breakdown sorununu da çözer.

❌ 5. api_keys'TE requests_today ATOMIC DEĞİL
   Concurrent isteklerde race condition.
   → Redis counter veya PostgreSQL advisory lock

❌ 6. UPDATED_AT KOLONU YOK
   Hiçbir tabloda updated_at yok. Değişiklik takibi imkansız.

❌ 7. SOFT DELETE YOK
   Yanlışlıkla silinen veri geri getirilemez.

❌ 8. CHECK CONSTRAINT'LER EKSİK
   cts_score negatif olabilir, tier rastgele string olabilir.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SKILL #44 — PERFORMANS: 6 DARBOĞAZ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 1. HER API İSTEĞİNDE from core.database import db
   Her endpoint'te lazy import yapılıyor.
   → App startup'ta bir kez import, dependency injection

❌ 2. NORMALIZER O(n²) COMPLEXITY
   _group_similar() her yeni mention'ı TÜM mevcut gruplarla
   karşılaştırıyor. 500 mention × 200 grup = 100K comparison.
   → İlk keyword'e göre hash bucket, sonra grup içi karşılaştır
   Beklenen iyileşme: ~10-20x

❌ 3. SCORER'DA historical_data DB'DEN ÇEKİLMİYOR
   Manuel dict veriliyor. Gerçek burst detection çalışmıyor.
   → Pipeline'da DB'den son 7 gün verisini çek

❌ 4. GOOGLE TRENDS COLLECTOR SENKRON
   4 ülke × 2 sn sleep = 8 saniye minimum.
   → asyncio ile paralel (aynı anda 2 ülke)

❌ 5. API RESPONSE'DA SELECT * KULLANILIYOR
   Tüm kolonlar çekiliyor ama client yarısını kullanmıyor.
   → Sadece gerekli kolonları seç

❌ 6. CACHE KATMANI YOK
   /trends endpoint'i saatte 1 kez değişen veri için
   her istekte DB'ye gidiyor.
   → In-memory TTL cache (60sn), Redis gerekli değil başta
"""
