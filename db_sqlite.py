"""
Database SQLite sistem Emplifi: struktur tabel, view dashboard, dan koneksi.

Pengganti PostgreSQL. Seluruh data ada di SATU file (default data/emplifi.db),
tidak perlu instalasi, password, atau service.

Waktu disimpan sebagai teks:
  - date (waktu posting)  : waktu lokal WIB  "YYYY-MM-DD HH:MM:SS"
  - *_at (waktu sistem)   : UTC ISO          "YYYY-MM-DDTHH:MM:SS+00:00"
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS emplifi_raw (
    raw_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    sheet_name  TEXT,
    row_number  INTEGER,
    raw_data    TEXT NOT NULL,                 -- JSON baris Excel apa adanya
    imported_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_raw_file ON emplifi_raw (source_file);
CREATE INDEX IF NOT EXISTS ix_raw_file_konten
    ON emplifi_raw (source_file, trim(json_extract(raw_data, '$."Content ID"')));

CREATE TABLE IF NOT EXISTS emplifi_content (
    content_pk   INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id   TEXT NOT NULL UNIQUE,
    date         TEXT,
    profile_name TEXT,
    platform     TEXT,
    content_type TEXT,
    media_type   TEXT,
    labels       TEXT,
    total_interactions  INTEGER,               -- tersedia juga untuk akun publik (kompetitor)
    total_reach         INTEGER,
    paid_reach          INTEGER,
    organic_reach       INTEGER,
    total_impressions   INTEGER,
    paid_impressions    INTEGER,
    organic_impressions INTEGER,
    engagements         INTEGER,
    impressions_engagement_rate REAL,
    reach_engagement_rate       REAL,
    link_clicks  INTEGER,
    post_clicks  INTEGER,
    video_views  INTEGER,
    -- Disalin dari baris laporan saat ETL (bukan dicari ulang saat dashboard dibuka -> cepat)
    caption          TEXT,
    komentar_positif REAL,
    komentar_negatif REAL,
    komentar_netral  REAL,
    total_komentar   REAL,
    sentimen         TEXT,
    kolaborator      TEXT,
    source_file     TEXT,
    source_email_at TEXT,
    imported_at     TEXT
);

CREATE TABLE IF NOT EXISTS emplifi_content_label (
    content_pk     INTEGER NOT NULL
                   REFERENCES emplifi_content (content_pk) ON DELETE CASCADE,
    content_id     TEXT NOT NULL,
    label_order    INTEGER NOT NULL,
    label_raw      TEXT NOT NULL,
    label_type     TEXT NOT NULL,              -- 'PILLAR' / 'TOWER_CAMPAIGN' / 'LAINNYA'
    tower          TEXT,
    campaign       TEXT,
    sub_campaign   TEXT,
    pillar         TEXT,
    mapping_status TEXT,
    mapped_at      TEXT,
    PRIMARY KEY (content_pk, label_order)
);
CREATE INDEX IF NOT EXISTS ix_label_content ON emplifi_content_label (content_id);

-- Semua alamat http(s) di laporan: hyperlink tersembunyi maupun teks sel.
CREATE TABLE IF NOT EXISTS emplifi_link (
    source_file TEXT NOT NULL,
    content_id  TEXT NOT NULL,
    kolom       TEXT NOT NULL,
    url         TEXT NOT NULL,
    PRIMARY KEY (source_file, content_id, kolom)
);

CREATE TABLE IF NOT EXISTS import_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name       TEXT,
    file_hash       TEXT,
    row_count       INTEGER,
    status          TEXT NOT NULL,             -- 'success' / 'failed'
    pesan           TEXT,
    source_email_at TEXT,
    jumlah_insert   INTEGER,
    jumlah_update   INTEGER,
    jumlah_lewati   INTEGER,
    created_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_log_hash ON import_log (file_hash);

-- Hasil AI per postingan. Hanya disimpan setelah lolos pemeriksaan kode
-- (setiap nama yang disebut AI wajib punya kutipan yang benar-benar ada di caption).
CREATE TABLE IF NOT EXISTS ai_konten (
    content_id TEXT PRIMARY KEY,
    teks_hash  TEXT NOT NULL,                  -- caption berubah -> dianalisis ulang
    topik      TEXT,
    entitas    TEXT,                           -- JSON [{"nama": ..., "bukti": ...}]
    model      TEXT,
    dibuat     TEXT
);

-- Ringkasan naratif AI. Hanya disimpan jika SEMUA angka & rujukan postingan cocok
-- dengan fakta yang dihitung sistem.
CREATE TABLE IF NOT EXISTS ai_ringkasan (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cakupan      TEXT NOT NULL,                -- 'sendiri' / 'kompetitor'
    periode_awal TEXT,
    periode_akhir TEXT,
    teks         TEXT NOT NULL,                -- markdown, rujukan postingan berbentuk [P1]
    rujukan      TEXT,                         -- JSON {"P1": "content_id", ...}
    fakta        TEXT,                         -- JSON fakta yang diberikan ke AI (untuk audit)
    model        TEXT,
    dibuat       TEXT
);
"""

