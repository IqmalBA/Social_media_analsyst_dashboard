"""
PROSES LAPORAN DARI LINK - dijalankan GitHub Actions saat Apps Script mengirim
link laporan Emplifi baru.

Membaca dari variabel lingkungan: LAPORAN_LINK, LAPORAN_TANGGAL, LAPORAN_ID.
Mengunduh Excel (dengan pemeriksaan keamanan yang sama seperti skrip Gmail),
lalu menjalankan ETL. Kegagalan dicatat agar tampil di dashboard.
"""

import os
import re
import subprocess
import sys
from io import BytesIO
from urllib.parse import urlparse
from zipfile import ZipFile, is_zipfile

import requests

from log_status import log_failure
from db_sqlite import now
from settings import BASE

REPORT_HOSTS = "sbks-reporting.svc.emplifi.io"
MAX_SIZE = 25 * 1024 * 1024
TEST_HOSTS = os.environ.get("EMPLIFI_UJI_HOST")          # hanya untuk pengujian lokal


def fail(message, since=None):
    print("GAGAL:", message)
    log_failure(message, since=since)
    sys.exit(1)


def safe_link(url):
    a = urlparse(url)
    if a.scheme == "https" and a.hostname == REPORT_HOSTS:
        return True
    return bool(TEST_HOSTS) and a.hostname == TEST_HOSTS and a.scheme in ("http", "https")


def download(url):
    with requests.get(url, timeout=(15, 120), stream=True) as r:
        if r.status_code != 200:
            raise ValueError(f"Download gagal (HTTP {r.status_code}). Link mungkin sudah kedaluwarsa.")
        if not all(safe_link(x.url) for x in [*r.history, r]):
            raise ValueError("Download dialihkan ke alamat yang tidak aman.")
        body, size = [], 0
        for truncate in r.iter_content(65536):
            size += len(truncate)
            if size > MAX_SIZE:
                raise ValueError("File melebihi 25 MB.")
            body.append(truncate)
    data = b"".join(body)
    if not is_zipfile(BytesIO(data)):
        raise ValueError("Hasil download bukan file Excel (XLSX).")
    with ZipFile(BytesIO(data)) as z:
        if "xl/workbook.xml" not in z.namelist():
            raise ValueError("Workbook Excel tidak valid.")
    return data


def main():
    link = os.environ.get("LAPORAN_LINK", "").strip()
    date_value = os.environ.get("LAPORAN_TANGGAL", "").strip()
    message_id = os.environ.get("LAPORAN_ID", "").strip()

    if not link or not date_value or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", message_id):
        fail("Data laporan dari Gmail tidak lengkap.")
    if not safe_link(link):
        fail("Link laporan bukan dari domain Emplifi. Diabaikan demi keamanan.")

    print("Mengunduh laporan", message_id, "...")
    try:
        data = download(link)
    except (requests.RequestException, ValueError) as error:
        fail(f"Laporan Emplifi tidak bisa diunduh: {error}")

    folder = BASE / "input" / "gmail_downloads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Emplifi_{message_id}.xlsx"
    path.write_bytes(data)
    print(f"Tersimpan: {path.name} ({len(data):,} byte)")

    etl_start = now()
    result = subprocess.run([sys.executable, str(BASE / "etl_emplifi.py"),
                            str(path), date_value])
    if result.returncode != 0:
        fail("Laporan terunduh, tetapi ETL gagal memprosesnya. Lihat GitHub Actions.",
              since=etl_start)
    print("Laporan selesai diproses.")


if __name__ == "__main__":
    main()
