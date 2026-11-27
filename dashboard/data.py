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

# Modul bersama ada di folder induk (konfigurasi.py, db_sqlite.py).
_INDUK = Path(__file__).resolve().parent.parent
if str(_INDUK) not in sys.path:
    sys.path.insert(0, str(_INDUK))

TANPA_LABEL = "(no label)"

# Nama tampilan -> kolom. Hanya metrik yang ada di sumber.
METRIK = {
    "Reach": "total_reach",
    "Impressions": "total_impressions",
    "Engagements": "engagements",
    "Link clicks": "link_clicks",
    "Post clicks": "post_clicks",
    "Video views": "video_views",
}

# Rasio dihitung ulang dari jumlah, BUKAN rata-rata rate per konten.
RASIO = {
    "Engagement rate (impr.)": ("engagements", "total_impressions"),
    "Engagement rate (reach)": ("engagements", "total_reach"),
}

KOLOM_ANGKA = list(METRIK.values()) + [
    "paid_reach", "organic_reach", "paid_impressions",
    "organic_impressions", "impressions_engagement_rate",
    "reach_engagement_rate",
]


# =========================
# AKSES DATABASE (SQLite, hanya baca)
# =========================

def lokasi_db():
    """Lokasi file database. Dapat diganti oleh sumber online (lihat sumber_data.py)."""
    try:
        import sumber_data                       # hanya ada di versi online
        return sumber_data.lokasi_db()
    except ImportError:
        from konfigurasi import lokasi_database
        return lokasi_database()


BATAS_DETIK_QUERY = 40


def koneksi():
    """Koneksi baca-saja dengan batas waktu: query yang terlalu lama dihentikan dan
    menampilkan pesan, bukan membuat halaman berputar tanpa akhir."""
    import time
    from db_sqlite import buka
    conn = buka(lokasi_db(), baca_saja=True)
    mulai = time.monotonic()
    conn.set_progress_handler(lambda: int(time.monotonic() - mulai > BATAS_DETIK_QUERY), 100_000)
    return conn


def ambil_status():
    """Query sangat ringan, dipanggil berkala untuk deteksi data baru."""
    conn = koneksi()
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


def ambil_data():
    """Dipanggil hanya saat signature berubah (lihat app.py)."""
    conn = koneksi()
    try:
        try:
            konten = pd.read_sql("SELECT * FROM v_content;", conn)
            label = pd.read_sql("SELECT * FROM v_content_label;", conn)
        except Exception as error:
            if "interrupt" in str(error).lower():
                raise RuntimeError(
                    f"Loading data took longer than {BATAS_DETIK_QUERY} seconds and was stopped. "
                    "The database structure is outdated: run the GitHub workflow "
                    "'Perbarui data Emplifi' once, then reboot the app.") from error
            raise
        try:                                     # database lama belum punya tabel AI
            ai = pd.read_sql("SELECT content_id, topik AS ai_topik, entitas AS ai_entitas "
                             "FROM ai_konten;", conn)
            ai["ai_topik"] = ai["ai_topik"].replace(TP.TOPIK_LAMA)
            konten = konten.merge(ai, on="content_id", how="left")
        except Exception:
            pass
    finally:
        conn.close()
    return siapkan(konten, label)


