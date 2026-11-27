"""
Mencatat kegagalan proses online (GitHub Actions) agar tampil di dashboard.

  python log_status.py fail "message"
      -> mencatat kegagalan, KECUALI ETL sudah mencatat sendiri sejak proses dimulai.
"""

import sys

from db_sqlite import open_db, now, prepare
from settings import database_path


def log_failure(message, since=None):
    """
    Mencatat kegagalan agar tampil di dashboard.
    sejak: waktu mulai proses; jika ETL sudah mencatat kegagalannya sendiri
    setelah waktu itu, tidak dicatat lagi (mencegah catatan ganda).
    """
    conn = open_db(database_path())
    try:
        prepare(conn)
        if since and conn.execute(
                "SELECT 1 FROM import_log WHERE status = 'failed' AND created_at >= ? LIMIT 1;",
                (since,)).fetchone():
            return
        conn.execute("INSERT INTO import_log (status, pesan, created_at) "
                     "VALUES ('failed', ?, ?);", (message[:500], now()))
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fail":
        log_failure(sys.argv[2])
    else:
        raise SystemExit(__doc__)
