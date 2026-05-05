-- Migration: Mat view'ı 24 saat filter ile yeniden yarat + refresh function
-- Tarih: 2026-05-05
--
-- ASIL SORUN ANALİZİ
-- ───────────────────
-- Pipeline her run'da NormalizedTopic.id için yeni UUID üretiyor (uuid.uuid4)
-- → trend_scores'a eski + yeni topic'ler birikmiş. Mat view DISTINCT ON
--   (topic_id) ORDER BY scored_at DESC → her UUID için tek satır.
-- → 28 gün önce skorlanan eski Reddit/HN topic'leri hâlâ mat view'da.
-- → Yeni TR/Bluesky/Webrazzi topic'leri pipeline son run'larında toplandı
--   ama eski Reddit topic'leri yüksek cts_score ile top'u tutuyor.
--
-- ÇÖZÜM: Mat view'ı 24h pencere ile yeniden yarat. Eski topic'ler düşer,
--        sadece son pipeline run'larındaki taze trend'ler kalır.

-- ─── 1. Eski mat view'ı düşür + 24h filter ile yeniden yarat ─────────
DROP MATERIALIZED VIEW IF EXISTS latest_trend_scores CASCADE;

CREATE MATERIALIZED VIEW latest_trend_scores AS
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
    ts.country,
    ts.summary,
    ts.edu_score,
    ts.edu_category,
    ts.edu_reason,
    ts.course_idea,
    ts.scored_at
FROM trend_scores ts
WHERE ts.scored_at > NOW() - INTERVAL '24 hours'
ORDER BY topic_id, scored_at DESC;

-- ─── 2. Indexleri yeniden oluştur (DROP CASCADE'den sonra) ──────────
CREATE UNIQUE INDEX idx_latest_scores_topic
    ON latest_trend_scores (topic_id);
CREATE INDEX idx_latest_scores_cts
    ON latest_trend_scores (cts_score DESC);
CREATE INDEX idx_latest_scores_recent
    ON latest_trend_scores (scored_at DESC);
CREATE INDEX idx_latest_scores_country
    ON latest_trend_scores (country, cts_score DESC);
CREATE INDEX idx_latest_scores_category
    ON latest_trend_scores (category, cts_score DESC);
CREATE INDEX idx_latest_scores_burst
    ON latest_trend_scores (cts_score DESC) WHERE is_burst = TRUE;

-- ─── 3. Refresh function (PR #34 — idempotent, üzerine yazar) ───────
CREATE OR REPLACE FUNCTION public.refresh_latest_trend_scores()
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET statement_timeout = '300000'  -- 5 dk
AS $$
DECLARE
    start_ts TIMESTAMPTZ := clock_timestamp();
    duration_s NUMERIC;
    row_count INT;
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY latest_trend_scores;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'CONCURRENTLY fail (%)— lock''lı refresh', SQLERRM;
            REFRESH MATERIALIZED VIEW latest_trend_scores;
    END;

    SELECT COUNT(*) INTO row_count FROM latest_trend_scores;
    duration_s := EXTRACT(EPOCH FROM (clock_timestamp() - start_ts));
    RETURN json_build_object('ok', true, 'duration_s', duration_s, 'rows', row_count);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.refresh_latest_trend_scores() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.refresh_latest_trend_scores() TO service_role;

-- ─── 4. Source_count backfill (mevcut satırlar için) ─────────────────
-- Insert'te 0 ile yazılan eski satırları source_breakdown len'i ile doldur.
UPDATE trend_scores
SET source_count = (
    SELECT COUNT(*) FROM jsonb_object_keys(source_breakdown)
)
WHERE source_count = 0
  AND source_breakdown IS NOT NULL
  AND source_breakdown::text != '{}'
  AND scored_at > NOW() - INTERVAL '7 days';  -- son hafta yeter

-- ─── 5. İlk REFRESH (mat view yeni 24h tanımıyla doldur) ────────────
SELECT public.refresh_latest_trend_scores();

-- ─── 6. Doğrulama sorgusu — mat view canlı mı? ──────────────────────
SELECT
    'latest_trend_scores' AS view_name,
    COUNT(*) AS row_count,
    MIN(scored_at) AS oldest,
    MAX(scored_at) AS newest,
    NOW() - MAX(scored_at) AS staleness,
    COUNT(DISTINCT country) AS country_count,
    COUNT(*) FILTER (WHERE country = 'TR') AS tr_topics,
    COUNT(*) FILTER (WHERE source_breakdown ? 'eksisozluk') AS eksi_topics,
    COUNT(*) FILTER (WHERE source_breakdown ? 'webrazzi') AS webrazzi_topics,
    COUNT(*) FILTER (WHERE source_breakdown ? 'tr_news_rss') AS tr_news_topics,
    COUNT(*) FILTER (WHERE source_breakdown ? 'bluesky') AS bluesky_topics,
    AVG(source_count)::NUMERIC(10,2) AS avg_source_count
FROM latest_trend_scores;