def ambil_ringkasan_ai():
    """Ringkasan AI terbaru per cakupan ('sendiri' / 'kompetitor'). Kosong jika belum ada."""
    conn = koneksi()
    try:
        return pd.read_sql("""
            SELECT r.* FROM ai_ringkasan r
            JOIN (SELECT cakupan, MAX(id) id FROM ai_ringkasan GROUP BY cakupan) t ON t.id = r.id;
        """, conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


KOLOM_OPSIONAL = ["total_interactions", "ai_topik", "ai_entitas", "kolaborator", "labels_lain", "content_url", "content_image", "kolom_link", "sub_campaigns", "caption",
                  "komentar_positif", "komentar_negatif", "komentar_netral", "total_komentar",
                  "sentimen",
                  "towers", "campaigns", "pillars", "labels_raw"]


def lengkapi_kolom(konten):
    """Kolom yang belum ada (view lama / cache lama) diisi kosong agar tidak error."""
    hilang = [k for k in KOLOM_OPSIONAL if k not in konten]
    if hilang:
        konten = konten.copy()
        for kolom in hilang:
            konten[kolom] = None
    return konten


def siapkan(konten, label):
    konten = lengkapi_kolom(konten.copy())
    label = label.copy()
    if "label_lain" not in label:
        label["label_lain"] = None
    konten["post_date"] = pd.to_datetime(konten["post_date"]).dt.date
    for kolom in ["komentar_positif", "komentar_negatif", "komentar_netral", "total_komentar",
                  "total_interactions"]:
        konten[kolom] = pd.to_numeric(konten[kolom], errors="coerce")
    for kolom in KOLOM_ANGKA:
        if kolom in konten:
            konten[kolom] = pd.to_numeric(konten[kolom], errors="coerce")
    for kolom in ["platform", "profile_name", "content_type", "media_type"]:
        konten[kolom] = konten[kolom].fillna("(empty)")
    import brand_watch as _tp
    peta = {n: _tp.brand_akun(n) for n in konten["profile_name"].unique()}
    konten["akun"] = konten["profile_name"].map(peta)     # Kopi Rimbun / Rimbun App / Rimbun Roastery
    return konten, label


# =========================
# FILTER
# =========================

def opsi(seri):
    """Opsi filter diambil dari data, sehingga kategori baru muncul sendiri."""
    return sorted(v for v in seri.dropna().unique() if str(v).strip())


def filter_konten(konten, label, f):
    """
    f: dict filter. List kosong = tidak difilter.
    Dalam satu dimensi = OR, antar dimensi = AND.
    Tower/Campaign/Sub Campaign harus cocok pada LABEL YANG SAMA.
    """
    df = konten

    if f.get("tanggal"):
        awal, akhir = f["tanggal"]
        df = df[(df["post_date"] >= awal) & (df["post_date"] <= akhir)]

    for kunci, kolom in [
        ("platform", "platform"), ("profile", "akun"),
        ("content_type", "content_type"), ("media_type", "media_type"),
    ]:
        if f.get(kunci):
            df = df[df[kolom].isin(f[kunci])]

    hier = label_hierarki_terfilter(label, f)
    if hier is not None:
        df = df[df["content_id"].isin(hier["content_id"])]

    pil = label_pillar_terfilter(label, f)
    if pil is not None:
        df = df[df["content_id"].isin(pil["content_id"])]

    lain = label_lain_terfilter(label, f)
    if lain is not None:
        df = df[df["content_id"].isin(lain["content_id"])]

    return df


def label_hierarki_terfilter(label, f):
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


def label_lain_terfilter(label, f):
    if not f.get("label_lain") or "label_lain" not in label:
        return None
    l = label[label["label_type"] == "LAINNYA"]
    return l[l["label_lain"].isin(f["label_lain"])]


def label_pillar_terfilter(label, f):
    if not f.get("pillar"):
        return None
    l = label[label["label_type"] == "PILLAR"]
    return l[l["pillar"].isin(f["pillar"])]


# =========================
# AGREGASI
# =========================

def ringkasan(df):
    """Total KPI dari konten unik."""
    hasil = {"Content": int(df["content_id"].nunique())}
    for nama, kolom in METRIK.items():
        hasil[nama] = float(df[kolom].sum(min_count=1)) if df[kolom].notna().any() else None
    for nama, (atas, bawah) in RASIO.items():
        pembagi = df[bawah].sum()
        hasil[nama] = float(df[atas].sum() / pembagi) if pembagi else None
    return hasil


def periode_sebelumnya(awal, akhir):
    panjang = (akhir - awal).days + 1
    return awal - timedelta(days=panjang), awal - timedelta(days=1)


def perubahan(sekarang, sebelum):
    """Persentase perubahan; None jika tidak bisa dihitung."""
    if sekarang is None or sebelum in (None, 0):
        return None
    return (sekarang - sebelum) / abs(sebelum)


def _kolom_metrik(metrik):
    return list(RASIO[metrik]) if metrik in RASIO else [METRIK[metrik]]


def agregasi(df, kunci, metrik):
    """
    Agregasi per grup dari baris yang sudah unik per (grup, Content ID).
    Rasio dihitung ulang dari jumlah, bukan rata-rata rate per konten.
    """
    kolom = _kolom_metrik(metrik)
    spes = {k: (k, lambda s: s.sum(min_count=1)) for k in kolom}
    spes["Content"] = ("content_id", "nunique")
    hasil = df.groupby(kunci, dropna=False).agg(**spes).reset_index()

    if metrik in RASIO:
        atas, bawah = RASIO[metrik]
        pembagi = hasil[bawah].where(hasil[bawah] != 0)
        hasil[metrik] = hasil[atas] / pembagi
    else:
        hasil[metrik] = hasil[METRIK[metrik]]

    return hasil[[kunci, metrik, "Content"]]


def breakdown_atribut(df, kolom, metrik):
    """Breakdown berdasarkan atribut konten (1 nilai per konten -> aditif)."""
    if df.empty:
        return pd.DataFrame(columns=[kolom, metrik, "Content"])
    hasil = agregasi(df, kolom, metrik)
    return hasil.sort_values(metrik, ascending=False, na_position="last")


def breakdown_label(df, label_rows, kolom, metrik, label_type):
    """
    Breakdown berdasarkan label (many-to-many -> TIDAK aditif).
    label_rows: baris label yang relevan (sudah difilter jika perlu).
    Konten tanpa label jenis ini dimasukkan ke kategori '(no label)'.
    """
    if df.empty:
        return pd.DataFrame(columns=[kolom, metrik, "Content"])

    l = label_rows[label_rows["label_type"] == label_type]
    pasangan = l[["content_id", kolom]].dropna().drop_duplicates()
    pasangan = pasangan[pasangan["content_id"].isin(df["content_id"])]

    tanpa = df.loc[~df["content_id"].isin(pasangan["content_id"]), ["content_id"]]
    tanpa = tanpa.assign(**{kolom: TANPA_LABEL})

    gabung = pd.concat([pasangan, tanpa], ignore_index=True).merge(
        df.drop(columns=[kolom], errors="ignore"), on="content_id", how="inner"
    )
    hasil = agregasi(gabung, kolom, metrik)
    hasil = hasil.sort_values(metrik, ascending=False, na_position="last")
    akhir = hasil[kolom] == TANPA_LABEL
    return pd.concat([hasil[~akhir], hasil[akhir]], ignore_index=True)


def tren(df, metrik, granularitas):
    if df.empty:
        return pd.DataFrame(columns=["periode", metrik, "Content"])
    tgl = pd.to_datetime(df["post_date"])
    if granularitas == "Daily":
        periode = tgl.dt.normalize()
    elif granularitas == "Monthly":
        periode = tgl.dt.to_period("M").dt.start_time
    else:
        periode = tgl.dt.to_period("W-SUN").dt.start_time
    hasil = agregasi(df.assign(periode=periode), "periode", metrik)
    return hasil.sort_values("periode")


def total_jumlah_breakdown_melebihi(breakdown, total, metrik):
    """True jika jumlah antar-kategori > total (bukti label ganda)."""
    if metrik in RASIO or breakdown.empty or total is None:
        return False
    return breakdown[metrik].sum() > total * 1.0000001


def rentang_default(konten):
    if konten.empty:
        hari_ini = date.today()
        return hari_ini, hari_ini
    return konten["post_date"].min(), konten["post_date"].max()


# =========================
# PRESET TANGGAL
# =========================

PRESET = ["All data", "Last 7 days", "Last 30 days",
          "This month", "Last month", "Custom"]


def rentang_preset(nama, tgl_min, tgl_max):
    """Rentang relatif terhadap TANGGAL DATA TERAKHIR, bukan hari ini,
    agar tidak kosong jika laporan terlambat masuk."""
    if nama == "Last 7 days":
        awal = tgl_max - timedelta(days=6)
    elif nama == "Last 30 days":
        awal = tgl_max - timedelta(days=29)
    elif nama == "This month":
        awal = tgl_max.replace(day=1)
    elif nama == "Last month":
        akhir = tgl_max.replace(day=1) - timedelta(days=1)
        return max(akhir.replace(day=1), tgl_min), max(min(akhir, tgl_max), tgl_min)
    elif nama == "All data":
        awal = tgl_min
    else:
        return None
    return max(awal, tgl_min), tgl_max


def rentang_periode(tanggal, granularitas, tgl_min, tgl_max):
    """Rentang tanggal untuk satu titik di grafik tren (dipakai saat diklik)."""
    t = pd.Timestamp(tanggal).date()
    if granularitas == "Monthly":
        awal = t.replace(day=1)
        akhir = (pd.Timestamp(awal) + pd.offsets.MonthEnd(0)).date()
    elif granularitas == "Weekly":
        awal = t - timedelta(days=t.weekday())
        akhir = awal + timedelta(days=6)
    else:
        awal = akhir = t
    return max(awal, tgl_min), min(akhir, tgl_max)


# =========================
# WAKTU POSTING
# =========================

HARI = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def waktu_lokal(seri):
    """Waktu posting dalam WIB (tanpa zona) apa pun tipe kolom sumbernya."""
    if pd.api.types.is_datetime64_any_dtype(seri):
        waktu = seri
    elif seri.map(lambda v: getattr(v, "tzinfo", None) is not None).any():
        waktu = pd.to_datetime(seri, errors="coerce", utc=True)   # ada zona waktu
    else:
        waktu = pd.to_datetime(seri, errors="coerce")             # sudah waktu lokal
    if getattr(waktu.dt, "tz", None) is not None:
        waktu = waktu.dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    return waktu


def punya_jam(waktu):
    """False jika semua waktu tepat 00:00 (sumber hanya berisi tanggal)."""
    w = waktu.dropna()
    if w.empty:
        return False
    return bool(((w.dt.hour != 0) | (w.dt.minute != 0)).any())


def _nilai_per_konten(df, kunci, metrik):
    """
    Untuk perbandingan slot waktu: metrik jumlah dirata-rata PER KONTEN
    (agar slot dengan banyak posting tidak otomatis menang),
    rasio dihitung ulang dari jumlah.
    """
    kolom = _kolom_metrik(metrik)
    spes = {k: (k, lambda s: s.sum(min_count=1)) for k in kolom}
    spes["Content"] = ("content_id", "nunique")
    if metrik not in RASIO:
        spes["_terisi"] = (METRIK[metrik], "count")
    hasil = df.groupby(kunci).agg(**spes).reset_index()
    if metrik in RASIO:
        atas, bawah = RASIO[metrik]
        hasil["nilai"] = hasil[atas] / hasil[bawah].where(hasil[bawah] != 0)
    else:
        kol = METRIK[metrik]
        hasil["nilai"] = hasil[kol] / hasil["_terisi"].where(hasil["_terisi"] != 0)
    return hasil[kunci + ["nilai", "Content"]]


def waktu_posting(df, metrik):
    waktu = waktu_lokal(df["posted_at"])
    data = df.assign(hari=waktu.dt.dayofweek, jam=waktu.dt.hour).dropna(
        subset=["hari", "jam"])
    data = data.astype({"hari": int, "jam": int})
    return _nilai_per_konten(data, ["hari", "jam"], metrik)


def per_hari(df, metrik):
    waktu = waktu_lokal(df["posted_at"])
    data = df.assign(hari=waktu.dt.dayofweek).dropna(subset=["hari"])
    data = data.astype({"hari": int})
    hasil = _nilai_per_konten(data, ["hari"], metrik)
    hasil["nama_hari"] = hasil["hari"].map(dict(enumerate(HARI)))
    return hasil.sort_values("hari")


# =========================
# PETA KONTEN
# =========================

def peta_konten(df):
    """Konten dengan Impressions > 0 beserta ER (Engagements / Impressions)."""
    data = df[df["total_impressions"] > 0].copy()
    data["er"] = data["engagements"] / data["total_impressions"]
    return data.dropna(subset=["er"])


# =========================
# PENCARIAN
# =========================

def cari(df, teks):
    """Semua kata harus ada di Content ID atau Labels (tidak peka huruf besar)."""
    kata = [k for k in str(teks).lower().split() if k]
    if not kata:
        return df
    gabung = (df["content_id"].astype(str) + " " + df["labels_raw"].fillna("") + " "
              + df["caption"].fillna("").astype(str)).str.lower()
    cocok = pd.Series(True, index=df.index)
    for k in kata:
        cocok &= gabung.str.contains(k, regex=False)
    return df[cocok]


# =========================
# HIERARKI TOWER > CAMPAIGN > SUB CAMPAIGN
# =========================

LEVEL = ["tower", "campaign", "sub_campaign"]
KOLOM_RINGKAS = {
    "Reach": "total_reach", "Impressions": "total_impressions",
    "Engagements": "engagements",
}


def _pasangan_hierarki(df, label_rows):
    l = label_rows[label_rows["label_type"] == "TOWER_CAMPAIGN"]
    l = l[l["content_id"].isin(df["content_id"])][["content_id"] + LEVEL]
    l = l.dropna(subset=LEVEL).drop_duplicates()
    tanpa = df.loc[~df["content_id"].isin(l["content_id"]), ["content_id"]]
    tanpa = tanpa.assign(tower=TANPA_LABEL, campaign=TANPA_LABEL, sub_campaign=TANPA_LABEL)
    return pd.concat([l, tanpa], ignore_index=True)


def _ringkas(df, pasangan, kunci):
    """Setiap konten dihitung SEKALI per grup (pasangan dibuat unik dulu)."""
    unik = pasangan[["content_id"] + kunci].drop_duplicates()
    gabung = unik.merge(df, on="content_id", how="inner")
    spes = {nama: (kol, lambda s: s.sum(min_count=1))
            for nama, kol in KOLOM_RINGKAS.items()}
    spes["Content"] = ("content_id", "nunique")
    hasil = gabung.groupby(kunci, dropna=False).agg(**spes).reset_index()
    hasil["ER (impr.)"] = hasil["Engagements"] / hasil["Impressions"].where(
        hasil["Impressions"] != 0)
    return hasil


def hierarki(df, label_rows):
    """
    Mengembalikan (tower, campaign, sub, aditif).
    aditif = True jika setiap konten hanya berada di SATU jalur, sehingga
    angka induk = jumlah anak dan treemap aman dipakai.
    """
    pasangan = _pasangan_hierarki(df, label_rows)
    jalur_per_konten = pasangan.groupby("content_id").size()
    aditif = bool((jalur_per_konten <= 1).all())
    return (
        _ringkas(df, pasangan, ["tower"]),
        _ringkas(df, pasangan, ["tower", "campaign"]),
        _ringkas(df, pasangan, LEVEL),
        aditif,
    )


def tabel_hierarki(tower, campaign, sub):
    """Satu tabel: baris Tower, lalu Campaign, lalu Sub Campaign di bawahnya,
    dengan kolom Tower, Campaign, dan Sub Campaign yang terpisah."""
    baris = []
    urutan = tower.assign(_akhir=tower["tower"] == TANPA_LABEL).sort_values(
        ["_akhir", "Content"], ascending=[True, False])
    for _, t in urutan.iterrows():
        baris.append({"Level": "Tower", "Tower": t["tower"], "Campaign": "",
                      "Sub Campaign": "", **_nilai(t)})
        cs = campaign[campaign["tower"] == t["tower"]].sort_values("Content", ascending=False)
        for _, c in cs.iterrows():
            if c["campaign"] == TANPA_LABEL:
                continue
            baris.append({"Level": "Campaign", "Tower": t["tower"],
                          "Campaign": c["campaign"], "Sub Campaign": "", **_nilai(c)})
            ss = sub[(sub["tower"] == t["tower"]) & (sub["campaign"] == c["campaign"])]
            for _, x in ss.sort_values("Content", ascending=False).iterrows():
                baris.append({"Level": "Sub Campaign", "Tower": t["tower"],
                              "Campaign": c["campaign"], "Sub Campaign": x["sub_campaign"],
                              **_nilai(x)})
    return pd.DataFrame(baris)


def tabel_jalur(sub):
    """Satu baris per jalur lengkap Tower - Campaign - Sub Campaign."""
    data = sub[sub["tower"] != TANPA_LABEL].rename(columns={
        "tower": "Tower", "campaign": "Campaign", "sub_campaign": "Sub Campaign"})
    return data.sort_values(["Tower", "Campaign", "Content"], ascending=[True, True, False])


def _nilai(r):
    return {"Content": int(r["Content"]), "Reach": r["Reach"],
            "Impressions": r["Impressions"], "Engagements": r["Engagements"],
            "ER (impr.)": r["ER (impr.)"]}


# =========================
# KONTRIBUSI (hanya untuk atribut 1-nilai-per-konten -> aditif)
# =========================

def kontribusi(df, kolom, metrik):
    """Persentase kontribusi. Rasio tidak bisa dijadikan kontribusi -> Impressions."""
    dipakai = "Impressions" if metrik in RASIO else metrik
    data = breakdown_atribut(df, kolom, dipakai)
    total = data[dipakai].sum()
    data["Percent"] = data[dipakai] / total if total else None
    return data, dipakai


# =========================
# PERINGKAT (TOP KONTEN)
# =========================

PERINGKAT = ["Reach", "Impressions", "Video views", "Link clicks",
             "Post clicks", "Engagements"]


def metrik_tersedia(df, daftar=PERINGKAT):
    """Metrik yang punya data (> 0) pada filter ini; sisanya disembunyikan."""
    ada, kosong = [], []
    for nama in daftar:
        kolom = METRIK[nama]
        (ada if (df[kolom].fillna(0) > 0).any() else kosong).append(nama)
    return ada, kosong


PENANDA_NAMA = "#konten="


def _link_valid(u):
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))


