-- ============================================================
-- HashTrend Analytics — Supabase Veritabanı Şeması
-- Bu SQL'i Supabase SQL Editor'de çalıştır.
-- ============================================================

-- 1. Ham bahsedilmeler (collector'lardan gelen raw data)
CREATE TABLE IF NOT EXISTS raw_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,          -- google_trends, reddit, hackernews, vb.
    topic VARCHAR(500) NOT NULL,           -- Ham konu başlığı
    mention_count INTEGER DEFAULT 1,       -- Bahsedilme sayısı / popülerlik skoru
    raw_data JSONB DEFAULT '{}',           -- Kaynaktan gelen ek veri
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    country VARCHAR(10),                   -- ISO ülke kodu (TR, US, vb.)
    url TEXT                               -- Kaynak URL
);

-- Index'ler: sorgularda sık kullanılan alanlar
CREATE INDEX IF NOT EXISTS idx_raw_mentions_source ON raw_mentions(source);
CREATE INDEX IF NOT EXISTS idx_raw_mentions_collected_at ON raw_mentions(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_mentions_topic ON raw_mentions(topic);

-- 2. Normalize edilmiş konular (birleştirilmiş ve deduplicate)
CREATE TABLE IF NOT EXISTS normalized_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(500) UNIQUE NOT NULL,  -- Normalize edilmiş konu adı
    category VARCHAR(100),                         -- AI tarafından atanan kategori
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    total_mentions INTEGER DEFAULT 0,
    sources TEXT[] DEFAULT '{}',                    -- Bu konuyu raporlayan kaynaklar
    country VARCHAR(10)
);

CREATE INDEX IF NOT EXISTS idx_normalized_topics_category ON normalized_topics(category);
CREATE INDEX IF NOT EXISTS idx_normalized_topics_last_seen ON normalized_topics(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_topics_canonical ON normalized_topics(canonical_name);

-- 3. Trend skorları (CTS hesaplaması)
CREATE TABLE IF NOT EXISTS trend_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES normalized_topics(id),
    topic_name VARCHAR(500) NOT NULL,
    category VARCHAR(100),
    cts_score DECIMAL(5,2) DEFAULT 0,        -- Composite Trend Score (0-100)
    platform_coverage DECIMAL(3,2) DEFAULT 0, -- Platform kapsamı (0-1)
    velocity DECIMAL(10,4) DEFAULT 0,         -- Büyüme hızı
    volume DECIMAL(5,2) DEFAULT 0,            -- Normalize edilmiş hacim
    recency DECIMAL(3,2) DEFAULT 0,           -- Tazelik skoru (0-1)
    is_burst BOOLEAN DEFAULT FALSE,            -- Patlama tespiti
    source_breakdown JSONB DEFAULT '{}',       -- Kaynak bazlı detay
    scored_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trend_scores_cts ON trend_scores(cts_score DESC);
CREATE INDEX IF NOT EXISTS idx_trend_scores_scored_at ON trend_scores(scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_trend_scores_category ON trend_scores(category);
CREATE INDEX IF NOT EXISTS idx_trend_scores_burst ON trend_scores(is_burst) WHERE is_burst = TRUE;

-- 4. API key yönetimi (Faz 3 — gelir geldiğinde)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    tier VARCHAR(20) DEFAULT 'free',         -- free, pro, business, enterprise
    daily_limit INTEGER DEFAULT 100,
    requests_today INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

-- 5. Veri temizlik politikası (90 günden eski raw data'yı sil)
-- Bu fonksiyonu Supabase cron job olarak ayarla (pg_cron extension)
CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- 90 günden eski raw mention'ları sil
    DELETE FROM raw_mentions
    WHERE collected_at < NOW() - INTERVAL '90 days';

    -- 30 günden eski trend skorlarını sil (güncel olanları tut)
    DELETE FROM trend_scores
    WHERE scored_at < NOW() - INTERVAL '30 days';

    RAISE NOTICE 'Eski veriler temizlendi';
END;
$$ LANGUAGE plpgsql;

-- Row Level Security (opsiyonel — API key bazlı erişim için)
-- ALTER TABLE trend_scores ENABLE ROW LEVEL SECURITY;
