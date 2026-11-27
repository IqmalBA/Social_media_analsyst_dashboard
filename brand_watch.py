"""
Brand watch configuration, shared by the dashboard (dashboard/data.py) and the AI
step (ai_analysis.py) so both apply exactly the same rules.

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

ENTITIES = {
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
COMPETITORS = {
    "Kopi Senja": [r"kopi ?senja"],
    "Teh Lembah": [r"teh ?lembah"],
    "Kopi Kilat": [r"kopi ?kilat"],
}

# Profile names that are ALWAYS own accounts (never treated as a competitor).
OWN_BRAND = [r"rimbun"]

OWN_COMPETITOR_LABEL = "Kopi Rimbun (own accounts)"


def normalize(text):
    """Lower-case, unicode-normalised, single-spaced text (for comparisons)."""
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def word_pattern(keywords):
    """Regex for whole words/phrases, optionally prefixed by @ or #, case-insensitive."""
    section = [r"(?<![\w@#])[@#]?" + re.escape(normalize(k).lstrip("@#")) + r"(?!\w)"
              for k in keywords if str(k).strip()]
    return "|".join(section) if section else None


def valid_evidence(name, evidence, text, entity=ENTITIES):
    """An AI quote is accepted only if (1) it really exists in the caption and
    (2) it contains the anchor word of the claimed name. Stops invented mentions."""
    if name not in entity:
        return False
    b = normalize(evidence).strip(" \"'.,;:!?")
    t = normalize(text)
    if len(b) < 3 or len(b) > 200 or b not in t:
        return False
    if not any(re.search(r"(?<!\w)[@#]?" + re.escape(j), b) for j in entity[name]["jangkar"]):
        return False
    reject = entity[name].get("tolak") or []
    if not reject:
        return True
    # Valid if at least ONE occurrence of the quote is not one of the generic phrases.
    for m in re.finditer(re.escape(b), t):
        around = t[max(0, m.start() - 15):m.end() + 25]
        if not any(re.search(p, around) for p in reject):
            return True
    return False


def profile_party(profile_name, competitor=None):
    """Competitor brand name, or None for own accounts."""
    competitor = COMPETITORS if competitor is None else competitor
    n = normalize(profile_name)
    if not n or any(re.search(p, n) for p in OWN_BRAND):
        return None
    for brand, pattern in competitor.items():
        if any(re.search(p, n) for p in pattern):
            return brand
    return None


# Fixed list of AI topic categories (the AI must pick one; it cannot invent new ones).
TOPICS = ["Promos & deals", "New menu & products", "App & ordering", "Stores & openings",
         "Coffee education", "Community & people", "Giveaways", "Service updates",
         "Lifestyle & moments", "Other"]
LEGACY_TOPICS = {}          # mapping for renamed categories in older analysis results


# Own profiles grouped into the brand's accounts (profile names can differ per
# platform, e.g. "kopirimbun" vs "Kopi Rimbun Official"). Most specific rule first.
OWN_ACCOUNTS = [("Rimbun Roastery", [r"roastery"]),
                ("Rimbun App", [r"rimbun ?app"])]
DEFAULT_ACCOUNT = "Kopi Rimbun"
ACCOUNT_ORDER = ["Kopi Rimbun", "Rimbun App", "Rimbun Roastery"]


def account_brand(profile_name):
    n = normalize(profile_name)
    for brand, pattern in OWN_ACCOUNTS:
        if any(re.search(p, n) for p in pattern):
            return brand
    return DEFAULT_ACCOUNT