def teks_singkat(teks, n=70):
    """Caption satu baris yang aman dijadikan teks link."""
    if teks is None or (not isinstance(teks, str) and pd.isna(teks)):
        return ""
    t = " ".join(str(teks).split())
    return (t[:n].rstrip() + "…") if len(t) > n else t


def teks_link(url, teks):
    """Nilai untuk kolom link: alamat postingan + teks tampilan di belakang penanda."""
    return (url + PENANDA_NAMA + teks) if _link_valid(url) else None


def top_konten(df, metrik, n=5):
    """
    Nama  : peringkat + cuplikan caption + profile/platform/tanggal (teks biasa).
    Konten: alamat postingan + Nama di belakang penanda (agar teks bisa diklik).
    """
    kolom = METRIK[metrik]
    data = df[df[kolom].fillna(0) > 0].nlargest(n, kolom).copy()
    info = (data["profile_name"].astype(str) + " · " + data["platform"].astype(str)
            + " · " + pd.to_datetime(data["post_date"]).dt.strftime("%d %b"))
    cuplikan = data["caption"].map(lambda t: teks_singkat(t, 60)) if "caption" in data \
        else pd.Series("", index=data.index)
    data["Name"] = [f"{i}. {c} — {x}" if c else f"{i}. {x}"
                    for i, (c, x) in enumerate(zip(cuplikan, info), 1)]
    url = data["content_url"] if "content_url" in data else pd.Series(None, index=data.index)
    data["punya_link"] = [_link_valid(u) for u in url]
    data["Posts"] = [u if _link_valid(u) else None for u in url]
    data["Content"] = [teks_link(u, x) for u, x in zip(url, data["Name"])]
    return data[["content_image", "Name", "Content", "Posts", kolom,
                 "punya_link", "content_id"]].rename(
        columns={kolom: metrik, "content_image": "Preview"})


