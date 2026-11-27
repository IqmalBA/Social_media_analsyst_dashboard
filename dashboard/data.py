"""
Lapisan data dashboard.

Aturan anti double counting:
  - Total KPI SELALU dihitung dari tabel konten (1 baris per Content ID).
  - Filter label = memilih himpunan Content ID dulu, baru SUM metrik.
  - Breakdown per kategori: pasangan (Content ID, kategori) dibuat unik,
    lalu digabung ke metrik. Angka per kategori benar, tetapi jumlah
    antar-kategori bisa melebihi total karena satu konten bisa punya
    beberapa label.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Modul bersama ada di folder induk (settings.py, db_sqlite.py).
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

NO_LABEL = "(no label)"

# Nama tampilan -> kolom. Hanya metrik yang ada di sumber.
METRICS = {
    "Reach": "total_reach",
    "Impressions": "total_impressions",
    "Engagements": "engagements",
    "Link clicks": "link_clicks",
    "Post clicks": "post_clicks",
    "Video views": "video_views",
}

# Rasio dihitung ulang dari jumlah, BUKAN rata-rata rate per konten.
RATIOS = {
    "Engagement rate (impr.)": ("engagements", "total_impressions"),
    "Engagement rate (reach)": ("engagements", "total_reach"),
}

NUMERIC_COLUMNS = list(METRICS.values()) + [
    "paid_reach", "organic_reach", "paid_impressions",
    "organic_impressions", "impressions_engagement_rate",
    "reach_engagement_rate",
]


# =========================
# AKSES DATABASE (SQLite, hanya baca)
# =========================

def db_path():
    """Lokasi file database. Dapat diganti oleh sumber online (lihat data_source.py)."""
    try:
        import data_source                       # hanya ada di versi online
        return data_source.db_path()
    except ImportError:
        from settings import database_path
        return database_path()


QUERY_TIMEOUT_SECONDS = 40


def connect():
    """Koneksi baca-saja dengan batas waktu: query yang terlalu lama dihentikan dan
    menampilkan pesan, bukan membuat halaman berputar tanpa akhir."""
    import time
    from db_sqlite import open_db
    conn = open_db(db_path(), read_only=True)
    start_time = time.monotonic()
    conn.set_progress_handler(lambda: int(time.monotonic() - start_time > QUERY_TIMEOUT_SECONDS), 100_000)
    return conn


def fetch_status():
    """Query sangat ringan, dipanggil berkala untuk deteksi data baru."""
    conn = connect()
    try:
        b = conn.execute("""
            SELECT import_count, import_sukses, content_count, last_imported_at,
                   last_source_email_at, last_status, last_pesan, last_attempt_at, db_bytes
            FROM v_status;
        """).fetchone()
        try:                                     # database lama belum punya kolom ini
            ai_versi = conn.execute("SELECT ai_versi FROM v_status;").fetchone()[0]
        except Exception:
            ai_versi = ""
    finally:
        conn.close()
    return {
        "import_count": b[1], "content_count": b[2],
        "last_imported_at": b[3], "last_source_email_at": b[4],
        "last_status": b[5], "last_pesan": b[6], "last_attempt_at": b[7],
        "db_mb": (b[8] or 0) / 1e6,
        "signature": f"{b[0]}|{b[2]}|{b[3]}|{ai_versi}",
    }


def fetch_data():
    """Dipanggil hanya saat signature berubah (lihat app.py)."""
    conn = connect()
    try:
        try:
            content = pd.read_sql("SELECT * FROM v_content;", conn)
            label = pd.read_sql("SELECT * FROM v_content_label;", conn)
        except Exception as error:
            if "interrupt" in str(error).lower():
                raise RuntimeError(
                    f"Loading data took longer than {QUERY_TIMEOUT_SECONDS} seconds and was stopped. "
                    "The database structure is outdated: run the GitHub workflow "
                    "'Perbarui data Emplifi' once, then reboot the app.") from error
            raise
        try:                                     # database lama belum punya tabel AI
            ai = pd.read_sql("SELECT content_id, topik AS ai_topik, entitas AS ai_entitas "
                             "FROM ai_konten;", conn)
            ai["ai_topik"] = ai["ai_topik"].replace(TP.LEGACY_TOPICS)
            content = content.merge(ai, on="content_id", how="left")
        except Exception:
            pass
    finally:
        conn.close()
    return prepare(content, label)


def fetch_ai_summary():
    """Ringkasan AI terbaru per cakupan ('sendiri' / 'kompetitor'). Kosong jika belum ada."""
    conn = connect()
    try:
        return pd.read_sql("""
            SELECT r.* FROM ai_ringkasan r
            JOIN (SELECT cakupan, MAX(id) id FROM ai_ringkasan GROUP BY cakupan) t ON t.id = r.id;
        """, conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


OPTIONAL_COLUMNS = ["total_interactions", "ai_topik", "ai_entitas", "kolaborator", "labels_lain", "content_url", "content_image", "kolom_link", "sub_campaigns", "caption",
                  "komentar_positif", "komentar_negatif", "komentar_netral", "total_komentar",
                  "sentimen",
                  "towers", "campaigns", "pillars", "labels_raw"]


def complete_columns(content):
    """Kolom yang belum ada (view lama / cache lama) diisi kosong agar tidak error."""
    missing = [k for k in OPTIONAL_COLUMNS if k not in content]
    if missing:
        content = content.copy()
        for column in missing:
            content[column] = None
    return content


def prepare(content, label):
    content = complete_columns(content.copy())
    label = label.copy()
    if "label_lain" not in label:
        label["label_lain"] = None
    content["post_date"] = pd.to_datetime(content["post_date"]).dt.date
    for column in ["komentar_positif", "komentar_negatif", "komentar_netral", "total_komentar",
                  "total_interactions"]:
        content[column] = pd.to_numeric(content[column], errors="coerce")
    for column in NUMERIC_COLUMNS:
        if column in content:
            content[column] = pd.to_numeric(content[column], errors="coerce")
    for column in ["platform", "profile_name", "content_type", "media_type"]:
        content[column] = content[column].fillna("(empty)")
    import brand_watch as _tp
    lookup = {n: _tp.account_brand(n) for n in content["profile_name"].unique()}
    content["akun"] = content["profile_name"].map(lookup)     # Kopi Rimbun / Rimbun App / Rimbun Roastery
    return content, label


# =========================
# FILTER
# =========================

def options(series):
    """Opsi filter diambil dari data, sehingga kategori baru muncul sendiri."""
    return sorted(v for v in series.dropna().unique() if str(v).strip())


def filter_content(content, label, f):
    """
    f: dict filter. List kosong = tidak difilter.
    Dalam satu dimensi = OR, antar dimensi = AND.
    Tower/Campaign/Sub Campaign harus cocok pada LABEL YANG SAMA.
    """
    df = content

    if f.get("tanggal"):
        start, end = f["tanggal"]
        df = df[(df["post_date"] >= start) & (df["post_date"] <= end)]

    for key, column in [
        ("platform", "platform"), ("profile", "akun"),
        ("content_type", "content_type"), ("media_type", "media_type"),
    ]:
        if f.get(key):
            df = df[df[column].isin(f[key])]

    hier = filtered_hierarchy_labels(label, f)
    if hier is not None:
        df = df[df["content_id"].isin(hier["content_id"])]

    pill = filtered_pillar_labels(label, f)
    if pill is not None:
        df = df[df["content_id"].isin(pill["content_id"])]

    others = filtered_other_labels(label, f)
    if others is not None:
        df = df[df["content_id"].isin(others["content_id"])]

    return df


def filtered_hierarchy_labels(label, f):
    """Baris label Tower-Campaign yang cocok filter, atau None jika tidak difilter."""
    if not (f.get("tower") or f.get("campaign") or f.get("sub_campaign")):
        return None
    l = label[label["label_type"] == "TOWER_CAMPAIGN"]
    if f.get("tower"):
        l = l[l["tower"].isin(f["tower"])]
    if f.get("campaign"):
        l = l[l["campaign"].isin(f["campaign"])]
    if f.get("sub_campaign"):
        l = l[l["sub_campaign"].isin(f["sub_campaign"])]
    return l


def filtered_other_labels(label, f):
    if not f.get("label_lain") or "label_lain" not in label:
        return None
    l = label[label["label_type"] == "LAINNYA"]
    return l[l["label_lain"].isin(f["label_lain"])]


def filtered_pillar_labels(label, f):
    if not f.get("pillar"):
        return None
    l = label[label["label_type"] == "PILLAR"]
    return l[l["pillar"].isin(f["pillar"])]


# =========================
# AGREGASI
# =========================

def summary(df):
    """Total KPI dari konten unik."""
    result = {"Content": int(df["content_id"].nunique())}
    for name, column in METRICS.items():
        result[name] = float(df[column].sum(min_count=1)) if df[column].notna().any() else None
    for name, (top, bottom) in RATIOS.items():
        divisor = df[bottom].sum()
        result[name] = float(df[top].sum() / divisor) if divisor else None
    return result


def previous_period(start, end):
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


def change(now, before):
    """Persentase perubahan; None jika tidak bisa dihitung."""
    if now is None or before in (None, 0):
        return None
    return (now - before) / abs(before)


def _metric_column(metric):
    return list(RATIOS[metric]) if metric in RATIOS else [METRICS[metric]]


def aggregate(df, key, metric):
    """
    Agregasi per grup dari baris yang sudah unik per (grup, Content ID).
    Rasio dihitung ulang dari jumlah, bukan rata-rata rate per konten.
    """
    column = _metric_column(metric)
    spec = {k: (k, lambda s: s.sum(min_count=1)) for k in column}
    spec["Content"] = ("content_id", "nunique")
    result = df.groupby(key, dropna=False).agg(**spec).reset_index()

    if metric in RATIOS:
        top, bottom = RATIOS[metric]
        divisor = result[bottom].where(result[bottom] != 0)
        result[metric] = result[top] / divisor
    else:
        result[metric] = result[METRICS[metric]]

    return result[[key, metric, "Content"]]


def attribute_breakdown(df, column, metric):
    """Breakdown berdasarkan atribut konten (1 nilai per konten -> aditif)."""
    if df.empty:
        return pd.DataFrame(columns=[column, metric, "Content"])
    result = aggregate(df, column, metric)
    return result.sort_values(metric, ascending=False, na_position="last")


def label_breakdown(df, label_rows, column, metric, label_type):
    """
    Breakdown berdasarkan label (many-to-many -> TIDAK aditif).
    label_rows: baris label yang relevan (sudah difilter jika perlu).
    Konten tanpa label jenis ini dimasukkan ke kategori '(no label)'.
    """
    if df.empty:
        return pd.DataFrame(columns=[column, metric, "Content"])

    l = label_rows[label_rows["label_type"] == label_type]
    pairs = l[["content_id", column]].dropna().drop_duplicates()
    pairs = pairs[pairs["content_id"].isin(df["content_id"])]

    without = df.loc[~df["content_id"].isin(pairs["content_id"]), ["content_id"]]
    without = without.assign(**{column: NO_LABEL})

    merged = pd.concat([pairs, without], ignore_index=True).merge(
        df.drop(columns=[column], errors="ignore"), on="content_id", how="inner"
    )
    result = aggregate(merged, column, metric)
    result = result.sort_values(metric, ascending=False, na_position="last")
    end = result[column] == NO_LABEL
    return pd.concat([result[~end], result[end]], ignore_index=True)


def trend(df, metric, granularity):
    if df.empty:
        return pd.DataFrame(columns=["periode", metric, "Content"])
    date_str = pd.to_datetime(df["post_date"])
    if granularity == "Daily":
        period = date_str.dt.normalize()
    elif granularity == "Monthly":
        period = date_str.dt.to_period("M").dt.start_time
    else:
        period = date_str.dt.to_period("W-SUN").dt.start_time
    result = aggregate(df.assign(periode=period), "periode", metric)
    return result.sort_values("periode")


def breakdown_sum_exceeds_total(breakdown, total, metric):
    """True jika jumlah antar-kategori > total (bukti label ganda)."""
    if metric in RATIOS or breakdown.empty or total is None:
        return False
    return breakdown[metric].sum() > total * 1.0000001


def default_range(content):
    if content.empty:
        today = date.today()
        return today, today
    return content["post_date"].min(), content["post_date"].max()


# =========================
# PRESET TANGGAL
# =========================

PRESET = ["All data", "Last 7 days", "Last 30 days",
          "This month", "Last month", "Custom"]


def preset_range(name, date_min, date_max):
    """Rentang relatif terhadap TANGGAL DATA TERAKHIR, bukan hari ini,
    agar tidak kosong jika laporan terlambat masuk."""
    if name == "Last 7 days":
        start = date_max - timedelta(days=6)
    elif name == "Last 30 days":
        start = date_max - timedelta(days=29)
    elif name == "This month":
        start = date_max.replace(day=1)
    elif name == "Last month":
        end = date_max.replace(day=1) - timedelta(days=1)
        return max(end.replace(day=1), date_min), max(min(end, date_max), date_min)
    elif name == "All data":
        start = date_min
    else:
        return None
    return max(start, date_min), date_max


def period_range(date_value, granularity, date_min, date_max):
    """Rentang tanggal untuk satu titik di grafik tren (dipakai saat diklik)."""
    t = pd.Timestamp(date_value).date()
    if granularity == "Monthly":
        start = t.replace(day=1)
        end = (pd.Timestamp(start) + pd.offsets.MonthEnd(0)).date()
    elif granularity == "Weekly":
        start = t - timedelta(days=t.weekday())
        end = start + timedelta(days=6)
    else:
        start = end = t
    return max(start, date_min), min(end, date_max)


# =========================
# WAKTU POSTING
# =========================

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def local_time(series):
    """Waktu posting dalam WIB (tanpa zona) apa pun tipe kolom sumbernya."""
    if pd.api.types.is_datetime64_any_dtype(series):
        timestamp = series
    elif series.map(lambda v: getattr(v, "tzinfo", None) is not None).any():
        timestamp = pd.to_datetime(series, errors="coerce", utc=True)   # ada zona waktu
    else:
        timestamp = pd.to_datetime(series, errors="coerce")             # sudah waktu lokal
    if getattr(timestamp.dt, "tz", None) is not None:
        timestamp = timestamp.dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    return timestamp


def has_time_of_day(timestamp):
    """False jika semua waktu tepat 00:00 (sumber hanya berisi tanggal)."""
    w = timestamp.dropna()
    if w.empty:
        return False
    return bool(((w.dt.hour != 0) | (w.dt.minute != 0)).any())


def _value_per_content(df, key, metric):
    """
    Untuk perbandingan slot waktu: metrik jumlah dirata-rata PER KONTEN
    (agar slot dengan banyak posting tidak otomatis menang),
    rasio dihitung ulang dari jumlah.
    """
    column = _metric_column(metric)
    spec = {k: (k, lambda s: s.sum(min_count=1)) for k in column}
    spec["Content"] = ("content_id", "nunique")
    if metric not in RATIOS:
        spec["_terisi"] = (METRICS[metric], "count")
    result = df.groupby(key).agg(**spec).reset_index()
    if metric in RATIOS:
        top, bottom = RATIOS[metric]
        result["nilai"] = result[top] / result[bottom].where(result[bottom] != 0)
    else:
        col = METRICS[metric]
        result["nilai"] = result[col] / result["_terisi"].where(result["_terisi"] != 0)
    return result[key + ["nilai", "Content"]]


def post_time(df, metric):
    timestamp = local_time(df["posted_at"])
    data = df.assign(hari=timestamp.dt.dayofweek, jam=timestamp.dt.hour).dropna(
        subset=["hari", "jam"])
    data = data.astype({"hari": int, "jam": int})
    return _value_per_content(data, ["hari", "jam"], metric)


def per_day(df, metric):
    timestamp = local_time(df["posted_at"])
    data = df.assign(hari=timestamp.dt.dayofweek).dropna(subset=["hari"])
    data = data.astype({"hari": int})
    result = _value_per_content(data, ["hari"], metric)
    result["nama_hari"] = result["hari"].map(dict(enumerate(WEEKDAYS)))
    return result.sort_values("hari")


# =========================
# PETA KONTEN
# =========================

def content_map(df):
    """Konten dengan Impressions > 0 beserta ER (Engagements / Impressions)."""
    data = df[df["total_impressions"] > 0].copy()
    data["er"] = data["engagements"] / data["total_impressions"]
    return data.dropna(subset=["er"])


# =========================
# PENCARIAN
# =========================

def search(df, text):
    """Semua kata harus ada di Content ID atau Labels (tidak peka huruf besar)."""
    words = [k for k in str(text).lower().split() if k]
    if not words:
        return df
    merged = (df["content_id"].astype(str) + " " + df["labels_raw"].fillna("") + " "
              + df["caption"].fillna("").astype(str)).str.lower()
    matches = pd.Series(True, index=df.index)
    for k in words:
        matches &= merged.str.contains(k, regex=False)
    return df[matches]


# =========================
# HIERARKI TOWER > CAMPAIGN > SUB CAMPAIGN
# =========================

LEVEL = ["tower", "campaign", "sub_campaign"]
SUMMARY_COLUMNS = {
    "Reach": "total_reach", "Impressions": "total_impressions",
    "Engagements": "engagements",
}


def _hierarchy_pairs(df, label_rows):
    l = label_rows[label_rows["label_type"] == "TOWER_CAMPAIGN"]
    l = l[l["content_id"].isin(df["content_id"])][["content_id"] + LEVEL]
    l = l.dropna(subset=LEVEL).drop_duplicates()
    without = df.loc[~df["content_id"].isin(l["content_id"]), ["content_id"]]
    without = without.assign(tower=NO_LABEL, campaign=NO_LABEL, sub_campaign=NO_LABEL)
    return pd.concat([l, without], ignore_index=True)


def _summarize(df, pairs, key):
    """Setiap konten dihitung SEKALI per grup (pasangan dibuat unik dulu)."""
    unique = pairs[["content_id"] + key].drop_duplicates()
    merged = unique.merge(df, on="content_id", how="inner")
    spec = {name: (col, lambda s: s.sum(min_count=1))
            for name, col in SUMMARY_COLUMNS.items()}
    spec["Content"] = ("content_id", "nunique")
    result = merged.groupby(key, dropna=False).agg(**spec).reset_index()
    result["ER (impr.)"] = result["Engagements"] / result["Impressions"].where(
        result["Impressions"] != 0)
    return result


def hierarchy(df, label_rows):
    """
    Mengembalikan (tower, campaign, sub, aditif).
    aditif = True jika setiap konten hanya berada di SATU jalur, sehingga
    angka induk = jumlah anak dan treemap aman dipakai.
    """
    pairs = _hierarchy_pairs(df, label_rows)
    paths_per_content = pairs.groupby("content_id").size()
    additive = bool((paths_per_content <= 1).all())
    return (
        _summarize(df, pairs, ["tower"]),
        _summarize(df, pairs, ["tower", "campaign"]),
        _summarize(df, pairs, LEVEL),
        additive,
    )


def hierarchy_table(tower, campaign, sub):
    """Satu tabel: baris Tower, lalu Campaign, lalu Sub Campaign di bawahnya,
    dengan kolom Tower, Campaign, dan Sub Campaign yang terpisah."""
    row = []
    order = tower.assign(_akhir=tower["tower"] == NO_LABEL).sort_values(
        ["_akhir", "Content"], ascending=[True, False])
    for _, t in order.iterrows():
        row.append({"Level": "Tower", "Tower": t["tower"], "Campaign": "",
                      "Sub Campaign": "", **_value(t)})
        cs = campaign[campaign["tower"] == t["tower"]].sort_values("Content", ascending=False)
        for _, c in cs.iterrows():
            if c["campaign"] == NO_LABEL:
                continue
            row.append({"Level": "Campaign", "Tower": t["tower"],
                          "Campaign": c["campaign"], "Sub Campaign": "", **_value(c)})
            ss = sub[(sub["tower"] == t["tower"]) & (sub["campaign"] == c["campaign"])]
            for _, x in ss.sort_values("Content", ascending=False).iterrows():
                row.append({"Level": "Sub Campaign", "Tower": t["tower"],
                              "Campaign": c["campaign"], "Sub Campaign": x["sub_campaign"],
                              **_value(x)})
    return pd.DataFrame(row)


def path_table(sub):
    """Satu baris per jalur lengkap Tower - Campaign - Sub Campaign."""
    data = sub[sub["tower"] != NO_LABEL].rename(columns={
        "tower": "Tower", "campaign": "Campaign", "sub_campaign": "Sub Campaign"})
    return data.sort_values(["Tower", "Campaign", "Content"], ascending=[True, True, False])


def _value(r):
    return {"Content": int(r["Content"]), "Reach": r["Reach"],
            "Impressions": r["Impressions"], "Engagements": r["Engagements"],
            "ER (impr.)": r["ER (impr.)"]}


# =========================
# KONTRIBUSI (hanya untuk atribut 1-nilai-per-konten -> aditif)
# =========================

def contribution(df, column, metric):
    """Persentase kontribusi. Rasio tidak bisa dijadikan kontribusi -> Impressions."""
    used = "Impressions" if metric in RATIOS else metric
    data = attribute_breakdown(df, column, used)
    total = data[used].sum()
    data["Percent"] = data[used] / total if total else None
    return data, used


# =========================
# PERINGKAT (TOP KONTEN)
# =========================

RANKING = ["Reach", "Impressions", "Video views", "Link clicks",
             "Post clicks", "Engagements"]


def available_metrics(df, items=RANKING):
    """Metrik yang punya data (> 0) pada filter ini; sisanya disembunyikan."""
    found, is_empty = [], []
    for name in items:
        column = METRICS[name]
        (found if (df[column].fillna(0) > 0).any() else is_empty).append(name)
    return found, is_empty


NAME_MARKER = "#konten="


def _valid_link(u):
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))


def short_text(text, n=70):
    """Caption satu baris yang aman dijadikan teks link."""
    if text is None or (not isinstance(text, str) and pd.isna(text)):
        return ""
    t = " ".join(str(text).split())
    return (t[:n].rstrip() + "…") if len(t) > n else t


def link_text(url, text):
    """Nilai untuk kolom link: alamat postingan + teks tampilan di belakang penanda."""
    return (url + NAME_MARKER + text) if _valid_link(url) else None


def top_content(df, metric, n=5):
    """
    Nama  : peringkat + cuplikan caption + profile/platform/tanggal (teks biasa).
    Konten: alamat postingan + Nama di belakang penanda (agar teks bisa diklik).
    """
    column = METRICS[metric]
    data = df[df[column].fillna(0) > 0].nlargest(n, column).copy()
    info = (data["profile_name"].astype(str) + " · " + data["platform"].astype(str)
            + " · " + pd.to_datetime(data["post_date"]).dt.strftime("%d %b"))
    snippet = data["caption"].map(lambda t: short_text(t, 60)) if "caption" in data \
        else pd.Series("", index=data.index)
    data["Name"] = [f"{i}. {c} — {x}" if c else f"{i}. {x}"
                    for i, (c, x) in enumerate(zip(snippet, info), 1)]
    url = data["content_url"] if "content_url" in data else pd.Series(None, index=data.index)
    data["punya_link"] = [_valid_link(u) for u in url]
    data["Posts"] = [u if _valid_link(u) else None for u in url]
    data["Content"] = [link_text(u, x) for u, x in zip(url, data["Name"])]
    return data[["content_image", "Name", "Content", "Posts", column,
                 "punya_link", "content_id"]].rename(
        columns={column: metric, "content_image": "Preview"})


def has_image(df):
    return "content_image" in df and df["content_image"].notna().any()


def has_link(df):
    return "content_url" in df and df["content_url"].notna().any()


def excel_ready(df):
    """Excel tidak menerima zona waktu: semua waktu diubah ke WIB tanpa zona."""
    result = df.copy()
    for column in result.columns:
        series = result[column]
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            result[column] = series.dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
        elif series.dtype == object and series.map(
                lambda v: getattr(v, "tzinfo", None) is not None).any():
            result[column] = local_time(series)
    return result



# =========================
# WHAT HAPPENS IN SOCIAL MEDIA (dari teks postingan akun sendiri)
# =========================
# Catatan: ini analisis postingan akun brand sendiri
# (topik yang dibicarakan brand & responsnya), BUKAN percakapan publik.

import re as _re

STOPWORDS = set("""
yang dan di ke dari untuk dengan ini itu ada pada juga atau dalam akan bisa kamu kami kita
aku saya mereka dia nya lah kah pun sih dong deh yuk ayo jadi lagi sudah udah belum tidak
gak nggak enggak bukan cuma hanya buat biar agar karena kalau kalo jika saat waktu sama
semua banyak lebih paling sangat aja saja makin terus tapi tetapi namun hari ini besok
kemarin sekarang nanti dapat dapetin dapatkan klik link bio cek info selengkapnya
cara apa siapa mana gimana bagaimana kapan berapa setiap tiap baru ya yah nih tuh kok
the and for you your with this that are our from have has will can get now new all out
more just like about into what when how who why its it's not but was were been
""".split())
BRAND_NAMES = {"kopirimbun", "rimbun", "rimbunapp", "rimbunroastery"}
MIN_POSTS = 3          # batas minimal agar sebuah sorotan layak disebut


def hashtag(text):
    return {h.lower() for h in _re.findall(r"#(\w+)", str(text or ""))}


def keywords(text):
    t = str(text or "").lower()
    t = _re.sub(r"https?://\S+|[@#]\w+", " ", t)
    words = _re.findall(r"[a-z][a-z]{2,}", t)
    return {k for k in words if k not in STOPWORDS and k not in BRAND_NAMES}


def has_caption(df):
    return "caption" in df and df["caption"].fillna("").astype(str).str.strip().ne("").any()


def analyze_topics(df, df_prev, kind="hashtag", n=10):
    """
    Topik per postingan (setiap postingan dihitung sekali per topik).
    Hasil: topik, Postingan, Postingan lalu, Engagements, ER, Perubahan.
    """
    if kind == "ai":                            # kategori dari AI (daftar tetap)
        def get_rows(r):
            return [r.ai_topik] if isinstance(getattr(r, "ai_topik", None), str) else []
    else:
        getter = hashtag if kind == "hashtag" else keywords

        def get_rows(r):
            return getter(r.caption)

    def compute(data):
        if data.empty or "caption" not in data:
            return pd.DataFrame(columns=["topik", "Posts", "Engagements", "Impressions"])
        row = [(t, r.content_id, r.engagements, r.total_impressions)
                 for r in data.itertuples() for t in get_rows(r)]
        if not row:
            return pd.DataFrame(columns=["topik", "Posts", "Engagements", "Impressions"])
        x = pd.DataFrame(row, columns=["topik", "content_id", "Engagements", "Impressions"])
        return x.groupby("topik").agg(Posts=("content_id", "nunique"),
                                     Engagements=("Engagements", "sum"),
                                     Impressions=("Impressions", "sum")).reset_index()

    current, previous = compute(df), compute(df_prev)
    if current.empty:
        return current
    result = current.merge(previous[["topik", "Posts"]].rename(columns={"Posts": "Posts (prev.)"}),
                       on="topik", how="left").fillna({"Posts (prev.)": 0})
    result["ER"] = result["Engagements"] / result["Impressions"].where(result["Impressions"] != 0)
    result["Change"] = result["Posts"] - result["Posts (prev.)"]
    result = result.sort_values(["Posts", "Engagements"], ascending=False).head(n)
    return result.reset_index(drop=True)


def _percent(a, b):
    return None if not b else (a - b) / b


def highlights(df, df_prev, label_rows):
    """Kalimat ringkas yang SEMUANYA dihitung dari data. Poin tanpa dukungan data dilewati."""
    points = []
    if df.empty:
        return points

    # 1. Postingan dengan engagement tertinggi
    if df["engagements"].notna().any():
        r = df.loc[df["engagements"].idxmax()]
        text = str(r.get("caption") or "").strip().replace("\n", " ")
        snippet = f' — "{text[:90]}{"…" if len(text) > 90 else ""}"' if text else ""
        points.append(f"**Most engaged post:** {r['profile_name']} on {r['platform']} "
                    f"({r['post_date']:%d %b}), {int(r['engagements']):,} engagements{snippet}")

    # 2. Perubahan engagement per platform (hanya jika kedua periode punya cukup postingan)
    if not df_prev.empty:
        current = df.groupby("platform").agg(n=("content_id", "nunique"), e=("engagements", "sum"))
        previous = df_prev.groupby("platform").agg(n=("content_id", "nunique"), e=("engagements", "sum"))
        merged = current.join(previous, rsuffix="_lalu", how="inner")
        merged = merged[(merged["n"] >= MIN_POSTS) & (merged["n_lalu"] >= MIN_POSTS)]
        if not merged.empty:
            merged["ubah"] = [_percent(a, b) for a, b in zip(merged["e"], merged["e_lalu"])]
            merged = merged.dropna(subset=["ubah"])
            if not merged.empty:
                p = merged["ubah"].abs().idxmax()
                u = merged.loc[p, "ubah"]
                points.append(f"**Biggest change:** {p} engagements {'up' if u > 0 else 'down'} "
                            f"{abs(u):.0%} vs the previous period "
                            f"({int(merged.loc[p, 'n'])} vs {int(merged.loc[p, 'n_lalu'])} posts).")

    # 3. Aktivitas posting per brand
    activity = df.groupby("profile_name")["content_id"].nunique().sort_values(ascending=False)
    if len(activity):
        section = ", ".join(f"{k} {v}" for k, v in activity.head(4).items())
        points.append(f"**Posting activity:** {len(df):,} posts — {section}.")

    # 4. Campaign yang baru muncul periode ini
    l = label_rows[label_rows["label_type"] == "TOWER_CAMPAIGN"]
    curr_c = set(l.loc[l["content_id"].isin(df["content_id"]), "campaign"].dropna())
    prev_c = set(l.loc[l["content_id"].isin(df_prev["content_id"]), "campaign"].dropna())
    new = sorted(curr_c - prev_c) if not df_prev.empty else []
    if new:
        points.append(f"**New active campaigns:** {', '.join(new[:5])}"
                    + (f" and {len(new) - 5} more." if len(new) > 5 else "."))

    # 5. Hashtag yang sedang naik
    if has_caption(df):
        h = analyze_topics(df, df_prev, "hashtag", n=50)
        h = h[(h["Posts"] >= MIN_POSTS) & (h["Change"] > 0)]
        if not h.empty:
            t = h.sort_values("Change", ascending=False).iloc[0]
            points.append(f"**Rising hashtag:** #{t['topik']} used in {int(t['Posts'])} "
                        f"posts (previously {int(t['Posts (prev.)'])}).")

    # 6. Pillar dengan engagement rate tertinggi
    p = label_rows[label_rows["label_type"] == "PILLAR"][["content_id", "pillar"]].drop_duplicates()
    p = p.merge(df[["content_id", "engagements", "total_impressions"]], on="content_id")
    if not p.empty:
        g = p.groupby("pillar").agg(n=("content_id", "nunique"), e=("engagements", "sum"),
                                    i=("total_impressions", "sum"))
        g = g[(g["n"] >= MIN_POSTS) & (g["i"] > 0)]
        if len(g) >= 2:
            g["er"] = g["e"] / g["i"]
            t = g["er"].idxmax()
            points.append(f"**Most engaging pillar:** {t} (ER {g.loc[t, 'er']:.2%}, "
                        f"{int(g.loc[t, 'n'])} posts).")
    points.extend(sentiment_highlights(df, df_prev))
    return points



# =========================
# SENTIMEN KOMENTAR (klasifikasi Emplifi)
# =========================
# Persentase dihitung dari JUMLAH komentar yang diklasifikasi (bukan rata-rata
# per postingan), sehingga postingan dengan banyak komentar berbobot sesuai.

MIN_COMMENTS = 20           # minimal komentar terklasifikasi untuk ringkasan
MIN_BRAND_COMMENTS = 10     # minimal per brand untuk perbandingan
_SENT = ["komentar_positif", "komentar_netral", "komentar_negatif"]


def has_sentiment(df):
    return all(k in df for k in _SENT) and df[_SENT].fillna(0).to_numpy().sum() > 0


def sentiment_summary(df):
    """{positif, netral, negatif, total, pos%, netral%, neg%, net} atau None jika data kurang."""
    if df.empty or not has_sentiment(df):
        return None
    pos, net, neg = (float(df[k].fillna(0).sum()) for k in _SENT)
    total = pos + net + neg
    if total < MIN_COMMENTS:
        return None
    return {"positif": pos, "netral": net, "negatif": neg, "total": total,
            "pos%": pos / total, "netral%": net / total, "neg%": neg / total,
            "net": (pos - neg) / total}


def sentiment_per_brand(df):
    if df.empty or not has_sentiment(df):
        return pd.DataFrame()
    key = "akun" if "akun" in df else "profile_name"
    g = df.groupby(key)[_SENT].sum(min_count=1).fillna(0)
    g.index.name = "profile_name"
    g["total"] = g.sum(axis=1)
    g = g[g["total"] >= MIN_BRAND_COMMENTS].copy()
    for k, name in zip(_SENT, ["Positive", "Neutral", "Negative"]):
        g[name] = g[k] / g["total"]
    g["Net sentiment"] = g["Positive"] - g["Negative"]
    g = g.reset_index()
    order = {n: i for i, n in enumerate(TP.ACCOUNT_ORDER)}
    return g.sort_values("profile_name", key=lambda x: x.map(lambda v: order.get(v, 99)))


SENTIMENTS = {"Positive": "komentar_positif", "Neutral": "komentar_netral", "Negative": "komentar_negatif"}


def comment_topics(df, n=4):
    """Per sentimen: kategori topik (AI) dari POSTINGAN yang menerima komentar tersebut,
    berbobot jumlah komentar. Laporan Feed hanya berisi JUMLAH komentar per sentimen,
    bukan teks komentarnya, jadi ini menjawab "komentar positif/negatif muncul di
    postingan tentang apa", bukan isi kalimat komentarnya."""
    if df.empty or not has_sentiment(df) or not has_ai(df):
        return {}
    x = df[df["ai_topik"].notna()]
    result = {}
    for name, column in SENTIMENTS.items():
        full = float(df[column].fillna(0).sum())
        tot = float(x[column].fillna(0).sum())
        if tot < MIN_BRAND_COMMENTS:
            result[name] = None
            continue
        g = x.groupby("ai_topik")[column].sum()
        g = g[g > 0].sort_values(ascending=False).head(n)
        row = []
        for topic, value in g.items():
            sub = x[x["ai_topik"] == topic]
            row.append({"Topic": topic, "Comments": int(value), "Share": value / tot,
                          "Posts": int((sub[column].fillna(0) > 0).sum()),
                          "contoh": sub.loc[sub[column].fillna(0).idxmax()]})
        result[name] = {"total": int(tot), "cakupan": tot / full if full else None, "baris": row}
    return result


