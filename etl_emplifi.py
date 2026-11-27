"""
ETL Emplifi Feed -> SQLite

Cara pakai (dipanggil otomatis oleh gmail_pilih_report.py):
    python etl_emplifi.py "file.xlsx" "Mon, 26 Oct 2026 07:54:51 +0000"

Proteksi (sama dengan versi PostgreSQL):
  1. File yang sama (hash) tidak diproses dua kali.
  2. Content ID kosong/duplikat dalam satu file ditolak.
  3. Konten lama tanpa tanggal sumber tidak ditimpa (perlu verifikasi).
  4. Data hanya ditimpa oleh laporan dengan tanggal email LEBIH BARU.
  5. Hasil insert/update/dilewati dicocokkan dengan perkiraan.
  6. Label harus berformat "Pillar: X" atau "Tower - Campaign - Sub Campaign".
  7. Semua atau tidak sama sekali (rollback jika gagal).
  8. Satu ETL berjalan dalam satu waktu (BEGIN IMMEDIATE).
Baru: kegagalan dicatat di import_log (status 'failed') agar tampil di dashboard.

Exit code: 0 = sukses / file sudah pernah diproses, 1 = gagal.
"""

import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

from ambil_hyperlink import simpan_link
from db_sqlite import (KOLOM_TEKS_KONTEN, buka, ke_utc_teks, kolom_teks_konten, pangkas,
                       rapatkan, sekarang, siapkan)
from konfigurasi import lokasi_database
from validasi_feed import validasi_feed

KOLOM_ANGKA = {               # kolom database : kolom Excel
    "total_interactions": "Total interactions",
    "total_reach": "Total reach", "paid_reach": "Paid reach",
    "organic_reach": "Organic reach", "total_impressions": "Total impressions",
    "paid_impressions": "Paid impressions", "organic_impressions": "Organic impressions",
    "engagements": "Engagements", "link_clicks": "Link clicks",
    "post_clicks": "Post clicks", "video_views": "Video view count",
}
KOLOM_RASIO = {
    "impressions_engagement_rate": "Impressions engagement rate",
    "reach_engagement_rate": "Reach engagement rate",
}
KOLOM_TEKS = {
    "profile_name": "Profile name", "platform": "Platform",
    "content_type": "Content type", "media_type": "Media type", "labels": "Labels",
}


# =========================
# UTILITAS
# =========================

def kosong(nilai):
    if nilai is None:
        return True
    try:
        return bool(pd.isna(nilai))
    except (TypeError, ValueError):
        return False


def nilai_json(nilai):
    if kosong(nilai):
        return None
    if isinstance(nilai, (pd.Timestamp, datetime, date)):
        return nilai.isoformat()
    if hasattr(nilai, "item"):
        return nilai.item()
    return nilai


def ke_angka(nilai, kolom, bulat):
    if kosong(nilai) or (isinstance(nilai, str) and not nilai.strip()):
        return None
    try:
        angka = float(nilai)
    except (TypeError, ValueError):
        raise ValueError(f"Nilai '{nilai}' di kolom '{kolom}' bukan angka.")
    if math.isnan(angka):
        return None
    return int(round(angka)) if bulat else angka


def ke_teks(nilai):
    return None if kosong(nilai) else str(nilai)


def ke_waktu_posting(nilai):
    """Waktu posting Emplifi = waktu lokal WIB, disimpan tanpa zona."""
    if kosong(nilai):
        return None
    waktu = pd.Timestamp(nilai)
    if waktu.tzinfo is not None:
        waktu = waktu.tz_convert("Asia/Jakarta").tz_localize(None)
    return waktu.strftime("%Y-%m-%d %H:%M:%S")


def urai_label(teks):
    """
    [(urutan, label_raw, jenis, tower, campaign, sub, pillar)]
    - "Pillar: X"                          -> PILLAR
    - "Tower - Campaign - Sub Campaign"    -> TOWER_CAMPAIGN
    - label lain (mis. "Menu Musim Hujan") -> LAINNYA, disimpan apa adanya
    Label tidak pernah dibuang dan tidak menggagalkan laporan.
    """
    hasil = []
    if kosong(teks):
        return hasil
    for urutan, potongan in enumerate(str(teks).split(";"), start=1):
        label = potongan.strip()
        if not label:
            continue
        if label.lower().startswith("pillar:"):
            pillar = label.split(":", 1)[1].strip()
            if pillar:
                hasil.append((urutan, label, "PILLAR", None, None, None, pillar))
                continue
        else:
            bagian = [b.strip() for b in label.split(" - ")]
            if len(bagian) == 3 and all(bagian):
                hasil.append((urutan, label, "TOWER_CAMPAIGN", *bagian, None))
                continue
        hasil.append((urutan, label, "LAINNYA", None, None, None, None))
    return hasil