def ada_gambar(df):
    return "content_image" in df and df["content_image"].notna().any()


def ada_link(df):
    return "content_url" in df and df["content_url"].notna().any()


def siap_excel(df):
    """Excel tidak menerima zona waktu: semua waktu diubah ke WIB tanpa zona."""
    hasil = df.copy()
    for kolom in hasil.columns:
        seri = hasil[kolom]
        if isinstance(seri.dtype, pd.DatetimeTZDtype):
            hasil[kolom] = seri.dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
        elif seri.dtype == object and seri.map(
                lambda v: getattr(v, "tzinfo", None) is not None).any():
            hasil[kolom] = waktu_lokal(seri)
    return hasil



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
NAMA_BRAND = {"kopirimbun", "rimbun", "rimbunapp", "rimbunroastery"}
MIN_POSTINGAN = 3          # batas minimal agar sebuah sorotan layak disebut


def hashtag(teks):
    return {h.lower() for h in _re.findall(r"#(\w+)", str(teks or ""))}


def kata_kunci(teks):
    t = str(teks or "").lower()
    t = _re.sub(r"https?://\S+|[@#]\w+", " ", t)
    kata = _re.findall(r"[a-z][a-z]{2,}", t)
    return {k for k in kata if k not in STOPWORDS and k not in NAMA_BRAND}


