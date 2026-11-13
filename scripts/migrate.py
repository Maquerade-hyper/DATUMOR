from pathlib import Path
import os
import re
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATIONS = ROOT / "migrations" / "sql"

def main():
    required = ("DATUMOR_DB_USER", "DATUMOR_DB_PASSWORD", "DATUMOR_DB_NAME")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("Missing database environment variables: " + ", ".join(missing))

    conn = psycopg.connect(
        host=os.getenv("DATUMOR_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DATUMOR_DB_PORT", "5432")),
        dbname=os.environ["DATUMOR_DB_NAME"],
        user=os.environ["DATUMOR_DB_USER"],
        password=os.environ["DATUMOR_DB_PASSWORD"],
        connect_timeout=15,
    )

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS datumor_schema_migrations (
                    migration_name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()

        files = sorted(MIGRATIONS.glob("*.sql"))
        if not files:
            raise RuntimeError(f"No SQL migrations found in {MIGRATIONS}")

        for path in files:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM datumor_schema_migrations WHERE migration_name = %s",
                    (path.name,),
                )
                if cur.fetchone():
                    print(f"SKIP {path.name} (already applied)")
                    continue

            sql = path.read_text(encoding="utf-8-sig")
            sql = re.sub(r"(?im)^\s*(BEGIN|COMMIT|END)\s*;\s*$", "", sql)

            try:
                with conn.cursor() as cur:
                    cur.execute(sql, prepare=False)
                    cur.execute(
                        "INSERT INTO datumor_schema_migrations (migration_name) VALUES (%s)",
                        (path.name,),
                    )
                conn.commit()
                print(f"APPLIED {path.name}")
            except Exception:
                conn.rollback()
                raise

        print(f"Migration check complete: {len(files)} SQL files discovered.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