LINK_COLUMNS = ("'view on platform', 'permalink', 'post url', 'post link', "
              "'content url', 'content link', 'post permalink'")
# "Post detail URL" hanya dipakai jika alamatnya memang domain media sosial.
# "Link URL" (link DI DALAM postingan) dan URL profil TIDAK PERNAH dipakai.
SOCIAL_DOMAINS = ["instagram.com", "facebook.com", "fb.com", "tiktok.com", "x.com",
                 "twitter.com", "youtube.com", "youtu.be", "linkedin.com", "threads.net"]
_DOMAIN = " OR ".join(f"l.url LIKE '%{d}/%'" for d in SOCIAL_DOMAINS)
LINK_RULES = (f"(lower(trim(l.kolom)) IN ({LINK_COLUMNS}) "
               f"OR (lower(trim(l.kolom)) = 'post detail url' AND ({_DOMAIN})))")
LINK_ORDER = (f"lower(trim(l.kolom)) = 'view on platform' DESC, "
               f"lower(trim(l.kolom)) IN ({LINK_COLUMNS}) DESC, l.kolom")

VIEWS = f"""
DROP VIEW IF EXISTS v_content;
DROP VIEW IF EXISTS v_content_label;
DROP VIEW IF EXISTS v_status;

-- 1 baris per Content ID: SATU-SATUNYA sumber untuk total KPI.
CREATE VIEW v_content AS
SELECT
    c.content_id,
    c.date        AS posted_at,
    date(c.date)  AS post_date,
    c.profile_name, c.platform, c.content_type, c.media_type,
    c.labels      AS labels_raw,
    c.total_interactions,
    c.total_reach, c.paid_reach, c.organic_reach,
    c.total_impressions, c.paid_impressions, c.organic_impressions,
    c.engagements, c.impressions_engagement_rate, c.reach_engagement_rate,
    c.link_clicks, c.post_clicks, c.video_views,
    c.source_file, c.source_email_at, c.imported_at,
    (SELECT group_concat(v, ', ') FROM (SELECT DISTINCT tower v FROM emplifi_content_label
        WHERE content_pk = c.content_pk AND tower IS NOT NULL ORDER BY v))        AS towers,
    (SELECT group_concat(v, ', ') FROM (SELECT DISTINCT campaign v FROM emplifi_content_label
        WHERE content_pk = c.content_pk AND campaign IS NOT NULL ORDER BY v))     AS campaigns,
    (SELECT group_concat(v, ', ') FROM (SELECT DISTINCT pillar v FROM emplifi_content_label
        WHERE content_pk = c.content_pk AND pillar IS NOT NULL ORDER BY v))       AS pillars,
    (SELECT group_concat(v, ', ') FROM (SELECT DISTINCT label_raw v FROM emplifi_content_label
        WHERE content_pk = c.content_pk AND label_type = 'LAINNYA' ORDER BY v))   AS labels_lain,
    (SELECT group_concat(v, ', ') FROM (SELECT DISTINCT sub_campaign v FROM emplifi_content_label
        WHERE content_pk = c.content_pk AND sub_campaign IS NOT NULL ORDER BY v)) AS sub_campaigns,
    -- Link postingan: HANYA kolom yang memang link postingan (View on platform, dll.)
    (SELECT l.url FROM emplifi_link l
        WHERE l.source_file = c.source_file AND l.content_id = c.content_id
          AND {LINK_RULES}
        ORDER BY {LINK_ORDER} LIMIT 1)                                          AS content_url,
    (SELECT l.url FROM emplifi_link l
        WHERE l.source_file = c.source_file AND l.content_id = c.content_id
          AND (lower(l.kolom) LIKE '%image%' OR lower(l.kolom) LIKE '%thumbnail%'
               OR lower(l.kolom) LIKE '%picture%' OR lower(l.kolom) LIKE '%photo%'
               OR lower(l.kolom) LIKE '%media%')
          AND lower(l.kolom) NOT LIKE '%profile%' AND lower(l.kolom) NOT LIKE '%avatar%'
          AND lower(l.kolom) NOT LIKE '%icon%' AND lower(l.kolom) NOT LIKE '%logo%'
        ORDER BY l.kolom LIMIT 1)                                                 AS content_image,
    (SELECT l.kolom FROM emplifi_link l
        WHERE l.source_file = c.source_file AND l.content_id = c.content_id
          AND {LINK_RULES}
        ORDER BY {LINK_ORDER} LIMIT 1)                                          AS kolom_link,
    c.caption, c.komentar_positif, c.komentar_negatif, c.komentar_netral,
    c.total_komentar, c.sentimen, c.kolaborator
FROM emplifi_content c;

-- Jembatan label tanpa metrik (tidak bisa di-SUM tak sengaja).
CREATE VIEW v_content_label AS
SELECT DISTINCT l.content_id, l.label_type, l.tower, l.campaign, l.sub_campaign, l.pillar,
       CASE WHEN l.label_type = 'LAINNYA' THEN l.label_raw END AS label_lain
FROM emplifi_content_label l
JOIN emplifi_content c ON c.content_pk = l.content_pk;

-- Status ringan untuk deteksi data baru + status ETL terakhir.
CREATE VIEW v_status AS
SELECT
    (SELECT COUNT(*) FROM import_log)                                AS import_count,
    (SELECT COUNT(*) FROM import_log WHERE status = 'success')        AS import_sukses,
    (SELECT COUNT(*) FROM emplifi_content)                           AS content_count,
    (SELECT MAX(imported_at) FROM emplifi_content)                   AS last_imported_at,
    (SELECT MAX(source_email_at) FROM emplifi_content)               AS last_source_email_at,
    (SELECT status     FROM import_log ORDER BY log_id DESC LIMIT 1) AS last_status,
    (SELECT pesan      FROM import_log ORDER BY log_id DESC LIMIT 1) AS last_pesan,
    (SELECT created_at FROM import_log ORDER BY log_id DESC LIMIT 1) AS last_attempt_at,
    (SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()) AS db_bytes,
    (SELECT COUNT(*) || '-' || COALESCE(MAX(dibuat), '') FROM ai_konten)
        || '/' || (SELECT COALESCE(MAX(id), 0) FROM ai_ringkasan)       AS ai_versi;
"""


