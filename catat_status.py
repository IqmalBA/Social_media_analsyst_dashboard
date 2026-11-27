"""
Mencatat kegagalan proses online (GitHub Actions) agar tampil di dashboard.

  python catat_status.py gagal "pesan"
      -> mencatat kegagalan, KECUALI ETL sudah mencatat sendiri sejak proses dimulai.
"""

import sys

from db_sqlite import buka, sekarang, siapkan
from konfigurasi import lokasi_database


def catat_gagal(pesan, sejak=None):
    """
    Mencatat kegagalan agar tampil di dashboard.
    sejak: waktu mulai proses; jika ETL sudah mencatat kegagalannya sendiri
    setelah waktu itu, tidak dicatat lagi (mencegah catatan ganda).
    """
    conn = buka(lokasi_database())
    try:
        siapkan(conn)
        if sejak and conn.execute(
                "SELECT 1 FROM import_log WHERE status = 'failed' AND created_at >= ? LIMIT 1;",
                (sejak,)).fetchone():
            return
        conn.execute("INSERT INTO import_log (status, pesan, created_at) "
                     "VALUES ('failed', ?, ?);", (pesan[:500], sekarang()))
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "gagal":
        catat_gagal(sys.argv[2])
    else:
        raise SystemExit(__doc__)
