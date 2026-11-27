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
CONFIG_FILE = BASE / "config.json"


def read_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def database_path():
    if os.environ.get("EMPLIFI_DB"):
        return Path(os.environ["EMPLIFI_DB"])
    location = read_config().get("sqlite")
    if not location:
        return BASE / "data" / "emplifi.db"
    location = Path(location)
    return location if location.is_absolute() else BASE / location