def now():
    """Waktu UTC dalam format teks yang konsisten (bisa dibandingkan sebagai teks)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_utc_text(timestamp):
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def open_db(path, read_only=False):
    path = Path(path)
    if read_only:
        if not path.is_file():
            raise FileNotFoundError(f"Database belum ada: {path}")
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=60, isolation_level=None)  # transaksi manual
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 60000;")
    return conn


def prune(conn):
    """
    Menjaga ukuran database tetap kecil:
      - emplifi_raw hanya menyimpan baris mentah untuk VERSI TERBARU setiap konten
        (versi lama sudah tergantikan dan tidak dipakai dashboard).
      - emplifi_link hanya untuk versi terbaru setiap konten.
    Tanpa ini, laporan harian yang memuat konten yang sama berulang kali membuat
    database tumbuh puluhan kali lipat. File Excel asli tetap menjadi arsip lengkap.
    Mengembalikan jumlah baris yang dihapus.
    """
    raw = conn.execute("""
        DELETE FROM emplifi_raw
        WHERE raw_id NOT IN (
            SELECT r.raw_id FROM emplifi_raw r
            JOIN emplifi_content c
              ON c.source_file = r.source_file
             AND c.content_id = trim(json_extract(r.raw_data, '$."Content ID"'))
        );
    """).rowcount
    link = conn.execute("""
        DELETE FROM emplifi_link
        WHERE NOT EXISTS (
            SELECT 1 FROM emplifi_content c
            WHERE c.source_file = emplifi_link.source_file
              AND c.content_id = emplifi_link.content_id
        );
    """).rowcount
    return raw + link


def tighten(conn):
    """Mengecilkan file setelah penghapusan (harus di luar transaksi)."""
    conn.execute("VACUUM;")


CONTENT_TEXT_COLUMNS = {"caption": "TEXT", "komentar_positif": "REAL", "komentar_negatif": "REAL",
                     "komentar_netral": "REAL", "total_komentar": "REAL", "sentimen": "TEXT",
                     "kolaborator": "TEXT"}
EXTRA_COLUMNS = {"emplifi_content": {"total_interactions": "INTEGER", **CONTENT_TEXT_COLUMNS}}
SCHEMA_VERSION = 2

# Kolom Excel -> kolom database (dipakai ETL dan pengisian ulang database lama).
CAPTION_SOURCES = ["Content", "Title", "Description", "Text", "Message"]
TEXT_NUMBER_SOURCES = {"komentar_positif": "Positive comments", "komentar_negatif": "Negative comments",
                     "komentar_netral": "Neutral comments", "total_komentar": "Total comments"}
TEXT_SOURCES = {"sentimen": "Sentiment", "kolaborator": "Collaborators"}


def _empty(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return True
    try:
        return bool(v != v)                  # NaN / NaT
    except TypeError:                         # pd.NA
        return True


def _loose_number(v):
    """Angka komentar; nilai yang tidak bisa dibaca -> kosong (tidak menggagalkan laporan)."""
    if _empty(v):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def content_text_columns(getter):
    """ambil(nama_kolom_excel) -> nilai. Mengembalikan dict kolom KOLOM_TEKS_KONTEN."""
    caption = None
    for k in CAPTION_SOURCES:
        v = getter(k)
        if not _empty(v):
            caption = str(v).strip()
            break
    result = {"caption": caption}
    for column, origin in TEXT_NUMBER_SOURCES.items():
        result[column] = _loose_number(getter(origin))
    for column, origin in TEXT_SOURCES.items():
        v = getter(origin)
        result[column] = None if _empty(v) else str(v)
    return result


def refill_text(conn):
    """Database lama: isi kolom caption/sentimen/kolaborator dari baris mentah, satu kali jalan
    (membaca data mentah sekali saja, bukan per konten)."""
    import json
    latest = {}
    for raw_id, source, raw in conn.execute(
            "SELECT raw_id, source_file, raw_data FROM emplifi_raw ORDER BY raw_id;"):
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            continue
        cid = d.get("Content ID")
        if cid is not None:
            latest[(source, str(cid).strip())] = d
    row = [(*content_text_columns(d.get).values(), cid, source)
             for (source, cid), d in latest.items()]
    column_set = ", ".join(f"{k} = ?" for k in CONTENT_TEXT_COLUMNS)
    conn.execute("BEGIN;")
    conn.executemany(f"UPDATE emplifi_content SET {column_set} "
                     f"WHERE content_id = ? AND source_file = ?;", row)
    conn.execute("COMMIT;")
    return len(row)


def prepare(conn):
    """Membuat tabel (jika belum ada), menambah kolom baru ke database lama,
    dan memperbarui view. Aman diulang."""
    conn.executescript(SCHEMA)
    for table, column in EXTRA_COLUMNS.items():
        found = {r[1] for r in conn.execute(f"PRAGMA table_info({table});")}
        for name, typ in column.items():
            if name not in found:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ};")
    if conn.execute("PRAGMA user_version;").fetchone()[0] < SCHEMA_VERSION:
        refill_text(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
    conn.executescript(VIEWS)