def ada_caption(df):
    return "caption" in df and df["caption"].fillna("").astype(str).str.strip().ne("").any()


def analisis_topik(df, df_lalu, jenis="hashtag", n=10):
    """
    Topik per postingan (setiap postingan dihitung sekali per topik).
    Hasil: topik, Postingan, Postingan lalu, Engagements, ER, Perubahan.
    """
    if jenis == "ai":                            # kategori dari AI (daftar tetap)
        def ambil_baris(r):
            return [r.ai_topik] if isinstance(getattr(r, "ai_topik", None), str) else []
    else:
        ambil = hashtag if jenis == "hashtag" else kata_kunci

        def ambil_baris(r):
            return ambil(r.caption)

    def hitung(data):
        if data.empty or "caption" not in data:
            return pd.DataFrame(columns=["topik", "Posts", "Engagements", "Impressions"])
        baris = [(t, r.content_id, r.engagements, r.total_impressions)
                 for r in data.itertuples() for t in ambil_baris(r)]
        if not baris:
            return pd.DataFrame(columns=["topik", "Posts", "Engagements", "Impressions"])
        x = pd.DataFrame(baris, columns=["topik", "content_id", "Engagements", "Impressions"])
        return x.groupby("topik").agg(Posts=("content_id", "nunique"),
                                     Engagements=("Engagements", "sum"),
                                     Impressions=("Impressions", "sum")).reset_index()

    kini, lalu = hitung(df), hitung(df_lalu)
    if kini.empty:
        return kini
    hasil = kini.merge(lalu[["topik", "Posts"]].rename(columns={"Posts": "Posts (prev.)"}),
                       on="topik", how="left").fillna({"Posts (prev.)": 0})
    hasil["ER"] = hasil["Engagements"] / hasil["Impressions"].where(hasil["Impressions"] != 0)
    hasil["Change"] = hasil["Posts"] - hasil["Posts (prev.)"]
    hasil = hasil.sort_values(["Posts", "Engagements"], ascending=False).head(n)
    return hasil.reset_index(drop=True)


def _persen(a, b):
    return None if not b else (a - b) / b


def sorotan(df, df_lalu, label_rows):
    """Kalimat ringkas yang SEMUANYA dihitung dari data. Poin tanpa dukungan data dilewati."""
    poin = []
    if df.empty:
        return poin

    # 1. Postingan dengan engagement tertinggi
    if df["engagements"].notna().any():
        r = df.loc[df["engagements"].idxmax()]
        teks = str(r.get("caption") or "").strip().replace("\n", " ")
        cuplikan = f' — "{teks[:90]}{"…" if len(teks) > 90 else ""}"' if teks else ""
        poin.append(f"**Most engaged post:** {r['profile_name']} on {r['platform']} "
                    f"({r['post_date']:%d %b}), {int(r['engagements']):,} engagements{cuplikan}")

    # 2. Perubahan engagement per platform (hanya jika kedua periode punya cukup postingan)
    if not df_lalu.empty:
        kini = df.groupby("platform").agg(n=("content_id", "nunique"), e=("engagements", "sum"))
        lalu = df_lalu.groupby("platform").agg(n=("content_id", "nunique"), e=("engagements", "sum"))
        gabung = kini.join(lalu, rsuffix="_lalu", how="inner")
        gabung = gabung[(gabung["n"] >= MIN_POSTINGAN) & (gabung["n_lalu"] >= MIN_POSTINGAN)]
        if not gabung.empty:
            gabung["ubah"] = [_persen(a, b) for a, b in zip(gabung["e"], gabung["e_lalu"])]
            gabung = gabung.dropna(subset=["ubah"])
            if not gabung.empty:
                p = gabung["ubah"].abs().idxmax()
                u = gabung.loc[p, "ubah"]
                poin.append(f"**Biggest change:** {p} engagements {'up' if u > 0 else 'down'} "
                            f"{abs(u):.0%} vs the previous period "
                            f"({int(gabung.loc[p, 'n'])} vs {int(gabung.loc[p, 'n_lalu'])} posts).")

    # 3. Aktivitas posting per brand
    aktivitas = df.groupby("profile_name")["content_id"].nunique().sort_values(ascending=False)
    if len(aktivitas):
        bagian = ", ".join(f"{k} {v}" for k, v in aktivitas.head(4).items())
        poin.append(f"**Posting activity:** {len(df):,} posts — {bagian}.")

    # 4. Campaign yang baru muncul periode ini
    l = label_rows[label_rows["label_type"] == "TOWER_CAMPAIGN"]
    kini_c = set(l.loc[l["content_id"].isin(df["content_id"]), "campaign"].dropna())
    lalu_c = set(l.loc[l["content_id"].isin(df_lalu["content_id"]), "campaign"].dropna())
    baru = sorted(kini_c - lalu_c) if not df_lalu.empty else []
    if baru:
        poin.append(f"**New active campaigns:** {', '.join(baru[:5])}"
                    + (f" and {len(baru) - 5} more." if len(baru) > 5 else "."))

    # 5. Hashtag yang sedang naik
    if ada_caption(df):
        h = analisis_topik(df, df_lalu, "hashtag", n=50)
        h = h[(h["Posts"] >= MIN_POSTINGAN) & (h["Change"] > 0)]
        if not h.empty:
            t = h.sort_values("Change", ascending=False).iloc[0]
            poin.append(f"**Rising hashtag:** #{t['topik']} used in {int(t['Posts'])} "
                        f"posts (previously {int(t['Posts (prev.)'])}).")

    # 6. Pillar dengan engagement rate tertinggi
    p = label_rows[label_rows["label_type"] == "PILLAR"][["content_id", "pillar"]].drop_duplicates()
    p = p.merge(df[["content_id", "engagements", "total_impressions"]], on="content_id")
    if not p.empty:
        g = p.groupby("pillar").agg(n=("content_id", "nunique"), e=("engagements", "sum"),
                                    i=("total_impressions", "sum"))
        g = g[(g["n"] >= MIN_POSTINGAN) & (g["i"] > 0)]
        if len(g) >= 2:
            g["er"] = g["e"] / g["i"]
            t = g["er"].idxmax()
            poin.append(f"**Most engaging pillar:** {t} (ER {g.loc[t, 'er']:.2%}, "
                        f"{int(g.loc[t, 'n'])} posts).")
    poin.extend(sorotan_sentimen(df, df_lalu))
    return poin



