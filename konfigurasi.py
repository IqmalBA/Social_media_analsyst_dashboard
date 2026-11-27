"""
Pengaturan bersama sistem Emplifi (versi SQLite).

Lokasi file database SQLite, urutan prioritas:
  1. variabel lingkungan EMPLIFI_DB (dipakai server/GitHub Actions dan pengujian)
  2. "sqlite" di config.json
  3. data/emplifi.db di folder project
"""

import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILE_CONFIG = BASE / "config.json"


def baca_config():
    try:
        return json.loads(FILE_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def lokasi_database():
    if os.environ.get("EMPLIFI_DB"):
        return Path(os.environ["EMPLIFI_DB"])
    lokasi = baca_config().get("sqlite")
    if not lokasi:
        return BASE / "data" / "emplifi.db"
    lokasi = Path(lokasi)
    return lokasi if lokasi.is_absolute() else BASE / lokasi
