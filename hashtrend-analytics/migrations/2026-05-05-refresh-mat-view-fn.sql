-- Migration: Mat view manuel REFRESH function + ilk yenileme
-- Tarih: 2026-05-05
-- Sorun: Pipeline'da hiç REFRESH MATERIALIZED VIEW çağrısı yoktu.
--        latest_trend_scores 28 gün eski kalmıştı (production'da).
-- Çözüm: SQL function (SECURITY DEFINER + statement_timeout=300s) →
--        Pipeline RPC ile her run sonrası tetikler.

-- ─── 1. Refresh function ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.refresh_latest_trend_scores()
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET statement_timeout = '300000'  -- 5 dk; PostgREST default 60s yetmiyor
AS $$
DECLARE
    start_ts TIMESTAMPTZ := clock_timestamp();
    duration_s NUMERIC;
BEGIN
    -- CONCURRENTLY: blok yok, query'ler bekletilmez. Unique index zorunlu
    -- (idx_latest_scores_topic — schema'da var).
    -- Fallback: CONCURRENTLY fail olursa lock'lı refresh (ilk kez ya da
    -- mat view boş/bozuk durumda gerekli olabilir).
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY latest_trend_scores;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'CONCURRENTLY fail (%)— lock''lı refresh', SQLERRM;
            REFRESH MATERIALIZED VIEW latest_trend_scores;
    END;

    duration_s := EXTRACT(EPOCH FROM (clock_timestamp() - start_ts));
    RETURN json_build_object('ok', true, 'duration_s', duration_s);
END;
$$;

-- Anonim kullanıcı (anon role) çağıramaz, sadece authenticated/service_role
REVOKE EXECUTE ON FUNCTION public.refresh_latest_trend_scores() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.refresh_latest_trend_scores() TO service_role;

-- ─── 2. İlk manuel REFRESH (28 gün bayat snapshot'ı düzelt) ─────────
SELECT public.refresh_latest_trend_scores();

-- ─── 3. (Opsiyonel) pg_cron ile her 15 dk'da bir auto-refresh ──────
-- Pipeline RPC zaten her run sonrası tetikler ama backup olarak burada
-- saatlik bir cron iyi olur. Eğer pg_cron extension yoksa bu kısmı atla.
-- DO $$ BEGIN
--     IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
--         PERFORM cron.unschedule('refresh-latest-trend-scores');
--         PERFORM cron.schedule(
--             'refresh-latest-trend-scores',
--             '*/30 * * * *',  -- her 30 dk
--             $sql$ SELECT public.refresh_latest_trend_scores(); $sql$
--         );
--     END IF;
-- END $$;

-- ─── 4. Doğrulama sorgusu ─────────────────────────────────────────
-- Refresh sonrası en son scored_at:
SELECT
    'latest_trend_scores' AS view_name,
    COUNT(*) AS row_count,
    MIN(scored_at) AS oldest,
    MAX(scored_at) AS newest,
    NOW() - MAX(scored_at) AS staleness
FROM latest_trend_scores;