def per_potong(daftar, ukuran=800):
    for i in range(0, len(daftar), ukuran):
        yield daftar[i:i + ukuran]


# =========================
# 1. INPUT + VALIDASI
# =========================

if len(sys.argv) != 3:
    raise SystemExit('Cara pakai: python etl_emplifi.py '
                     '"input\\nama_file.xlsx" "Mon, 26 Oct 2026 07:54:51 +0000"')

file_path = Path(sys.argv[1])
file_name = file_path.name

try:
    waktu_email = parsedate_to_datetime(sys.argv[2])
    if waktu_email is None or waktu_email.tzinfo is None:
        raise ValueError("Tanggal laporan tidak memiliki timezone.")
except (TypeError, ValueError, OverflowError) as error:
    raise SystemExit(f"Tanggal laporan Gmail tidak valid: {error}")

source_email_at = ke_utc_teks(waktu_email)
print("Tanggal laporan (UTC):", source_email_at)

print("\nMemulai validasi file Excel...")
try:
    validasi_feed(file_path)
except (ValueError, OSError) as error:
    raise SystemExit(f"Import dibatalkan: {error}")

hasher = hashlib.sha256()
with open(file_path, "rb") as file:
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
        hasher.update(chunk)
file_hash = hasher.hexdigest()
print("File hash:", file_hash)

df = pd.read_excel(file_path, sheet_name="Content", dtype={"Content ID": "string"})
print("Jumlah baris:", len(df), "| Jumlah kolom:", len(df.columns))
if df.empty:
    raise SystemExit("Sheet Content kosong. Import dibatalkan.")


# =========================
# 2. DATABASE
# =========================

lokasi = lokasi_database()
conn = buka(lokasi)
siapkan(conn)
print("Database:", lokasi)

sudah = conn.execute(
    "SELECT 1 FROM import_log WHERE file_hash = ? AND status = 'success' LIMIT 1;",
    (file_hash,)).fetchone()
if sudah:
    print("File ini SUDAH pernah diproses. Program tidak melakukan import ulang.")
    conn.close()
    sys.exit(0)

ringkasan = {}

