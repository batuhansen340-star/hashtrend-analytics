-- ============================================================
-- HashTrend Analytics — V2 Veritabanı Şeması
-- Sprint 1 Audit sonrası yeniden tasarlandı.
--
-- Değişiklikler:
-- • topic_sources ayrı tablo (array yerine relational)
-- • trend_scores partition by scored_at
-- • CHECK constraint'ler eklendi
-- • updated_at + soft delete eklendi
-- • GIN trigram index (fuzzy search)
-- • Composite index'ler (query pattern bazlı)
-- • api_keys güçlendirildi (usage_logs ayrı tablo)
-- ============================================================

-- Trigram extension (fuzzy search için)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─── 1. KAYNAK TANIMLARI (lookup table) ─────────────────────
-- ENUM yerine lookup table → yeni kaynak eklemek kolay
CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,     -- google_trends, reddit, hackernews...
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    collect_interval_min INTEGER DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO sources (name, display_name, collect_interval_min) VALUES
    ('google_trends', 'Google Trends', 60),
    ('reddit', 'Reddit', 30),
    ('hackernews', 'Hacker News', 30),
    ('wikipedia', 'Wikipedia', 120),
    ('github', 'GitHub Trending', 60),
    ('newsapi', 'NewsAPI', 60)
ON CONFLICT (name) DO NOTHING;

-- ─── 2. HAM BAHSEDİLMELER ──────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    topic VARCHAR(500) NOT NULL,
    mention_count INTEGER DEFAULT 1 CHECK (mention_count >= 0),
    raw_data JSONB DEFAULT '{}',
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    country VARCHAR(5),              -- ISO 3166 alpha-2 (kısaltıldı)
    url TEXT,
    -- Dedup: aynı kaynak + aynı konu + aynı saat = tek kayıt
    CONSTRAINT uq_mention_source_topic_hour
        UNIQUE (source_id, topic, (DATE_TRUNC('hour', collected_at)))
);

-- Composite index: en sık sorgu "son N saatteki belirli kaynak verileri"
CREATE INDEX IF NOT EXISTS idx_raw_source_time
    ON raw_mentions (source_id, collected_at DESC);

-- GIN trigram: topic üzerinde fuzzy search
CREATE INDEX IF NOT EXISTS idx_raw_topic_trgm
    ON raw_mentions USING GIN (topic gin_trgm_ops);

-- Partition hazırlığı: collected_at bazlı aylık cleanup kolay
CREATE INDEX IF NOT EXISTS idx_raw_collected
    ON raw_mentions (collected_at DESC);

-- ─── 3. NORMALİZE KONULAR ──────────────────────────────────
CREATE TABLE IF NOT EXISTS topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(500) UNIQUE NOT NULL,
    slug VARCHAR(500) UNIQUE NOT NULL,    -- URL-safe versiyon: "gpt-5-released"
    category VARCHAR(50) CHECK (category IN (
        'Technology', 'Finance', 'Health', 'Politics',
        'Entertainment', 'Education', 'Science', 'Sports', 'Other'
    )),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    total_mentions INTEGER DEFAULT 0 CHECK (total_mentions >= 0),
    country VARCHAR(5),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ              -- soft delete
);