def sentiment_posts(df, direction="negatif", n=5):
    """Postingan dengan komentar negatif/positif terbanyak (minimal 1 komentar jenis itu)."""
    column = "komentar_negatif" if direction == "negatif" else "komentar_positif"
    if df.empty or column not in df:
        return pd.DataFrame()
    data = df[df[column].fillna(0) > 0].nlargest(n, column).copy()
    if data.empty:
        return data
    info = (data["profile_name"].astype(str) + " · " + data["platform"].astype(str)
            + " · " + pd.to_datetime(data["post_date"]).dt.strftime("%d %b"))
    data["Name"] = [f"{short_text(c, 60)} — {x}" if short_text(c) else x
                    for c, x in zip(data["caption"], info)]
    data["Content"] = [link_text(u, x) for u, x in zip(data["content_url"], data["Name"])]
    data["punya_link"] = [_valid_link(u) for u in data["content_url"]]
    data["Comments"] = data[column].astype(int)
    tot = data[_SENT].fillna(0).sum(axis=1)
    data["Share"] = data[column] / tot.where(tot > 0)
    return data[["Name", "Content", "punya_link", "Comments", "Share", "content_url", "content_id"]]


def sentiment_highlights(df, df_prev):
    points = []
    current, previous = sentiment_summary(df), sentiment_summary(df_prev)
    if current:
        text = (f"**Comment sentiment:** {current['pos%']:.0%} positive, {current['neg%']:.0%} negative, "
                f"{current['netral%']:.0%} neutral out of {int(current['total']):,} classified comments")
        if previous:
            d = current["neg%"] - previous["neg%"]
            if abs(d) >= 0.02:
                text += (f"; negative share {'up' if d > 0 else 'down'} {abs(d) * 100:.1f} pts "
                         "vs the previous period")
        points.append(text + ".")
    neg = sentiment_posts(df, "negatif", 1)
    if not neg.empty and neg.iloc[0]["Comments"] >= MIN_POSTS:
        r = neg.iloc[0]
        points.append(f"**Needs attention:** {r['Name']} received {int(r['Comments'])} negative comments"
                    + (f" ({r['Share']:.0%} of classified comments)." if pd.notna(r["Share"]) else "."))
    return points