try:
    conn.execute("BEGIN IMMEDIATE;")      # hanya satu ETL yang boleh menulis
    waktu_proses = sekarang()

    # ---------- 3. RAW ----------
    baris_raw = []
    for posisi, (_, baris) in enumerate(df.iterrows()):
        data = {str(k): nilai_json(v) for k, v in baris.items()}
        baris_raw.append((file_name, "Content", posisi + 2,
                          json.dumps(data, ensure_ascii=False, default=str), waktu_proses))
    conn.executemany("""
        INSERT INTO emplifi_raw (source_file, sheet_name, row_number, raw_data, imported_at)
        VALUES (?, ?, ?, ?, ?);
    """, baris_raw)
    print("Total RAW disimpan:", len(baris_raw))

    jumlah_link = simpan_link(conn, file_path, file_name)
    print("Link postingan tersimpan:", jumlah_link)

    # ---------- 4. SIAPKAN BARIS KONTEN ----------
    rekaman = []
    for _, baris in df.iterrows():
        cid = ke_teks(baris.get("Content ID"))
        cid = cid.strip() if cid else None
        r = {"content_id": cid, "date": ke_waktu_posting(baris.get("Date"))}
        for kolom, asal in KOLOM_TEKS.items():
            r[kolom] = ke_teks(baris.get(asal))
        for kolom, asal in KOLOM_ANGKA.items():
            r[kolom] = ke_angka(baris.get(asal), asal, bulat=True)
        for kolom, asal in KOLOM_RASIO.items():
            r[kolom] = ke_angka(baris.get(asal), asal, bulat=False)
        r.update(kolom_teks_konten(baris.get))      # caption, sentimen, kolaborator
        rekaman.append(r)

    ids = [r["content_id"] for r in rekaman]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Content ID kosong atau duplikat. UPSERT dibatalkan.")
    print("Validasi Content ID berhasil.")

    # Label divalidasi SEBELUM data diubah.
    label_per_konten = {r["content_id"]: urai_label(r["labels"]) for r in rekaman}

    # ---------- 5. KLASIFIKASI (proteksi tanggal email) ----------
    ada = {}
    for potong in per_potong(ids):
        tanda = ",".join("?" * len(potong))
        for cid, pk, at in conn.execute(
                f"SELECT content_id, content_pk, source_email_at FROM emplifi_content "
                f"WHERE content_id IN ({tanda});", potong):
            ada[cid] = (pk, at)

    tanpa_tanggal = [c for c, (_, at) in ada.items() if at is None]
    if tanpa_tanggal:
        raise ValueError(f"UPSERT dihentikan: {len(tanpa_tanggal)} Content ID historis "
                         "tanpa tanggal sumber. Perlu verifikasi terlebih dahulu.")

    baru, perbarui, sama, lama = [], [], [], []
    for r in rekaman:
        if r["content_id"] not in ada:
            baru.append(r)
        else:
            at = ada[r["content_id"]][1]
            (perbarui if at < source_email_at else sama if at == source_email_at else lama).append(r)

    # ---------- 6. INSERT / UPDATE ----------
    kolom_isi = (["content_id", "date"] + list(KOLOM_TEKS) + list(KOLOM_ANGKA)
                 + list(KOLOM_RASIO) + list(KOLOM_TEKS_KONTEN))
    nilai = lambda r: [r[k] for k in kolom_isi] + [file_name, source_email_at, waktu_proses]

    cur = conn.executemany(f"""
        INSERT INTO emplifi_content ({", ".join(kolom_isi)}, source_file, source_email_at, imported_at)
        VALUES ({", ".join("?" * (len(kolom_isi) + 3))});
    """, [nilai(r) for r in baru])
    jumlah_insert = cur.rowcount if baru else 0

    set_kolom = ", ".join(f"{k} = ?" for k in kolom_isi[1:])
    jumlah_update = 0
    for r in perbarui:
        cur = conn.execute(f"""
            UPDATE emplifi_content
            SET {set_kolom}, source_file = ?, source_email_at = ?, imported_at = ?
            WHERE content_id = ? AND source_email_at < ?;
        """, nilai(r)[1:] + [r["content_id"], source_email_at])
        jumlah_update += cur.rowcount

    print("\n=== HASIL UPSERT ===")
    print("Total baris Excel      :", len(df))
    print("CONTENT baru (insert)  :", jumlah_insert)
    print("CONTENT diperbarui     :", jumlah_update)
    print("Dilewati (versi sama)  :", len(sama))
    print("Dilewati (versi lama)  :", len(lama))
    if jumlah_insert != len(baru) or jumlah_update != len(perbarui):
        raise ValueError(f"Hasil UPSERT tidak sesuai perkiraan (insert {jumlah_insert}/"
                         f"{len(baru)}, update {jumlah_update}/{len(perbarui)}).")
    print("Validasi hasil UPSERT berhasil!")

    # ---------- 7. LABEL (hanya konten yang berubah) ----------
    berubah = [r["content_id"] for r in baru + perbarui]
    pk = {}
    for potong in per_potong(berubah):
        tanda = ",".join("?" * len(potong))
        pk.update(conn.execute(f"SELECT content_id, content_pk FROM emplifi_content "
                               f"WHERE content_id IN ({tanda});", potong).fetchall())
    conn.executemany("DELETE FROM emplifi_content_label WHERE content_pk = ?;",
                     [(pk[c],) for c in berubah])
    baris_label = [(pk[c], c, *lbl, "MAPPED", waktu_proses)
                   for c in berubah for lbl in label_per_konten[c]]
    conn.executemany("""
        INSERT INTO emplifi_content_label (content_pk, content_id, label_order, label_raw,
            label_type, tower, campaign, sub_campaign, pillar, mapping_status, mapped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, baris_label)
    print("Mapping label disimpan:", len(baris_label))

    # ---------- 8. PANGKAS DATA MENTAH VERSI LAMA ----------
    print("Data mentah versi lama dipangkas:", pangkas(conn), "baris")

    # ---------- 9. LOG + COMMIT ----------
    conn.execute("""
        INSERT INTO import_log (file_name, file_hash, row_count, status, pesan, source_email_at,
            jumlah_insert, jumlah_update, jumlah_lewati, created_at)
        VALUES (?, ?, ?, 'success', NULL, ?, ?, ?, ?, ?);
    """, (file_name, file_hash, len(df), source_email_at, jumlah_insert, jumlah_update,
          len(sama) + len(lama), waktu_proses))
    conn.execute("COMMIT;")
    rapatkan(conn)
    print("\nPROSES AUTOMATION SELESAI!")

except Exception as error:
    if conn.in_transaction:
        conn.execute("ROLLBACK;")
    print("\nProses gagal. Semua perubahan dibatalkan.")
    print("Detail error:", error)
    try:
        conn.execute("""
            INSERT INTO import_log (file_name, file_hash, row_count, status, pesan,
                source_email_at, created_at)
            VALUES (?, ?, ?, 'failed', ?, ?, ?);
        """, (file_name, file_hash, len(df), str(error)[:500], source_email_at, sekarang()))
    except Exception:
        pass
    conn.close()
    sys.exit(1)

conn.close()
