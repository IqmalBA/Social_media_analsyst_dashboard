"""
Sumber database untuk dashboard.

ONLINE (Streamlit Community Cloud): file emplifi.db diunduh dari branch "data"
di repository GitHub privat, yang diperbarui setiap hari oleh GitHub Actions.
Pengaturan di Streamlit secrets:

    [github]
    token  = "github_pat_..."        # token BACA SAJA untuk repository ini
    repo   = "namamu/emplifi-dashboard"
    branch = "data"                   # opsional
    file   = "emplifi.db"             # opsional

LOKAL (laptop): tanpa secrets, memakai data/emplifi.db seperti biasa.
"""

import tempfile
from pathlib import Path

import requests
import streamlit as st

API = "https://api.github.com"
FOLDER_UNDUH = Path(tempfile.gettempdir()) / "emplifi_dashboard"


def _pengaturan():
    try:
        g = st.secrets.get("github")
    except Exception:                      # tidak ada secrets.toml (mode lokal)
        return None
    if not g or not g.get("token") or not g.get("repo"):
        return None
    return {"token": g["token"], "repo": g["repo"],
            "branch": g.get("branch", "data"), "file": g.get("file", "emplifi.db")}


def _header(token, raw=False):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


@st.cache_data(ttl=60, show_spinner=False)
def _versi_terbaru(token, repo, branch):
    """SHA commit terbaru branch data (dicek paling sering 1x per menit untuk semua pengguna)."""
    r = requests.get(f"{API}/repos/{repo}/commits/{branch}", headers=_header(token), timeout=20)
    if r.status_code == 404:
        raise RuntimeError(f"Branch '{branch}' belum ada di {repo}. Unggah database awal dulu.")
    r.raise_for_status()
    return r.json()["sha"]


@st.cache_resource(show_spinner="Mengunduh data terbaru...", max_entries=3)
def _unduh(token, repo, branch, nama_file, sha):
    FOLDER_UNDUH.mkdir(parents=True, exist_ok=True)
    tujuan = FOLDER_UNDUH / f"emplifi_{sha[:12]}.db"
    if not tujuan.is_file():
        r = requests.get(f"{API}/repos/{repo}/contents/{nama_file}", params={"ref": sha},
                         headers=_header(token, raw=True), timeout=120)
        r.raise_for_status()
        sementara = tujuan.with_suffix(".tmp")
        sementara.write_bytes(r.content)
        perbarui_struktur(sementara)
        sementara.replace(tujuan)
    else:
        perbarui_struktur(tujuan)                 # file lama yang sudah terunduh sebelumnya
    for lama in FOLDER_UNDUH.glob("emplifi_*.db"):    # bersihkan versi lama
        if lama != tujuan:
            lama.unlink(missing_ok=True)
    return str(tujuan)


def perbarui_struktur(path):
    """Salinan unduhan ini milik dashboard sendiri, jadi aman diperbarui di tempat:
    database versi lama langsung dibuat cepat (kolom caption/sentimen disiapkan, view
    diperbarui) tanpa menunggu GitHub Actions. Gagal -> tetap dipakai apa adanya."""
    try:
        from db_sqlite import buka, siapkan
        conn = buka(path)
        try:
            siapkan(conn)
        finally:
            conn.close()
    except Exception as error:                    # jangan sampai menghalangi dashboard
        print(f"Pembaruan struktur database dilewati: {error}")


def lokasi_db():
    p = _pengaturan()
    if p is None:
        from konfigurasi import lokasi_database
        return lokasi_database()
    sha = _versi_terbaru(p["token"], p["repo"], p["branch"])
    return Path(_unduh(p["token"], p["repo"], p["branch"], p["file"], sha))
