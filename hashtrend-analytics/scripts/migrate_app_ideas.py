"""
Migration runner: app_ideas + viral_ideas tablolarını oluştur.

GHA workflow_dispatch ile manuel tetiklenir. Browser'a giremeyen kullanıcı
için Supabase SQL Editor alternatifi. Migration idempotent:
CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.

Env: SUPABASE_DB_URL (postgres connection string — yeni GHA secret)
Yoksa Service role REST API ile execute_sql RPC denenir (varsa).
"""

import os
import sys
from pathlib import Path
from loguru import logger

MIGRATION_FILE = "migrations/2026-05-05-app-ideas-viral-ideas.sql"


def run_with_psycopg(sql: str, db_url: str):
    """Direct postgres bağlantısı ile DDL çalıştır."""
    import psycopg2
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        # Migration multiple statements içeriyor; tek seferde execute
        cur.execute(sql)
    conn.close()
    logger.info("Migration başarıyla çalıştırıldı (psycopg2)")


def run_with_rpc(sql: str):
    """Supabase Python client ile — exec_sql RPC tanımlı değilse fail eder."""
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    client = create_client(url, key)
    # Statements'ı split + her birini ayrı RPC olarak çalıştır
    # NOT: Supabase'de generic exec_sql RPC yok by default; bu fallback genelde fail.
    raise RuntimeError(
        "REST RPC ile arbitrary DDL çalıştırılamıyor. "
        "SUPABASE_DB_URL secret'ı eklenmeli (postgres connection string)."
    )


def main():
    sql_path = Path(__file__).resolve().parents[1] / MIGRATION_FILE
    if not sql_path.exists():
        logger.error(f"Migration dosyası bulunamadı: {sql_path}")
        sys.exit(1)

    sql = sql_path.read_text(encoding="utf-8")
    logger.info(f"Migration okundu: {sql_path.name} ({len(sql)} char)")

    db_url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if db_url:
        run_with_psycopg(sql, db_url)
    else:
        # Fallback denemesi (büyük olasılıkla fail)
        run_with_rpc(sql)

    logger.info("✓ Migration tamamlandı.")


if __name__ == "__main__":
    main()