# =========================
# BRAND WATCH: aplikasi brand dan brand ambassador
# =========================
# Sumber: teks caption + label + kolom Collaborators dari laporan Feed (akun sendiri).
# Kata kunci dapat diubah lewat Streamlit secrets [pantau] tanpa mengubah kode.

import json as _json

import brand_watch as TP

DEFAULT_WATCH = {
    "app": list(TP.ENTITIES["Rimbun App"]["kata_kunci"]),
    "ambassador": {n: list(e["kata_kunci"]) for n, e in TP.ENTITIES.items()
                   if e["kelompok"] == "ambassador"},
}
DESCRIPTIONS = {n: e["keterangan"] for n, e in TP.ENTITIES.items()}


def watch_list(secret=None):
    """Default (brand_watch.py) + tambahan/ubahan dari Streamlit secrets [pantau]."""
    result = {"app": list(DEFAULT_WATCH["app"]),
             "ambassador": {k: list(v) for k, v in DEFAULT_WATCH["ambassador"].items()}}
    if not secret:
        return result
    r = dict(secret)
    if r.get("app"):
        result["app"] = [str(x) for x in r["app"]]
    if r.get("ambassador"):
        for k, v in dict(r["ambassador"]).items():
            result["ambassador"][str(k)] = [str(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
    return result


def competitor_list(secret=None):
    """Pola nama profil kompetitor. Secrets [kompetitor] menambah/mengganti per brand."""
    result = {k: list(v) for k, v in TP.COMPETITORS.items()}
    if secret:
        for k, v in dict(secret).items():
            result[str(k)] = [str(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
    return result


def split_competitors(content, competitor=None):
    """(akun sendiri, akun kompetitor). Seluruh bagian lain dashboard hanya memakai akun
    sendiri, jadi angka brand sendiri tidak pernah tercampur data kompetitor."""
    lookup = {n: TP.profile_party(n, competitor) for n in content["profile_name"].dropna().unique()}
    brand = content["profile_name"].map(lookup)
    rival = content[brand.notna()].copy()
    rival["brand"] = brand[brand.notna()]
    return content[brand.isna()].copy(), rival


def _ai_entities(series):
    """Kolom JSON ai_entitas -> list nama per baris."""
    def parse(v):
        try:
            return [x["nama"] for x in _json.loads(v)] if isinstance(v, str) and v else []
        except (ValueError, TypeError, KeyError):
            return []
    return series.map(parse)


def mentions(df, name, keywords):
    """(mask, sumber). Postingan dihitung jika kata kunci jelas cocok, ATAU AI
    menemukannya dengan kutipan yang sudah diverifikasi kode (lihat ai_analysis.py)."""
    if df.empty:
        is_empty = pd.Series(False, index=df.index)
        return is_empty, pd.Series("", index=df.index)
    kw_match = matches(df, keywords)
    ai = _ai_entities(df["ai_entitas"]).map(lambda x: name in x)
    source = pd.Series("", index=df.index)
    source[ai] = "AI (with quote)"
    source[kw_match] = "Keyword"
    source[kw_match & ai] = "Keyword + AI"
    return kw_match | ai, source


def ai_evidence(df, name):
    """Kutipan AI untuk nama tertentu per postingan (untuk ditampilkan/diaudit)."""
    def getter(v):
        try:
            for x in _json.loads(v) if isinstance(v, str) and v else []:
                if x.get("nama") == name:
                    return x.get("bukti")
        except (ValueError, TypeError):
            pass
        return None
    return df["ai_entitas"].map(getter)


def _search_text(df):
    return (df["caption"].fillna("").astype(str) + " " + df["labels_raw"].fillna("").astype(str)
            + " " + df["kolaborator"].fillna("").astype(str)).str.lower()


def matches(df, keywords):
    """Mask postingan yang memuat salah satu kata kunci (utuh, tidak peka huruf besar)."""
    if df.empty or not keywords:
        return pd.Series(False, index=df.index)
    pattern = "|".join(r"(?<![\w@#])[@#]?" + _re.escape(k.lower().lstrip("@#")) + r"(?!\w)"
                    for k in keywords if str(k).strip())
    return _search_text(df).str.contains(pattern, regex=True, na=False)


def _summarize_watch(data):
    n = data["content_id"].nunique()
    imp = data["total_impressions"].sum()
    eng = data["engagements"].sum()
    neg, tot = 0.0, 0.0
    if all(k in data for k in _SENT):
        neg = float(data["komentar_negatif"].fillna(0).sum())
        tot = float(data[_SENT].fillna(0).to_numpy().sum())
    return {"Posts": n, "Engagements": eng, "Avg. engagements": eng / n if n else None,
            "ER": eng / imp if imp else None, "Negative": neg / tot if tot >= MIN_BRAND_COMMENTS else None,
            "Comments": tot}


def summarize_topics(df, mask):
    """Ringkasan postingan yang cocok, dibandingkan dengan SEMUA postingan pada filter yang sama."""
    if df.empty or not mask.any():
        return None
    topic, full = _summarize_watch(df[mask]), _summarize_watch(df)
    topic["Index"] = (topic["Avg. engagements"] / full["Avg. engagements"]
                       if full["Avg. engagements"] else None)
    topic["Negative (all)"] = full["Negative"]
    topic["Share"] = topic["Posts"] / full["Posts"] if full["Posts"] else None
    return topic


def per_entity(df, mapping):
    """Satu baris per entitas (ambassador). Postingan bisa masuk >1 entitas (tidak aditif)."""
    average = _summarize_watch(df)["Avg. engagements"] if not df.empty else None
    row = []
    for name, words in mapping.items():
        m, _ = mentions(df, name, words)
        if m.any():
            r = _summarize_watch(df[m])
            r["Name"] = name
            r["Index"] = r["Avg. engagements"] / average if average else None
            row.append(r)
    if not row:
        return pd.DataFrame()
    result = pd.DataFrame(row)
    return result[["Name", "Posts", "Engagements", "Avg. engagements", "Index", "ER",
                  "Negative"]].sort_values("Engagements", ascending=False).reset_index(drop=True)


def collaborators(df):
    """Dari kolom Collaborators (dipisah koma/titik koma). Data asli, tanpa daftar nama."""
    if df.empty or "kolaborator" not in df or df["kolaborator"].isna().all():
        return pd.DataFrame()
    x = df[["content_id", "kolaborator", "engagements", "total_impressions"] + _SENT].copy()
    x["Name"] = x["kolaborator"].fillna("").astype(str).str.split(r"[;,]")
    x = x.explode("Name")
    x["Name"] = x["Name"].str.strip()
    x = x[x["Name"] != ""].drop_duplicates(["content_id", "Name"])
    if x.empty:
        return pd.DataFrame()
    average = _summarize_watch(df)["Avg. engagements"]
    row = []
    for name, g in x.groupby("Name"):
        r = _summarize_watch(g)
        r["Name"] = name
        r["Index"] = r["Avg. engagements"] / average if average else None
        row.append(r)
    result = pd.DataFrame(row)
    return result[["Name", "Posts", "Engagements", "Avg. engagements", "Index", "ER",
                  "Negative"]].sort_values("Engagements", ascending=False).reset_index(drop=True)


def top_posts(df, mask, n=5):
    data = df[mask].nlargest(n, "engagements").copy()
    if data.empty:
        return data
    info = (data["profile_name"].astype(str) + " · " + data["platform"].astype(str)
            + " · " + pd.to_datetime(data["post_date"]).dt.strftime("%d %b"))
    data["Name"] = [f"{short_text(c, 70)} — {x}" if short_text(c) else x
                    for c, x in zip(data["caption"], info)]
    data["Content"] = [link_text(u, x) for u, x in zip(data["content_url"], data["Name"])]
    data["punya_link"] = [_valid_link(u) for u in data["content_url"]]
    return data[["Name", "Content", "punya_link", "engagements", "total_impressions"]]


def topic_sentence(name, r):
    """Kalimat ringkas yang seluruhnya dihitung dari data (hanya jika cukup postingan)."""
    if not r or r["Posts"] < MIN_POSTS:
        return None
    text = f"**{name}:** {r['Posts']} posts ({r['Share']:.0%} of total)"
    if r.get("Index"):
        text += (f", average engagement **{r['Index']:.1f}×** the average of all posts"
                 if r["Index"] >= 1 else
                 f", average engagement **{r['Index']:.0%}** of the average of all posts")
    if r.get("Negative") is not None and r.get("Negative (all)") is not None:
        text += (f"; negative comments {r['Negative']:.0%} "
                 f"(all posts average {r['Negative (all)']:.0%})")
    return text + "."


# =========================
# TOPIK (AI) & KOMPETITOR
# =========================

def has_ai(df):
    return "ai_topik" in df and df["ai_topik"].notna().any()


def filter_rivals(rival, f, search_text=""):
    """Kompetitor hanya mengikuti filter tanggal, platform, dan pencarian."""
    if rival.empty:
        return rival
    x = rival
    if f.get("tanggal"):
        start, end = f["tanggal"]
        x = x[(x["post_date"] >= start) & (x["post_date"] <= end)]
    if f.get("platform"):
        x = x[x["platform"].isin(f["platform"])]
    return search(x, search_text)


def compare_brands(own, rival):
    """Perbandingan per brand dengan Total interactions (tersedia untuk akun publik).
    Hanya platform yang ADA di data kompetitor, agar perbandingannya setara."""
    if rival.empty:
        return pd.DataFrame(), []
    platform = sorted(rival["platform"].dropna().unique())
    s = own[own["platform"].isin(platform)].assign(brand=TP.OWN_COMPETITOR_LABEL)
    full = pd.concat([s, rival], ignore_index=True)
    g = full.groupby("brand").agg(Posts=("content_id", "nunique"),
                                    Interactions=("total_interactions", "sum"))
    g["Interactions per post"] = g["Interactions"] / g["Posts"]
    tot_i, tot_p = g["Interactions"].sum(), g["Posts"].sum()
    g["Interaction share"] = g["Interactions"] / tot_i if tot_i else None
    g["Post share"] = g["Posts"] / tot_p if tot_p else None
    g = g.reset_index().rename(columns={"brand": "Brand"})
    return g.sort_values("Interactions", ascending=False).reset_index(drop=True), platform


def topics_per_brand(own, rival, platform):
    """Porsi kategori topik (AI) per brand -> tabel lebar (baris brand, kolom topik)."""
    s = own[own["platform"].isin(platform)].assign(brand=TP.OWN_COMPETITOR_LABEL)
    full = pd.concat([s, rival], ignore_index=True)
    full = full[full["ai_topik"].notna()]
    if full.empty:
        return pd.DataFrame()
    t = pd.crosstab(full["brand"], full["ai_topik"], normalize="index")
    return t


def rival_posts(rival, n=10):
    if rival.empty:
        return rival
    data = rival.nlargest(n, "total_interactions").copy()
    data["Name"] = [f"{short_text(c, 80)}" if short_text(c) else str(p)
                    for c, p in zip(data["caption"], data["profile_name"])]
    data["Content"] = [link_text(u, x) for u, x in zip(data["content_url"], data["Name"])]
    data["punya_link"] = [_valid_link(u) for u in data["content_url"]]
    data["Date"] = pd.to_datetime(data["post_date"]).dt.strftime("%d %b %Y")
    return data[["brand", "profile_name", "platform", "Date", "Content", "punya_link",
                 "ai_topik", "total_interactions"]]


def refs_to_links(text, refs_json, content):
    """[P1] di ringkasan AI -> tautan ke postingan aslinya."""
    try:
        refs = _json.loads(refs_json or "{}")
    except ValueError:
        refs = {}
    url = dict(zip(content["content_id"], content["content_url"]))

    def substitute(m):
        cid = refs.get(m.group(1))
        u = url.get(cid)
        return f"[↗ {m.group(1)}]({u})" if _valid_link(u) else f"({m.group(1)})"
    return _re.sub(r"\[(P\d+)\]", substitute, text)