# =========================
# SENTIMEN KOMENTAR (klasifikasi Emplifi)
# =========================
# Persentase dihitung dari JUMLAH komentar yang diklasifikasi (bukan rata-rata
# per postingan), sehingga postingan dengan banyak komentar berbobot sesuai.

MIN_KOMENTAR = 20           # minimal komentar terklasifikasi untuk ringkasan
MIN_KOMENTAR_BRAND = 10     # minimal per brand untuk perbandingan
_SEN = ["komentar_positif", "komentar_netral", "komentar_negatif"]


def ada_sentimen(df):
    return all(k in df for k in _SEN) and df[_SEN].fillna(0).to_numpy().sum() > 0


def ringkasan_sentimen(df):
    """{positif, netral, negatif, total, pos%, netral%, neg%, net} atau None jika data kurang."""
    if df.empty or not ada_sentimen(df):
        return None
    pos, net, neg = (float(df[k].fillna(0).sum()) for k in _SEN)
    total = pos + net + neg
    if total < MIN_KOMENTAR:
        return None
    return {"positif": pos, "netral": net, "negatif": neg, "total": total,
            "pos%": pos / total, "netral%": net / total, "neg%": neg / total,
            "net": (pos - neg) / total}


def sentimen_per_brand(df):
    if df.empty or not ada_sentimen(df):
        return pd.DataFrame()
    kunci = "akun" if "akun" in df else "profile_name"
    g = df.groupby(kunci)[_SEN].sum(min_count=1).fillna(0)
    g.index.name = "profile_name"
    g["total"] = g.sum(axis=1)
    g = g[g["total"] >= MIN_KOMENTAR_BRAND].copy()
    for k, nama in zip(_SEN, ["Positive", "Neutral", "Negative"]):
        g[nama] = g[k] / g["total"]
    g["Net sentiment"] = g["Positive"] - g["Negative"]
    g = g.reset_index()
    urutan = {n: i for i, n in enumerate(TP.URUTAN_AKUN)}
    return g.sort_values("profile_name", key=lambda x: x.map(lambda v: urutan.get(v, 99)))


SENTIMEN = {"Positive": "komentar_positif", "Neutral": "komentar_netral", "Negative": "komentar_negatif"}


def topik_komentar(df, n=4):
    """Per sentimen: kategori topik (AI) dari POSTINGAN yang menerima komentar tersebut,
    berbobot jumlah komentar. Laporan Feed hanya berisi JUMLAH komentar per sentimen,
    bukan teks komentarnya, jadi ini menjawab "komentar positif/negatif muncul di
    postingan tentang apa", bukan isi kalimat komentarnya."""
    if df.empty or not ada_sentimen(df) or not ada_ai(df):
        return {}
    x = df[df["ai_topik"].notna()]
    hasil = {}
    for nama, kolom in SENTIMEN.items():
        semua = float(df[kolom].fillna(0).sum())
        tot = float(x[kolom].fillna(0).sum())
        if tot < MIN_KOMENTAR_BRAND:
            hasil[nama] = None
            continue
        g = x.groupby("ai_topik")[kolom].sum()
        g = g[g > 0].sort_values(ascending=False).head(n)
        baris = []
        for topik, nilai in g.items():
            sub = x[x["ai_topik"] == topik]
            baris.append({"Topic": topik, "Comments": int(nilai), "Share": nilai / tot,
                          "Posts": int((sub[kolom].fillna(0) > 0).sum()),
                          "contoh": sub.loc[sub[kolom].fillna(0).idxmax()]})
        hasil[nama] = {"total": int(tot), "cakupan": tot / semua if semua else None, "baris": baris}
    return hasil


def postingan_sentimen(df, arah="negatif", n=5):
    """Postingan dengan komentar negatif/positif terbanyak (minimal 1 komentar jenis itu)."""
    kolom = "komentar_negatif" if arah == "negatif" else "komentar_positif"
    if df.empty or kolom not in df:
        return pd.DataFrame()
    data = df[df[kolom].fillna(0) > 0].nlargest(n, kolom).copy()
    if data.empty:
        return data
    info = (data["profile_name"].astype(str) + " · " + data["platform"].astype(str)
            + " · " + pd.to_datetime(data["post_date"]).dt.strftime("%d %b"))
    data["Name"] = [f"{teks_singkat(c, 60)} — {x}" if teks_singkat(c) else x
                    for c, x in zip(data["caption"], info)]
    data["Content"] = [teks_link(u, x) for u, x in zip(data["content_url"], data["Name"])]
    data["punya_link"] = [_link_valid(u) for u in data["content_url"]]
    data["Comments"] = data[kolom].astype(int)
    tot = data[_SEN].fillna(0).sum(axis=1)
    data["Share"] = data[kolom] / tot.where(tot > 0)
    return data[["Name", "Content", "punya_link", "Comments", "Share", "content_url", "content_id"]]


def sorotan_sentimen(df, df_lalu):
    poin = []
    kini, lalu = ringkasan_sentimen(df), ringkasan_sentimen(df_lalu)
    if kini:
        teks = (f"**Comment sentiment:** {kini['pos%']:.0%} positive, {kini['neg%']:.0%} negative, "
                f"{kini['netral%']:.0%} neutral out of {int(kini['total']):,} classified comments")
        if lalu:
            d = kini["neg%"] - lalu["neg%"]
            if abs(d) >= 0.02:
                teks += (f"; negative share {'up' if d > 0 else 'down'} {abs(d) * 100:.1f} pts "
                         "vs the previous period")
        poin.append(teks + ".")
    neg = postingan_sentimen(df, "negatif", 1)
    if not neg.empty and neg.iloc[0]["Comments"] >= MIN_POSTINGAN:
        r = neg.iloc[0]
        poin.append(f"**Needs attention:** {r['Name']} received {int(r['Comments'])} negative comments"
                    + (f" ({r['Share']:.0%} of classified comments)." if pd.notna(r["Share"]) else "."))
    return poin



