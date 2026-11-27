"""
Brand watch configuration, shared by the dashboard (dashboard/data.py) and the AI
step (ai_analisis.py) so both apply exactly the same rules.

Everything here describes the FICTIONAL demo brand "Kopi Rimbun". To use the
pipeline for a real brand, replace the entries below (or override them from
Streamlit secrets: [pantau] and [kompetitor]).

Accuracy rules (dashboard + AI):
  1. Unambiguous keywords (e.g. "wening asmara") are counted directly.
  2. Ambiguous mentions (e.g. "Tara", which is also the Indonesian "ta-da!")
     are only counted when the AI confirms them AND quotes text that really
     exists in the caption AND the quote contains the name's anchor word.
"""

import re
import unicodedata

ENTITAS = {
    "Rimbun App": {
        "kelompok": "aplikasi",
        "keterangan": "Ordering & loyalty app",
        "kata_kunci": ["rimbun app", "rimbunapp", "aplikasi rimbun", "app rimbun"],
        "jangkar": ["rimbun app", "rimbunapp", "aplikasi rimbun", "app rimbun"],
    },
    "Wening Asmara": {
        "kelompok": "ambassador",
        "keterangan": "Singer · seasonal menu campaign",
        "kata_kunci": ["wening asmara", "weningasmara", "wening"],
        "jangkar": ["wening"],
    },
    "Bagas Jenggala": {
        "kelompok": "ambassador",
        "keterangan": "Comedian · Rimbun App campaign",
        "kata_kunci": ["bagas jenggala", "bagasjenggala"],
        "jangkar": ["bagas"],
    },
    "Tara Senandika": {
        "kelompok": "ambassador",
        "keterangan": "Barista champion · Rimbun Roastery",
        # "tara" alone is NOT a keyword: in Indonesian captions it is often "tara!" (ta-da).
        "kata_kunci": ["tara senandika", "tarasenandika", "kak tara", "barista tara"],
        "jangkar": ["tara"],
        "tolak": [r"\btara+\s*[!🎉✨]", r"\btaraa+\b", r"\btara+\s*(menu|promo|produk|varian)\b"],
        "aturan": 'Only for the person Tara Senandika. "Tara!"/"Taraa" used as an '
                  'exclamation ("ta-da!") is NOT a mention.',
    },
}

# Competitor accounts are identified by PROFILE NAME in the Emplifi report (never by
# caption text), so own posts that mention a competitor are never counted as theirs.
KOMPETITOR = {
    "Kopi Senja": [r"kopi ?senja"],
    "Teh Lembah": [r"teh ?lembah"],
    "Kopi Kilat": [r"kopi ?kilat"],
}

# Profile names that are ALWAYS own accounts (never treated as a competitor).
MILIK_SENDIRI = [r"rimbun"]

KOMPETITOR_SENDIRI = "Kopi Rimbun (own accounts)"


def normal(teks):
    """Lower-case, unicode-normalised, single-spaced text (for comparisons)."""
    teks = unicodedata.normalize("NFKC", str(teks or "")).lower()
    teks = teks.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", teks).strip()


def pola_kata(kata_kunci):
    """Regex for whole words/phrases, optionally prefixed by @ or #, case-insensitive."""
    bagian = [r"(?<![\w@#])[@#]?" + re.escape(normal(k).lstrip("@#")) + r"(?!\w)"
              for k in kata_kunci if str(k).strip()]
    return "|".join(bagian) if bagian else None


def bukti_valid(nama, bukti, teks, entitas=ENTITAS):
    """An AI quote is accepted only if (1) it really exists in the caption and
    (2) it contains the anchor word of the claimed name. Stops invented mentions."""
    if nama not in entitas:
        return False
    b = normal(bukti).strip(" \"'.,;:!?")
    t = normal(teks)
    if len(b) < 3 or len(b) > 200 or b not in t:
        return False
    if not any(re.search(r"(?<!\w)[@#]?" + re.escape(j), b) for j in entitas[nama]["jangkar"]):
        return False
    tolak = entitas[nama].get("tolak") or []
    if not tolak:
        return True
    # Valid if at least ONE occurrence of the quote is not one of the generic phrases.
    for m in re.finditer(re.escape(b), t):
        sekitar = t[max(0, m.start() - 15):m.end() + 25]
        if not any(re.search(p, sekitar) for p in tolak):
            return True
    return False


def pihak_profil(nama_profil, kompetitor=None):
    """Competitor brand name, or None for own accounts."""
    kompetitor = KOMPETITOR if kompetitor is None else kompetitor
    n = normal(nama_profil)
    if not n or any(re.search(p, n) for p in MILIK_SENDIRI):
        return None
    for brand, pola in kompetitor.items():
        if any(re.search(p, n) for p in pola):
            return brand
    return None


# Fixed list of AI topic categories (the AI must pick one; it cannot invent new ones).
TOPIK = ["Promos & deals", "New menu & products", "App & ordering", "Stores & openings",
         "Coffee education", "Community & people", "Giveaways", "Service updates",
         "Lifestyle & moments", "Other"]
TOPIK_LAMA = {}          # mapping for renamed categories in older analysis results


# Own profiles grouped into the brand's accounts (profile names can differ per
# platform, e.g. "kopirimbun" vs "Kopi Rimbun Official"). Most specific rule first.
AKUN_SENDIRI = [("Rimbun Roastery", [r"roastery"]),
                ("Rimbun App", [r"rimbun ?app"])]
AKUN_DEFAULT = "Kopi Rimbun"
URUTAN_AKUN = ["Kopi Rimbun", "Rimbun App", "Rimbun Roastery"]


def brand_akun(nama_profil):
    n = normal(nama_profil)
    for brand, pola in AKUN_SENDIRI:
        if any(re.search(p, n) for p in pola):
            return brand
    return AKUN_DEFAULT
