-- Migration: app_ideas + viral_ideas tabloları
-- Tarih: 2026-05-05
-- Amaç: HashTrend'i Exploding Topics'ten ayıran iki AI katmanı:
--   1. App Idea Generator — trend → uygulama fikri + retention skoru
--   2. Viral Content Generator — trend → influencer video önerisi + viral skoru
-- Hem global hem country bazlı (TR + EN_US + GLOBAL).

-- ─── 1. APP IDEAS ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_ideas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    -- Country/market context — 'GLOBAL' veya ISO alpha-2
    country VARCHAR(10) NOT NULL DEFAULT 'GLOBAL',
    -- Idea content (LLM çıktısı)
    name VARCHAR(200) NOT NULL,
    tagline VARCHAR(300),
    problem TEXT,
    solution TEXT,
    tech_stack JSONB DEFAULT '[]',  -- ["FastAPI","Supabase",...]
    mvp_days INTEGER DEFAULT 30 CHECK (mvp_days >= 1 AND mvp_days <= 365),
    -- ML-aligned scoring (0-1)
    retention_score DECIMAL(3,2) DEFAULT 0.5 CHECK (retention_score >= 0 AND retention_score <= 1),
    feasibility_score DECIMAL(3,2) DEFAULT 0.5 CHECK (feasibility_score >= 0 AND feasibility_score <= 1),
    -- Pazar context
    market_size_estimate TEXT,
    competitors JSONB DEFAULT '[]',  -- ["TradingView","Investing.com"]
    differentiation TEXT,
    -- Confidence flag (LLM verisinin kalitesi yetersizse)
    confidence VARCHAR(20) DEFAULT 'medium',  -- high | medium | low
    -- Generation metadata
    llm_model VARCHAR(50) DEFAULT 'gpt-oss:120b',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (topic_id, country, name)
);

CREATE INDEX IF NOT EXISTS idx_app_ideas_topic ON app_ideas (topic_id);
CREATE INDEX IF NOT EXISTS idx_app_ideas_country ON app_ideas (country, retention_score DESC);
CREATE INDEX IF NOT EXISTS idx_app_ideas_recent ON app_ideas (generated_at DESC);

-- ─── 2. VIRAL CONTENT IDEAS (Influencer Fabrikası) ────────────
CREATE TABLE IF NOT EXISTS viral_ideas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    country VARCHAR(10) NOT NULL DEFAULT 'GLOBAL',
    platform VARCHAR(20) NOT NULL DEFAULT 'tiktok',  -- tiktok | instagram | youtube_shorts
    -- Video idea content
    hook VARCHAR(500),  -- "Bu üç hatayı yapan herkes parasını kaybediyor 👇"
    format VARCHAR(50),  -- "60s hook+payoff", "3-part series", "duet/stitch"
    description TEXT,
    -- ML-aligned scoring
    viral_score DECIMAL(3,2) DEFAULT 0.5 CHECK (viral_score >= 0 AND viral_score <= 1),
    expected_engagement VARCHAR(50),  -- "10K-50K view"
    -- Production hints
    audio_suggestion TEXT,
    hashtags JSONB DEFAULT '[]',  -- ["#fed","#yatırım"]
    visual_style TEXT,  -- "fast-cut", "talking head", "screen recording"
    -- Confidence
    confidence VARCHAR(20) DEFAULT 'medium',
    llm_model VARCHAR(50) DEFAULT 'gpt-oss:120b',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (topic_id, country, platform, hook)
);

CREATE INDEX IF NOT EXISTS idx_viral_ideas_topic ON viral_ideas (topic_id);
CREATE INDEX IF NOT EXISTS idx_viral_ideas_country ON viral_ideas (country, platform, viral_score DESC);
CREATE INDEX IF NOT EXISTS idx_viral_ideas_recent ON viral_ideas (generated_at DESC);

-- ─── 3. Doğrulama ─────────────────────────────────────────────
SELECT
    'app_ideas' AS table_name, COUNT(*) AS row_count FROM app_ideas
UNION ALL
SELECT
    'viral_ideas' AS table_name, COUNT(*) AS row_count FROM viral_ideas;