# =========================
# BRAND WATCH: aplikasi brand dan brand ambassador
# =========================
# Sumber: teks caption + label + kolom Collaborators dari laporan Feed (akun sendiri).
# Kata kunci dapat diubah lewat Streamlit secrets [pantau] tanpa mengubah kode.

import json as _json

import brand_watch as TP

PANTAU_DEFAULT = {
    "app": list(TP.ENTITAS["Rimbun App"]["kata_kunci"]),
    "ambassador": {n: list(e["kata_kunci"]) for n, e in TP.ENTITAS.items()
                   if e["kelompok"] == "ambassador"},
}
KETERANGAN = {n: e["keterangan"] for n, e in TP.ENTITAS.items()}


def daftar_pantau(rahasia=None):
    """Default (brand_watch.py) + tambahan/ubahan dari Streamlit secrets [pantau]."""
    hasil = {"app": list(PANTAU_DEFAULT["app"]),
             "ambassador": {k: list(v) for k, v in PANTAU_DEFAULT["ambassador"].items()}}
    if not rahasia:
        return hasil
    r = dict(rahasia)
    if r.get("app"):
        hasil["app"] = [str(x) for x in r["app"]]
    if r.get("ambassador"):
        for k, v in dict(r["ambassador"]).items():
            hasil["ambassador"][str(k)] = [str(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
    return hasil


def daftar_kompetitor(rahasia=None):
    """Pola nama profil kompetitor. Secrets [kompetitor] menambah/mengganti per brand."""
    hasil = {k: list(v) for k, v in TP.KOMPETITOR.items()}
    if rahasia:
        for k, v in dict(rahasia).items():
            hasil[str(k)] = [str(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
    return hasil


def pisahkan(konten, kompetitor=None):
    """(akun sendiri, akun kompetitor). Seluruh bagian lain dashboard hanya memakai akun
    sendiri, jadi angka brand sendiri tidak pernah tercampur data kompetitor."""
    peta = {n: TP.pihak_profil(n, kompetitor) for n in konten["profile_name"].dropna().unique()}
    brand = konten["profile_name"].map(peta)
    pesaing = konten[brand.notna()].copy()
    pesaing["brand"] = brand[brand.notna()]
    return konten[brand.isna()].copy(), pesaing


def _entitas_ai(seri):
    """Kolom JSON ai_entitas -> list nama per baris."""
    def urai(v):
        try:
            return [x["nama"] for x in _json.loads(v)] if isinstance(v, str) and v else []
        except (ValueError, TypeError, KeyError):
            return []
    return seri.map(urai)


def sebutan(df, nama, kata_kunci):
    """(mask, sumber). Postingan dihitung jika kata kunci jelas cocok, ATAU AI
    menemukannya dengan kutipan yang sudah diverifikasi kode (lihat ai_analisis.py)."""
    if df.empty:
        kosong = pd.Series(False, index=df.index)
        return kosong, pd.Series("", index=df.index)
    kk = cocok(df, kata_kunci)
    ai = _entitas_ai(df["ai_entitas"]).map(lambda x: nama in x)
    sumber = pd.Series("", index=df.index)
    sumber[ai] = "AI (with quote)"
    sumber[kk] = "Keyword"
    sumber[kk & ai] = "Keyword + AI"
    return kk | ai, sumber


def bukti_ai(df, nama):
    """Kutipan AI untuk nama tertentu per postingan (untuk ditampilkan/diaudit)."""
    def ambil(v):
        try:
            for x in _json.loads(v) if isinstance(v, str) and v else []:
                if x.get("nama") == nama:
                    return x.get("bukti")
        except (ValueError, TypeError):
            pass
        return None
    return df["ai_entitas"].map(ambil)


def _teks_cari(df):
    return (df["caption"].fillna("").astype(str) + " " + df["labels_raw"].fillna("").astype(str)
            + " " + df["kolaborator"].fillna("").astype(str)).str.lower()


def cocok(df, kata_kunci):
    """Mask postingan yang memuat salah satu kata kunci (utuh, tidak peka huruf besar)."""
    if df.empty or not kata_kunci:
        return pd.Series(False, index=df.index)
    pola = "|".join(r"(?<![\w@#])[@#]?" + _re.escape(k.lower().lstrip("@#")) + r"(?!\w)"
                    for k in kata_kunci if str(k).strip())
    return _teks_cari(df).str.contains(pola, regex=True, na=False)


def _ringkas_pantau(data):
    n = data["content_id"].nunique()
    imp = data["total_impressions"].sum()
    eng = data["engagements"].sum()
    neg, tot = 0.0, 0.0
    if all(k in data for k in _SEN):
        neg = float(data["komentar_negatif"].fillna(0).sum())
        tot = float(data[_SEN].fillna(0).to_numpy().sum())
    return {"Posts": n, "Engagements": eng, "Avg. engagements": eng / n if n else None,
            "ER": eng / imp if imp else None, "Negative": neg / tot if tot >= MIN_KOMENTAR_BRAND else None,
            "Comments": tot}


def ringkas_topik(df, mask):
    """Ringkasan postingan yang cocok, dibandingkan dengan SEMUA postingan pada filter yang sama."""
    if df.empty or not mask.any():
        return None
    topik, semua = _ringkas_pantau(df[mask]), _ringkas_pantau(df)
    topik["Index"] = (topik["Avg. engagements"] / semua["Avg. engagements"]
                       if semua["Avg. engagements"] else None)
    topik["Negative (all)"] = semua["Negative"]
    topik["Share"] = topik["Posts"] / semua["Posts"] if semua["Posts"] else None
    return topik


def per_entitas(df, kamus):
    """Satu baris per entitas (ambassador). Postingan bisa masuk >1 entitas (tidak aditif)."""
    rata = _ringkas_pantau(df)["Avg. engagements"] if not df.empty else None
    baris = []
    for nama, kata in kamus.items():
        m, _ = sebutan(df, nama, kata)
        if m.any():
            r = _ringkas_pantau(df[m])
            r["Name"] = nama
            r["Index"] = r["Avg. engagements"] / rata if rata else None
            baris.append(r)
    if not baris:
        return pd.DataFrame()
    hasil = pd.DataFrame(baris)
    return hasil[["Name", "Posts", "Engagements", "Avg. engagements", "Index", "ER",
                  "Negative"]].sort_values("Engagements", ascending=False).reset_index(drop=True)


def kolaborator(df):
    """Dari kolom Collaborators (dipisah koma/titik koma). Data asli, tanpa daftar nama."""
    if df.empty or "kolaborator" not in df or df["kolaborator"].isna().all():
        return pd.DataFrame()
    x = df[["content_id", "kolaborator", "engagements", "total_impressions"] + _SEN].copy()
    x["Name"] = x["kolaborator"].fillna("").astype(str).str.split(r"[;,]")
    x = x.explode("Name")
    x["Name"] = x["Name"].str.strip()
    x = x[x["Name"] != ""].drop_duplicates(["content_id", "Name"])
    if x.empty:
        return pd.DataFrame()
    rata = _ringkas_pantau(df)["Avg. engagements"]
    baris = []
    for nama, g in x.groupby("Name"):
        r = _ringkas_pantau(g)
        r["Name"] = nama
        r["Index"] = r["Avg. engagements"] / rata if rata else None
        baris.append(r)
    hasil = pd.DataFrame(baris)
    return hasil[["Name", "Posts", "Engagements", "Avg. engagements", "Index", "ER",
                  "Negative"]].sort_values("Engagements", ascending=False).reset_index(drop=True)


def postingan_teratas(df, mask, n=5):
    data = df[mask].nlargest(n, "engagements").copy()
    if data.empty:
        return data
    info = (data["profile_name"].astype(str) + " · " + data["platform"].astype(str)
            + " · " + pd.to_datetime(data["post_date"]).dt.strftime("%d %b"))
    data["Name"] = [f"{teks_singkat(c, 70)} — {x}" if teks_singkat(c) else x
                    for c, x in zip(data["caption"], info)]
    data["Content"] = [teks_link(u, x) for u, x in zip(data["content_url"], data["Name"])]
    data["punya_link"] = [_link_valid(u) for u in data["content_url"]]
    return data[["Name", "Content", "punya_link", "engagements", "total_impressions"]]


def kalimat_topik(nama, r):
    """Kalimat ringkas yang seluruhnya dihitung dari data (hanya jika cukup postingan)."""
    if not r or r["Posts"] < MIN_POSTINGAN:
        return None
    teks = f"**{nama}:** {r['Posts']} posts ({r['Share']:.0%} of total)"
    if r.get("Index"):
        teks += (f", average engagement **{r['Index']:.1f}×** the average of all posts"
                 if r["Index"] >= 1 else
                 f", average engagement **{r['Index']:.0%}** of the average of all posts")
    if r.get("Negative") is not None and r.get("Negative (all)") is not None:
        teks += (f"; negative comments {r['Negative']:.0%} "
                 f"(all posts average {r['Negative (all)']:.0%})")
    return teks + "."


# =========================
# TOPIK (AI) & KOMPETITOR
# =========================

def ada_ai(df):
    return "ai_topik" in df and df["ai_topik"].notna().any()


def filter_pesaing(pesaing, f, teks_cari=""):
    """Kompetitor hanya mengikuti filter tanggal, platform, dan pencarian."""
    if pesaing.empty:
        return pesaing
    x = pesaing
    if f.get("tanggal"):
        awal, akhir = f["tanggal"]
        x = x[(x["post_date"] >= awal) & (x["post_date"] <= akhir)]
    if f.get("platform"):
        x = x[x["platform"].isin(f["platform"])]
    return cari(x, teks_cari)


def banding_brand(sendiri, pesaing):
    """Perbandingan per brand dengan Total interactions (tersedia untuk akun publik).
    Hanya platform yang ADA di data kompetitor, agar perbandingannya setara."""
    if pesaing.empty:
        return pd.DataFrame(), []
    platform = sorted(pesaing["platform"].dropna().unique())
    s = sendiri[sendiri["platform"].isin(platform)].assign(brand=TP.KOMPETITOR_SENDIRI)
    semua = pd.concat([s, pesaing], ignore_index=True)
    g = semua.groupby("brand").agg(Posts=("content_id", "nunique"),
                                    Interactions=("total_interactions", "sum"))
    g["Interactions per post"] = g["Interactions"] / g["Posts"]
    tot_i, tot_p = g["Interactions"].sum(), g["Posts"].sum()
    g["Interaction share"] = g["Interactions"] / tot_i if tot_i else None
    g["Post share"] = g["Posts"] / tot_p if tot_p else None
    g = g.reset_index().rename(columns={"brand": "Brand"})
    return g.sort_values("Interactions", ascending=False).reset_index(drop=True), platform


def topik_per_brand(sendiri, pesaing, platform):
    """Porsi kategori topik (AI) per brand -> tabel lebar (baris brand, kolom topik)."""
    s = sendiri[sendiri["platform"].isin(platform)].assign(brand=TP.KOMPETITOR_SENDIRI)
    semua = pd.concat([s, pesaing], ignore_index=True)
    semua = semua[semua["ai_topik"].notna()]
    if semua.empty:
        return pd.DataFrame()
    t = pd.crosstab(semua["brand"], semua["ai_topik"], normalize="index")
    return t


def postingan_pesaing(pesaing, n=10):
    if pesaing.empty:
        return pesaing
    data = pesaing.nlargest(n, "total_interactions").copy()
    data["Name"] = [f"{teks_singkat(c, 80)}" if teks_singkat(c) else str(p)
                    for c, p in zip(data["caption"], data["profile_name"])]
    data["Content"] = [teks_link(u, x) for u, x in zip(data["content_url"], data["Name"])]
    data["punya_link"] = [_link_valid(u) for u in data["content_url"]]
    data["Date"] = pd.to_datetime(data["post_date"]).dt.strftime("%d %b %Y")
    return data[["brand", "profile_name", "platform", "Date", "Content", "punya_link",
                 "ai_topik", "total_interactions"]]


def rujukan_ke_link(teks, rujukan_json, konten):
    """[P1] di ringkasan AI -> tautan ke postingan aslinya."""
    try:
        rujukan = _json.loads(rujukan_json or "{}")
    except ValueError:
        rujukan = {}
    url = dict(zip(konten["content_id"], konten["content_url"]))

    def ganti(m):
        cid = rujukan.get(m.group(1))
        u = url.get(cid)
        return f"[↗ {m.group(1)}]({u})" if _link_valid(u) else f"({m.group(1)})"
    return _re.sub(r"\[(P\d+)\]", ganti, teks)