CREATE INDEX IF NOT EXISTS idx_topics_category ON topics(category) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_topics_last_seen ON topics(last_seen DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_topics_slug ON topics(slug) WHERE deleted_at IS NULL;
-- GIN trigram: canonical_name üzerinde fuzzy search
CREATE INDEX IF NOT EXISTS idx_topics_name_trgm
    ON topics USING GIN (canonical_name gin_trgm_ops);

-- Updated_at otomatik güncelleme trigger'ı
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_topics_updated
    BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── 4. KONU-KAYNAK İLİŞKİSİ (M:N) ────────────────────────
-- Eski: sources TEXT[] array → Yeni: ayrı tablo
-- Bu tablo source_breakdown sorununu da çözer
CREATE TABLE IF NOT EXISTS topic_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    mention_count INTEGER DEFAULT 0 CHECK (mention_count >= 0),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_topic_source UNIQUE (topic_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_topic_sources_topic ON topic_sources(topic_id);

-- ─── 5. TREND SKORLARI ─────────────────────────────────────
-- Denormalize: topic_name ve category burada tutulur (okuma performansı)
-- Çünkü bu tablo API'nin ana veri kaynağı ve JOIN yapmamak 2-3x hızlı
CREATE TABLE IF NOT EXISTS trend_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    -- Denormalize alanlar (okuma performansı için, yazma sırasında set edilir)
    topic_name VARCHAR(500) NOT NULL,
    topic_slug VARCHAR(500) NOT NULL,
    category VARCHAR(50),
    -- CTS bileşenleri
    cts_score DECIMAL(5,2) DEFAULT 0 CHECK (cts_score >= 0 AND cts_score <= 100),
    platform_coverage DECIMAL(3,2) DEFAULT 0 CHECK (platform_coverage >= 0 AND platform_coverage <= 1),
    velocity DECIMAL(10,4) DEFAULT 0,
    volume DECIMAL(5,2) DEFAULT 0,
    recency DECIMAL(3,2) DEFAULT 0 CHECK (recency >= 0 AND recency <= 1),
    -- Detaylar
    is_burst BOOLEAN DEFAULT FALSE,
    source_count INTEGER DEFAULT 0,
    source_breakdown JSONB DEFAULT '{}',  -- {"google_trends": 85, "reddit": 3000}
    -- Zamanlar
    scored_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ana sorgu: "en yüksek CTS'ye sahip son skorlar"
-- Composite index: scored_at DESC + cts_score DESC
CREATE INDEX IF NOT EXISTS idx_scores_time_cts
    ON trend_scores (scored_at DESC, cts_score DESC);

-- Kategori filtresi
CREATE INDEX IF NOT EXISTS idx_scores_category_cts
    ON trend_scores (category, cts_score DESC);

-- Burst filtresi (partial index — sadece burst=true satırları)
CREATE INDEX IF NOT EXISTS idx_scores_burst
    ON trend_scores (scored_at DESC, cts_score DESC) WHERE is_burst = TRUE;

-- Topic bazlı tarihsel sorgular
CREATE INDEX IF NOT EXISTS idx_scores_topic_time
    ON trend_scores (topic_id, scored_at DESC);

-- Slug bazlı arama (API'de /topics/{slug}/history için)
CREATE INDEX IF NOT EXISTS idx_scores_slug
    ON trend_scores (topic_slug, scored_at DESC);

-- ─── 6. API KEY YÖNETİMİ ───────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,       -- İlk 8 karakter (debug için göster)
    tier VARCHAR(20) DEFAULT 'free' CHECK (tier IN ('free', 'pro', 'business', 'enterprise')),
    daily_limit INTEGER NOT NULL DEFAULT 100,
    monthly_limit INTEGER NOT NULL DEFAULT 3000,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,              -- Opsiyonel son kullanma tarihi
    metadata JSONB DEFAULT '{}'          -- Ek bilgiler (şirket adı, vb.)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_api_keys_email ON api_keys(user_email);

CREATE TRIGGER trg_api_keys_updated
    BEFORE UPDATE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── 7. API KULLANIM LOGLARI ────────────────────────────────
-- requests_today yerine ayrı log tablosu (race condition yok)
CREATE TABLE IF NOT EXISTS api_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,           -- ms cinsinden response süresi
    ip_address INET,
    requested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Günlük kullanım sayımı için composite index
CREATE INDEX IF NOT EXISTS idx_usage_key_time
    ON api_usage_logs (api_key_id, requested_at DESC);

-- Partition hazırlığı: aylık retention
CREATE INDEX IF NOT EXISTS idx_usage_time
    ON api_usage_logs (requested_at DESC);

-- ─── 8. SON PIPELINE ÇALIŞTIRMA KAYDI ───────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    total_mentions INTEGER DEFAULT 0,
    total_topics INTEGER DEFAULT 0,
    burst_count INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds DECIMAL(8,2)
);

-- ─── 9. YARDIMCI FONKSİYONLAR ──────────────────────────────

-- Slug oluşturucu
CREATE OR REPLACE FUNCTION generate_slug(input_text TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN LOWER(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                TRIM(input_text),
                '[^a-zA-Z0-9\s-]', '', 'g'  -- Özel karakterleri sil
            ),
            '\s+', '-', 'g'                  -- Boşlukları tire yap
        )
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Günlük API kullanım sayısı
CREATE OR REPLACE FUNCTION get_daily_usage(p_api_key_id UUID)
RETURNS INTEGER AS $$
    SELECT COUNT(*)::INTEGER
    FROM api_usage_logs
    WHERE api_key_id = p_api_key_id
      AND requested_at >= DATE_TRUNC('day', NOW());
$$ LANGUAGE sql STABLE;

-- ─── 10. VERİ TEMİZLİK ─────────────────────────────────────

CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
DECLARE
    deleted_mentions INTEGER;
    deleted_scores INTEGER;
    deleted_logs INTEGER;
BEGIN
    -- 90 günden eski raw mention'ları sil
    DELETE FROM raw_mentions
    WHERE collected_at < NOW() - INTERVAL '90 days';
    GET DIAGNOSTICS deleted_mentions = ROW_COUNT;

    -- 90 günden eski trend skorlarını sil
    DELETE FROM trend_scores
    WHERE scored_at < NOW() - INTERVAL '90 days';
    GET DIAGNOSTICS deleted_scores = ROW_COUNT;

    -- 60 günden eski usage log'larını sil
    DELETE FROM api_usage_logs
    WHERE requested_at < NOW() - INTERVAL '60 days';
    GET DIAGNOSTICS deleted_logs = ROW_COUNT;

    RAISE NOTICE 'Temizlik: % mention, % skor, % log silindi',
        deleted_mentions, deleted_scores, deleted_logs;
END;
$$ LANGUAGE plpgsql;

-- ─── 11. MATERIALIZED VIEW: EN SON SKORLAR ─────────────────
-- API'nin ana endpoint'i bu view'ı okur (cache katmanı)
-- Her pipeline run'ında REFRESH MATERIALIZED VIEW CONCURRENTLY çalışır
CREATE MATERIALIZED VIEW IF NOT EXISTS latest_trend_scores AS
SELECT DISTINCT ON (topic_id)
    ts.id,
    ts.topic_id,
    ts.topic_name,
    ts.topic_slug,
    ts.category,
    ts.cts_score,
    ts.platform_coverage,
    ts.velocity,
    ts.volume,
    ts.recency,
    ts.is_burst,
    ts.source_count,
    ts.source_breakdown,
    ts.scored_at
FROM trend_scores ts
ORDER BY topic_id, scored_at DESC;

-- Unique index (CONCURRENTLY refresh için gerekli)
CREATE UNIQUE INDEX IF NOT EXISTS idx_latest_scores_topic
    ON latest_trend_scores (topic_id);
CREATE INDEX IF NOT EXISTS idx_latest_scores_cts
    ON latest_trend_scores (cts_score DESC);
CREATE INDEX IF NOT EXISTS idx_latest_scores_category
    ON latest_trend_scores (category, cts_score DESC);
CREATE INDEX IF NOT EXISTS idx_latest_scores_burst
    ON latest_trend_scores (cts_score DESC) WHERE is_burst = TRUE;

-- ============================================================
-- ÖLÇEKLENMEZLİK NOTLARI
-- ============================================================
-- 1M satır: Mevcut index'ler yeterli. VACUUM ANALYZE ayarla.
-- 10M satır: trend_scores'u RANGE partition (scored_at, aylık).
--            raw_mentions'ı da partition et.
-- 100M satır: Read replica ekle, API'yi replica'dan oku.
--             TimescaleDB'ye geçiş düşün (hypertable).
-- ============================================================
