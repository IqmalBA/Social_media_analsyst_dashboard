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

from extract_hyperlinks import save_links
from db_sqlite import (CONTENT_TEXT_COLUMNS, open_db, to_utc_text, content_text_columns, prune,
                       tighten, now, prepare)
from settings import database_path
from validate_feed import validate_feed

NUMERIC_COLUMNS = {               # kolom database : kolom Excel
    "total_interactions": "Total interactions",
    "total_reach": "Total reach", "paid_reach": "Paid reach",
    "organic_reach": "Organic reach", "total_impressions": "Total impressions",
    "paid_impressions": "Paid impressions", "organic_impressions": "Organic impressions",
    "engagements": "Engagements", "link_clicks": "Link clicks",
    "post_clicks": "Post clicks", "video_views": "Video view count",
}
RATIO_COLUMNS = {
    "impressions_engagement_rate": "Impressions engagement rate",
    "reach_engagement_rate": "Reach engagement rate",
}
TEXT_COLUMNS = {
    "profile_name": "Profile name", "platform": "Platform",
    "content_type": "Content type", "media_type": "Media type", "labels": "Labels",
}


# =========================
# UTILITAS
# =========================

def is_empty(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def json_value(value):
    if is_empty(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def to_number(value, column, as_int):
    if is_empty(value) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Nilai '{value}' di kolom '{column}' bukan angka.")
    if math.isnan(number):
        return None
    return int(round(number)) if as_int else number


def to_text(value):
    return None if is_empty(value) else str(value)


def to_post_time(value):
    """Waktu posting Emplifi = waktu lokal WIB, disimpan tanpa zona."""
    if is_empty(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("Asia/Jakarta").tz_localize(None)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def parse_labels(text):
    """
    [(urutan, label_raw, jenis, tower, campaign, sub, pillar)]
    - "Pillar: X"                          -> PILLAR
    - "Tower - Campaign - Sub Campaign"    -> TOWER_CAMPAIGN
    - label lain (mis. "Menu Musim Hujan") -> LAINNYA, disimpan apa adanya
    Label tidak pernah dibuang dan tidak menggagalkan laporan.
    """
    result = []
    if is_empty(text):
        return result
    for order, pieces in enumerate(str(text).split(";"), start=1):
        label = pieces.strip()
        if not label:
            continue
        if label.lower().startswith("pillar:"):
            pillar = label.split(":", 1)[1].strip()
            if pillar:
                result.append((order, label, "PILLAR", None, None, None, pillar))
                continue
        else:
            section = [b.strip() for b in label.split(" - ")]
            if len(section) == 3 and all(section):
                result.append((order, label, "TOWER_CAMPAIGN", *section, None))
                continue
        result.append((order, label, "LAINNYA", None, None, None, None))
    return result


def per_chunk(items, size=800):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# =========================
# 1. INPUT + VALIDASI
# =========================

if len(sys.argv) != 3:
    raise SystemExit('Cara pakai: python etl_emplifi.py '
                     '"input\\nama_file.xlsx" "Mon, 26 Oct 2026 07:54:51 +0000"')

file_path = Path(sys.argv[1])
file_name = file_path.name

try:
    email_time = parsedate_to_datetime(sys.argv[2])
    if email_time is None or email_time.tzinfo is None:
        raise ValueError("Tanggal laporan tidak memiliki timezone.")
except (TypeError, ValueError, OverflowError) as error:
    raise SystemExit(f"Tanggal laporan Gmail tidak valid: {error}")

source_email_at = to_utc_text(email_time)
print("Tanggal laporan (UTC):", source_email_at)

print("\nMemulai validasi file Excel...")
try:
    validate_feed(file_path)
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

location = database_path()
conn = open_db(location)
prepare(conn)
print("Database:", location)

done = conn.execute(
    "SELECT 1 FROM import_log WHERE file_hash = ? AND status = 'success' LIMIT 1;",
    (file_hash,)).fetchone()
if done:
    print("File ini SUDAH pernah diproses. Program tidak melakukan import ulang.")
    conn.close()
    sys.exit(0)

summary = {}

try:
    conn.execute("BEGIN IMMEDIATE;")      # hanya satu ETL yang boleh menulis
    process_time = now()

    # ---------- 3. RAW ----------
    raw_rows = []
    for position, (_, row) in enumerate(df.iterrows()):
        data = {str(k): json_value(v) for k, v in row.items()}
        raw_rows.append((file_name, "Content", position + 2,
                          json.dumps(data, ensure_ascii=False, default=str), process_time))
    conn.executemany("""
        INSERT INTO emplifi_raw (source_file, sheet_name, row_number, raw_data, imported_at)
        VALUES (?, ?, ?, ?, ?);
    """, raw_rows)
    print("Total RAW disimpan:", len(raw_rows))

    link_count = save_links(conn, file_path, file_name)
    print("Link postingan tersimpan:", link_count)

    # ---------- 4. SIAPKAN BARIS KONTEN ----------
    records = []
    for _, row in df.iterrows():
        cid = to_text(row.get("Content ID"))
        cid = cid.strip() if cid else None
        r = {"content_id": cid, "date": to_post_time(row.get("Date"))}
        for column, origin in TEXT_COLUMNS.items():
            r[column] = to_text(row.get(origin))
        for column, origin in NUMERIC_COLUMNS.items():
            r[column] = to_number(row.get(origin), origin, as_int=True)
        for column, origin in RATIO_COLUMNS.items():
            r[column] = to_number(row.get(origin), origin, as_int=False)
        r.update(content_text_columns(row.get))      # caption, sentimen, kolaborator
        records.append(r)

    ids = [r["content_id"] for r in records]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Content ID kosong atau duplikat. UPSERT dibatalkan.")
    print("Validasi Content ID berhasil.")

    # Label divalidasi SEBELUM data diubah.
    labels_per_content = {r["content_id"]: parse_labels(r["labels"]) for r in records}

    # ---------- 5. KLASIFIKASI (proteksi tanggal email) ----------
    found = {}
    for truncate in per_chunk(ids):
        sign = ",".join("?" * len(truncate))
        for cid, pk, at in conn.execute(
                f"SELECT content_id, content_pk, source_email_at FROM emplifi_content "
                f"WHERE content_id IN ({sign});", truncate):
            found[cid] = (pk, at)

    undated = [c for c, (_, at) in found.items() if at is None]
    if undated:
        raise ValueError(f"UPSERT dihentikan: {len(undated)} Content ID historis "
                         "tanpa tanggal sumber. Perlu verifikasi terlebih dahulu.")

    new, to_update, same, old = [], [], [], []
    for r in records:
        if r["content_id"] not in found:
            new.append(r)
        else:
            at = found[r["content_id"]][1]
            (to_update if at < source_email_at else same if at == source_email_at else old).append(r)

    # ---------- 6. INSERT / UPDATE ----------
    fill_columns = (["content_id", "date"] + list(TEXT_COLUMNS) + list(NUMERIC_COLUMNS)
                 + list(RATIO_COLUMNS) + list(CONTENT_TEXT_COLUMNS))
    value = lambda r: [r[k] for k in fill_columns] + [file_name, source_email_at, process_time]

    cur = conn.executemany(f"""
        INSERT INTO emplifi_content ({", ".join(fill_columns)}, source_file, source_email_at, imported_at)
        VALUES ({", ".join("?" * (len(fill_columns) + 3))});
    """, [value(r) for r in new])
    insert_count = cur.rowcount if new else 0

    column_set = ", ".join(f"{k} = ?" for k in fill_columns[1:])
    update_count = 0
    for r in to_update:
        cur = conn.execute(f"""
            UPDATE emplifi_content
            SET {column_set}, source_file = ?, source_email_at = ?, imported_at = ?
            WHERE content_id = ? AND source_email_at < ?;
        """, value(r)[1:] + [r["content_id"], source_email_at])
        update_count += cur.rowcount

    print("\n=== HASIL UPSERT ===")
    print("Total baris Excel      :", len(df))
    print("CONTENT baru (insert)  :", insert_count)
    print("CONTENT diperbarui     :", update_count)
    print("Dilewati (versi sama)  :", len(same))
    print("Dilewati (versi lama)  :", len(old))
    if insert_count != len(new) or update_count != len(to_update):
        raise ValueError(f"Hasil UPSERT tidak sesuai perkiraan (insert {insert_count}/"
                         f"{len(new)}, update {update_count}/{len(to_update)}).")
    print("Validasi hasil UPSERT berhasil!")

    # ---------- 7. LABEL (hanya konten yang berubah) ----------
    changed = [r["content_id"] for r in new + to_update]
    pk = {}
    for truncate in per_chunk(changed):
        sign = ",".join("?" * len(truncate))
        pk.update(conn.execute(f"SELECT content_id, content_pk FROM emplifi_content "
                               f"WHERE content_id IN ({sign});", truncate).fetchall())
    conn.executemany("DELETE FROM emplifi_content_label WHERE content_pk = ?;",
                     [(pk[c],) for c in changed])
    row_labels = [(pk[c], c, *lbl, "MAPPED", process_time)
                   for c in changed for lbl in labels_per_content[c]]
    conn.executemany("""
        INSERT INTO emplifi_content_label (content_pk, content_id, label_order, label_raw,
            label_type, tower, campaign, sub_campaign, pillar, mapping_status, mapped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, row_labels)
    print("Mapping label disimpan:", len(row_labels))

    # ---------- 8. PANGKAS DATA MENTAH VERSI LAMA ----------
    print("Data mentah versi lama dipangkas:", prune(conn), "baris")

    # ---------- 9. LOG + COMMIT ----------
    conn.execute("""
        INSERT INTO import_log (file_name, file_hash, row_count, status, pesan, source_email_at,
            jumlah_insert, jumlah_update, jumlah_lewati, created_at)
        VALUES (?, ?, ?, 'success', NULL, ?, ?, ?, ?, ?);
    """, (file_name, file_hash, len(df), source_email_at, insert_count, update_count,
          len(same) + len(old), process_time))
    conn.execute("COMMIT;")
    tighten(conn)
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
        """, (file_name, file_hash, len(df), str(error)[:500], source_email_at, now()))
    except Exception:
        pass
    conn.close()
    sys.exit(1)

conn.close()
