"""
DB maintenance: TR olarak işaretli ama TR-spesifik kaynak içermeyen
trend_scores satırlarını temizle. Counter normalizer öncesi (PR #30 öncesi)
random country atamalarının kalıntısı.

GHA workflow_dispatch ile manuel tetiklenir.
Env: SUPABASE_URL, SUPABASE_KEY (service role)
"""

import os
import sys
from supabase import create_client

TR_SPECIFIC_SOURCES = {
    "eksisozluk", "webrazzi", "gdelt", "tr_news_rss", "trends24", "bluesky",
}


def main():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    db = create_client(url, key)

    # 1. country=TR olan tüm trend_scores'i sayfalı çek
    print("Fetching country=TR snapshots...")
    page_size = 1000
    offset = 0
    all_rows = []
    while True:
        resp = (
            db.table("trend_scores")
            .select("id,source_breakdown")
            .eq("country", "TR")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        if offset > 100_000:  # safety
            print(f"WARNING: stopped at {offset} rows")
            break
    print(f"Fetched {len(all_rows)} country=TR rows")

    # 2. TR-spesifik kaynak içermeyen ID'leri bul
    orphan_ids = []
    for r in all_rows:
        sb = r.get("source_breakdown") or {}
        if not isinstance(sb, dict):
            continue
        sources_present = set(sb.keys())
        if not (sources_present & TR_SPECIFIC_SOURCES):
            orphan_ids.append(r["id"])
    print(f"Orphan TR snapshots (random country atanmış, gerçek TR kaynak yok): {len(orphan_ids)}")

    if not orphan_ids:
        print("Hiç orphan yok, temizlik gereksiz.")
    else:
        # 3. Batch DELETE — id'leri 100'lük chunk'larla
        deleted = 0
        for i in range(0, len(orphan_ids), 100):
            chunk = orphan_ids[i:i + 100]
            try:
                resp = (
                    db.table("trend_scores")
                    .delete()
                    .in_("id", chunk)
                    .execute()
                )
                deleted += len(resp.data) if resp.data else 0
            except Exception as e:
                print(f"DELETE batch [{i}:{i+100}] hatası: {e}")
        print(f"Silinen orphan TR snapshot: {deleted}/{len(orphan_ids)}")

    # 4. Mat view refresh (cleanup'ın UI'ya yansıması için)
    print("Refreshing mat view...")
    try:
        result = db.rpc("refresh_latest_trend_scores").execute()
        print(f"Refresh sonucu: {result.data}")
    except Exception as e:
        print(f"Refresh hatası: {e}")
        sys.exit(1)

    print("✓ Cleanup tamamlandı.")


if __name__ == "__main__":
    main()
