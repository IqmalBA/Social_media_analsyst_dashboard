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

from catat_status import catat_gagal
from db_sqlite import sekarang
from konfigurasi import BASE

HOST_LAPORAN = "sbks-reporting.svc.emplifi.io"
BATAS_UKURAN = 25 * 1024 * 1024
HOST_UJI = os.environ.get("EMPLIFI_UJI_HOST")          # hanya untuk pengujian lokal


def gagal(pesan, sejak=None):
    print("GAGAL:", pesan)
    catat_gagal(pesan, sejak=sejak)
    sys.exit(1)


def link_aman(url):
    a = urlparse(url)
    if a.scheme == "https" and a.hostname == HOST_LAPORAN:
        return True
    return bool(HOST_UJI) and a.hostname == HOST_UJI and a.scheme in ("http", "https")


def unduh(url):
    with requests.get(url, timeout=(15, 120), stream=True) as r:
        if r.status_code != 200:
            raise ValueError(f"Download gagal (HTTP {r.status_code}). Link mungkin sudah kedaluwarsa.")
        if not all(link_aman(x.url) for x in [*r.history, r]):
            raise ValueError("Download dialihkan ke alamat yang tidak aman.")
        isi, ukuran = [], 0
        for potong in r.iter_content(65536):
            ukuran += len(potong)
            if ukuran > BATAS_UKURAN:
                raise ValueError("File melebihi 25 MB.")
            isi.append(potong)
    data = b"".join(isi)
    if not is_zipfile(BytesIO(data)):
        raise ValueError("Hasil download bukan file Excel (XLSX).")
    with ZipFile(BytesIO(data)) as z:
        if "xl/workbook.xml" not in z.namelist():
            raise ValueError("Workbook Excel tidak valid.")
    return data


def main():
    link = os.environ.get("LAPORAN_LINK", "").strip()
    tanggal = os.environ.get("LAPORAN_TANGGAL", "").strip()
    id_pesan = os.environ.get("LAPORAN_ID", "").strip()

    if not link or not tanggal or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", id_pesan):
        gagal("Data laporan dari Gmail tidak lengkap.")
    if not link_aman(link):
        gagal("Link laporan bukan dari domain Emplifi. Diabaikan demi keamanan.")

    print("Mengunduh laporan", id_pesan, "...")
    try:
        data = unduh(link)
    except (requests.RequestException, ValueError) as error:
        gagal(f"Laporan Emplifi tidak bisa diunduh: {error}")

    folder = BASE / "input" / "gmail_downloads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Emplifi_{id_pesan}.xlsx"
    path.write_bytes(data)
    print(f"Tersimpan: {path.name} ({len(data):,} byte)")

    mulai_etl = sekarang()
    hasil = subprocess.run([sys.executable, str(BASE / "etl_emplifi.py"),
                            str(path), tanggal])
    if hasil.returncode != 0:
        gagal("Laporan terunduh, tetapi ETL gagal memprosesnya. Lihat GitHub Actions.",
              sejak=mulai_etl)
    print("Laporan selesai diproses.")


if __name__ == "__main__":
    main()
