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
DOWNLOAD_FOLDER = Path(tempfile.gettempdir()) / "emplifi_dashboard"


def _settings():
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
def _latest_version(token, repo, branch):
    """SHA commit terbaru branch data (dicek paling sering 1x per menit untuk semua pengguna)."""
    r = requests.get(f"{API}/repos/{repo}/commits/{branch}", headers=_header(token), timeout=20)
    if r.status_code == 404:
        raise RuntimeError(f"Branch '{branch}' belum ada di {repo}. Unggah database awal dulu.")
    r.raise_for_status()
    return r.json()["sha"]


@st.cache_resource(show_spinner="Mengunduh data terbaru...", max_entries=3)
def _download(token, repo, branch, filename, sha):
    DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    target = DOWNLOAD_FOLDER / f"emplifi_{sha[:12]}.db"
    if not target.is_file():
        r = requests.get(f"{API}/repos/{repo}/contents/{filename}", params={"ref": sha},
                         headers=_header(token, raw=True), timeout=120)
        r.raise_for_status()
        temp = target.with_suffix(".tmp")
        temp.write_bytes(r.content)
        update_schema(temp)
        temp.replace(target)
    else:
        update_schema(target)                 # file lama yang sudah terunduh sebelumnya
    for old in DOWNLOAD_FOLDER.glob("emplifi_*.db"):    # bersihkan versi lama
        if old != target:
            old.unlink(missing_ok=True)
    return str(target)


def update_schema(path):
    """Salinan unduhan ini milik dashboard sendiri, jadi aman diperbarui di tempat:
    database versi lama langsung dibuat cepat (kolom caption/sentimen disiapkan, view
    diperbarui) tanpa menunggu GitHub Actions. Gagal -> tetap dipakai apa adanya."""
    try:
        from db_sqlite import open_db, prepare
        conn = open_db(path)
        try:
            prepare(conn)
        finally:
            conn.close()
    except Exception as error:                    # jangan sampai menghalangi dashboard
        print(f"Pembaruan struktur database dilewati: {error}")


def db_path():
    p = _settings()
    if p is None:
        from settings import database_path
        return database_path()
    sha = _latest_version(p["token"], p["repo"], p["branch"])
    return Path(_download(p["token"], p["repo"], p["branch"], p["file"], sha))
