"""
Emplifi Dashboard - tahap 3 (tata letak kartu, filter di atas)
Jalankan lewat ikon "Emplifi Dashboard" atau: streamlit run app.py
"""

import importlib
from datetime import datetime, timezone
from io import BytesIO
import html as _html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import data as D
import viz as V

D = importlib.reload(D)
V = importlib.reload(V)

UPDATE_CHECK_SECONDS = 60
STALE_DATA_HOURS = 36

FILTER_LIST = {
    "f_platform": "Platform", "f_profile": "Profile", "f_tower": "Tower",
    "f_campaign": "Campaign", "f_sub_campaign": "Sub Campaign",
    "f_pillar": "Pillar", "f_label_lain": "Other labels", "f_content_type": "Content type",
    "f_media_type": "Media type",
}
CHART_LOCK = ["c_lain", "c_platform", "c_jalur", "t_jalur", "c_pillar", "c_ctype", "c_mtype", "c_tren",
                "c_peta", "t_konten", "t_hier", "c_profile"]

DARK = bool(st.session_state.get("mode_gelap", False))

st.set_page_config(page_title="Emplifi Dashboard", page_icon="📊", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
  @import url("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap");
  html, body, [class*="css"], .stMarkdown, button, input, textarea {
      font-family: "Plus Jakarta Sans", system-ui, sans-serif !important;
  }
  .block-container {padding-top: 1.2rem; max-width: 1320px;}
  [data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
  h3 {font-size: 1.08rem !important; margin: 0 !important; padding: 0 !important; font-weight: 700 !important;}
  .sub {font-size: 0.86rem; opacity: 0.68; margin: 0.2rem 0 0.7rem 0; line-height: 1.45;}
  .catatan {font-size: 0.78rem; opacity: 0.62; line-height: 1.45;}
  div[data-testid="stVerticalBlockBorderWrapper"] {
      border-radius: 16px; border-color: rgba(127,127,127,0.18) !important;
  }
  /* Header */
  .hero {padding: 4px 0 6px 0;}
  .hero .judul {font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; margin: 0;}
  .hero .tagline {font-size: 0.92rem; opacity: 0.7; margin-top: 2px;}
  .lencana {display:inline-flex; align-items:center; gap:6px; padding: 4px 12px;
            border-radius: 999px; font-size: 0.8rem; font-weight: 600; margin: 8px 8px 0 0;}
  .lencana.ok    {background: rgba(22,163,74,0.12);  color: #15803d;}
  .lencana.warn  {background: rgba(234,179,8,0.16);  color: #a16207;}
  .lencana.gagal {background: rgba(220,38,38,0.12);  color: #b91c1c;}
  .lencana.info  {background: rgba(127,127,127,0.12);}
  /* Kartu KPI */
  .sumber {font-size: 0.76rem; opacity: 0.75; line-height: 1.4; margin: 2px 0 8px;
            padding: 5px 10px; border-radius: 8px; background: rgba(127,127,127,0.07);}
  /* Kartu konten */
  .k-post {display:flex; gap:12px; align-items:flex-start; padding:12px 4px;
           border-bottom:1px solid rgba(127,127,127,0.15);}
  .k-post:last-child {border-bottom:none;}
  .k-rank {flex:0 0 28px; height:28px; border-radius:9px; display:flex; align-items:center;
           justify-content:center; font-weight:800; font-size:0.85rem;
           background: rgba(42,120,214,0.12); color:#2a78d6;}
  .k-thumb {flex:0 0 64px; height:64px; border-radius:10px; background-size:cover;
            background-position:center; background-color: rgba(127,127,127,0.12);}
  .k-isi {flex:1; min-width:0;}
  .k-meta {display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:0.76rem; opacity:0.75;}
  .k-chip {font-weight:700; font-size:0.7rem; padding:2px 8px; border-radius:999px; opacity:1;
           color: var(--c); background: color-mix(in srgb, var(--c) 14%, transparent);}
  .k-buka {margin-left:auto; font-weight:700; text-decoration:none !important; color:#2a78d6 !important;}
  .k-cap {display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
          margin:4px 0 6px; font-size:0.9rem; line-height:1.4; font-weight:600;
          color:inherit !important; text-decoration:none !important;}
  a.k-cap:hover {color:#2a78d6 !important;}
  .k-angka {display:flex; flex-wrap:wrap; gap:6px;}
  .k-m {font-size:0.74rem; padding:2px 8px; border-radius:7px; background: rgba(127,127,127,0.09);}
  .k-m b {font-weight:700;}
  .k-m.utama {background: rgba(42,120,214,0.14); color:#1f5fae;}
  .k-info {font-size:0.72rem; opacity:0.65; margin-top:6px;}
  .s-bar {display:flex; height:8px; border-radius:999px; overflow:hidden; margin:2px 0 8px;
          background: rgba(127,127,127,0.12);}
  .s-bar span {display:block; height:100%;}
  /* Dashboard publik: tanpa ikon unduh/salin di tabel */
  [data-testid="stElementToolbar"], [data-testid="stDataFrameToolbar"] {display: none !important;}
  .ai-judul {font-weight: 700; font-size: 1rem; margin: 2px 0 6px;}
  .kpi {border: 1px solid rgba(127,127,127,0.18); border-radius: 16px; padding: 14px 16px 12px;
        background: rgba(127,127,127,0.04); height: 100%;}
  .kpi .atas {display:flex; align-items:center; gap:8px; font-size: 0.82rem; font-weight: 600; opacity: 0.8;}
  .kpi .ikon {display:inline-flex; width:28px; height:28px; border-radius: 9px; align-items:center;
              justify-content:center; background: rgba(42,120,214,0.12); font-size: 0.95rem;}
  .kpi .angka {font-size: 1.7rem; font-weight: 800; letter-spacing: -0.02em; margin: 8px 0 4px;}
  .kpi .arti {font-size: 0.74rem; opacity: 0.6; line-height: 1.35; min-height: 2em;}
  .kpi .delta {display:inline-block; margin-top: 8px; padding: 2px 9px; border-radius: 999px;
               font-size: 0.74rem; font-weight: 700;}
  .delta.naik  {background: rgba(22,163,74,0.12); color: #15803d;}
  .delta.turun {background: rgba(220,38,38,0.12); color: #b91c1c;}
  .delta.datar {background: rgba(127,127,127,0.12);}
  /* Judul bagian */
  .judul-bagian {display:flex; align-items:center; gap:10px; margin-bottom: 2px;}
  .judul-bagian .ikon {display:inline-flex; width:32px; height:32px; border-radius: 10px;
                       align-items:center; justify-content:center; background: rgba(42,120,214,0.12);}
  .judul-bagian .teks {font-size: 1.08rem; font-weight: 700;}
  .cara {font-size: 0.78rem; border-left: 3px solid rgba(42,120,214,0.6); padding: 4px 10px;
         margin: 4px 0 10px; background: rgba(42,120,214,0.06); border-radius: 0 8px 8px 0;}
  /* Menu loncat */
  .menu {display:flex; flex-wrap:wrap; gap:8px; margin: 6px 0 14px;}
  .menu a {text-decoration:none !important; font-size: 0.8rem; font-weight: 600; padding: 5px 12px;
           border-radius: 999px; border: 1px solid rgba(127,127,127,0.25); color: inherit !important;}
  .menu a:hover {border-color: #2a78d6; color: #2a78d6 !important;}
  .jangkar {position: relative; top: -70px; height: 0;}
  .footer {text-align:center; font-size:0.76rem; opacity:0.55; margin-top:2rem;}

  /* ===== Gaya profesional ===== */
  .block-container {padding-top: 1rem;}
  div[data-testid="stVerticalBlockBorderWrapper"] {
      background: #FFFFFF; border: 1px solid #E6E9F0 !important;
      box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 6px 20px rgba(15,23,42,0.04);
  }
  div[data-testid="stExpander"] details {
      background: #FFFFFF; border: 1px solid #E6E9F0; border-radius: 16px;
      box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  }
  div[data-testid="stExpander"] summary p {font-weight: 700;}
  .banner {display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;
           padding: 22px 26px; border-radius: 20px; color: #FFFFFF; margin-bottom: 10px;
           background: radial-gradient(1200px 300px at 85% -40%, rgba(56,189,248,0.35), transparent 60%),
                       linear-gradient(120deg, #0B1B3F 0%, #13306E 55%, #1F4FA8 100%);
           box-shadow: 0 10px 30px rgba(11,27,63,0.18);}
  .banner .kiri {display:flex; align-items:center; gap:16px;}
  .banner .logo {width:52px; height:52px; border-radius:14px; display:flex; align-items:center;
                 justify-content:center; font-size:1.6rem; background: rgba(255,255,255,0.12);
                 border: 1px solid rgba(255,255,255,0.2);}
  .banner .eyebrow {font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase; opacity:0.7;
                    font-weight:700;}
  .banner .b-judul {font-size:1.55rem; font-weight:800; letter-spacing:-0.02em; line-height:1.15;}
  .banner .b-sub {font-size:0.86rem; opacity:0.78; margin-top:3px;}
  .banner .kanan {display:flex; align-items:center; gap:18px; flex-wrap:wrap;}
  .banner .pill {display:inline-flex; align-items:center; gap:8px; padding:6px 14px; border-radius:999px;
                 background: rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.22);
                 font-size:0.8rem; font-weight:700;}
  .banner .titik {width:8px; height:8px; border-radius:50%;}
  .titik.ok {background:#4ADE80; box-shadow:0 0 0 4px rgba(74,222,128,0.25);}
  .titik.gagal {background:#F87171; box-shadow:0 0 0 4px rgba(248,113,113,0.25);}
  .titik.warn {background:#FBBF24; box-shadow:0 0 0 4px rgba(251,191,36,0.25);}
  .banner .info {font-size:0.76rem; opacity:0.8; line-height:1.4; text-align:right;}
  .banner .info b {font-size:0.9rem; opacity:1;}
  .kpi {background:#FFFFFF; border:1px solid #E6E9F0; border-top: 3px solid var(--aksen, #2a78d6);
        box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 6px 20px rgba(15,23,42,0.04);}
  .kpi .ikon {background: color-mix(in srgb, var(--aksen, #2a78d6) 14%, transparent);}
  .kpi .angka {color:#0F172A;}
  .menu a {background:#FFFFFF; border-color:#E6E9F0;}
  /* ===== Tampilan HP ===== */
  @media (max-width: 640px) {
    .block-container {padding: 0.6rem 0.75rem 2rem !important;}
    .banner {padding: 14px 16px; border-radius: 16px; gap: 10px;}
    .banner .logo {width: 40px; height: 40px; font-size: 1.2rem; border-radius: 12px;}
    .banner .b-judul {font-size: 1.15rem;}
    .banner .b-sub, .banner .eyebrow {display: none;}
    .banner .kanan {gap: 10px; width: 100%; justify-content: space-between;}
    .banner .info {text-align: left; font-size: 0.72rem;}
    /* kartu KPI: 2 per baris, bukan 1 per baris */
    [data-testid="stHorizontalBlock"]:has(.kpi) {flex-wrap: wrap !important; gap: 8px !important;}
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="column"] {
        flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important; width: calc(50% - 8px) !important;}
    .kpi {padding: 10px 12px 8px; border-radius: 12px;}
    .kpi .angka {font-size: 1.25rem; margin: 4px 0 2px;}
    .kpi.utama .arti, .kpi .vs {display: none;}
    .kpi .ikon {width: 22px; height: 22px; font-size: 0.8rem;}
    /* menu loncat: satu baris, geser ke samping */
    .menu {flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 4px;}
    .menu a {white-space: nowrap; flex: 0 0 auto;}
    .judul-bagian .teks {font-size: 1rem;}
    .sub {font-size: 0.8rem;}
    .cara {display: none;}
    [data-testid="stTabs"] [role="tablist"] {overflow-x: auto; flex-wrap: nowrap;}
    .k-thumb {flex-basis: 52px; height: 52px;}
    .k-cap {font-size: 0.86rem;}
  }
</style>
""", unsafe_allow_html=True)


def chart(fig, *args, **kwargs):
    """Semua grafik: ikut mode terang/gelap, dan DIAM saat disentuh (nyaman di HP):
    tanpa zoom/geser/toolbar, legenda tidak bisa diklik, ketukan tidak memfilter dashboard.
    Mengetuk/mengarahkan kursor tetap menampilkan angka."""
    kwargs.setdefault("theme", None)
    kwargs.pop("on_select", None)
    kwargs.pop("selection_mode", None)
    kwargs.setdefault("config", {"displayModeBar": False, "scrollZoom": False,
                                 "doubleClick": False, "showTips": False, "responsive": True})
    fig = V.apply_theme(fig, DARK)
    fig.update_layout(dragmode=False, hovermode="closest" if fig.layout.hovermode is None
                      else fig.layout.hovermode,
                      legend=dict(itemclick=False, itemdoubleclick=False))
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return st.plotly_chart(fig, *args, **kwargs)

# Mode gelap: menimpa warna latar, kartu, teks, dan input
if DARK:
    st.markdown("""
<style>
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {background: #0B1120 !important;}
  .stApp, .stMarkdown, .stMarkdown p, .stMarkdown li, label, h1, h2, h3,
  [data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"],
  .stRadio label p, .stCheckbox label p, [data-testid="stToggle"] label p,
  [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary svg {color: #E2E8F0 !important;}
  div[data-testid="stVerticalBlockBorderWrapper"] {background: #141B2D !important;
      border-color: #22304D !important; box-shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.25) !important;}
  div[data-testid="stExpander"] details {background: #141B2D !important; border-color: #22304D !important;}
  .kpi {background: #141B2D !important; border-color: #22304D !important;}
  .kpi .angka {color: #F8FAFC !important;}
  .menu a {background: #141B2D !important; border-color: #22304D !important; color: #E2E8F0 !important;}
  .cara {background: rgba(57,135,229,0.12) !important;}
  [data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-baseweb="base-input"],
  .stDateInput input, .stTextInput input, [data-baseweb="popover"] ul {
      background: #0F172A !important; color: #E2E8F0 !important; border-color: #22304D !important;}
  [data-baseweb="tag"] {background: rgba(57,135,229,0.25) !important;}
  .stButton button, .stDownloadButton button {background: #141B2D !important; color: #E2E8F0 !important;
      border-color: #22304D !important;}
  /* Tabel digambar di kanvas: dibalik warnanya agar menyatu dengan mode gelap */
  [data-testid="stDataFrame"] {filter: invert(0.9) hue-rotate(180deg); border-radius: 8px;}
  .delta.naik {color: #4ADE80 !important;} .delta.turun {color: #F87171 !important;}
  .catatan, .sub {opacity: 0.75;}
  .k-m.utama {color: #8fbcf5 !important; background: rgba(57,135,229,0.22) !important;}
  .k-rank {color: #8fbcf5 !important; background: rgba(57,135,229,0.22) !important;}
  .k-post {border-color: #22304D !important;}
</style>""", unsafe_allow_html=True)


# =========================
# LOGIN (hanya aktif jika diatur di Streamlit secrets)
# =========================
#   [akses]
#   kunci_link = ["kunci-acak-1", "kunci-acak-2"]   # link rahasia: klien cukup klik
#   email = [...]        # opsional: login Google ([auth]) dengan daftar email
#   password = "..."     # opsional: login email + password

import hmac


def _secrets(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def _user():
    return getattr(st, "user", None) or getattr(st, "experimental_user", None)


def login_gate():
    access = _secrets("akses")
    if not access:
        return None                                  # mode lokal: tanpa login
    allowed = [e.strip().lower() for e in access.get("email", []) if e.strip()]

    valid_keys = access.get("kunci_link") or []
    if isinstance(valid_keys, str):
        valid_keys = [valid_keys]
    if valid_keys:                                    # link rahasia: tanpa login
        if st.session_state.get("lolos_kunci"):
            return None
        key = str(st.query_params.get("kunci", "")).strip()
        if key and any(hmac.compare_digest(key.encode(), str(k).encode())
                         for k in valid_keys if str(k).strip()):
            st.session_state["lolos_kunci"] = True
            return None
        if not (_secrets("auth") or access.get("password")):
            st.markdown("<div style='max-width:460px;margin:18vh auto;text-align:center'>"
                        "<h2>Emplifi Performance Dashboard</h2>"
                        "<p style='opacity:.7'>This link is invalid or has expired. "
                        "Please ask the dashboard administrator for the latest link.</p></div>",
                        unsafe_allow_html=True)
            st.stop()

    if _secrets("auth"):                             # login Google
        user = _user()
        if not getattr(user, "is_logged_in", False):
            st.markdown("<div style='max-width:420px;margin:12vh auto;text-align:center'>"
                        "<h2>Emplifi Performance Dashboard</h2>"
                        "<p style='opacity:.7'>Sign in with a registered Google account.</p>"
                        "</div>", unsafe_allow_html=True)
            _, middle, _ = st.columns([2, 1, 2])
            middle.button("Sign in with Google", on_click=st.login,
                          type="primary", use_container_width=True)
            st.stop()
        email = (getattr(user, "email", "") or "").lower()
        if allowed and email not in allowed:
            st.error(f"Account {email} does not have access to this dashboard. "
                     "Contact the administrator to be registered.")
            st.button("Sign out", on_click=st.logout)
            st.stop()
        return email

    if access.get("password"):                        # cadangan: password bersama
        if st.session_state.get("lolos_password"):
            return st.session_state.get("email_masuk", "")
        st.markdown("<h2 style='text-align:center;margin-top:10vh'>Emplifi Performance "
                    "Dashboard</h2>", unsafe_allow_html=True)
        _, middle, _ = st.columns([1, 1, 1])
        with middle.form("masuk"):
            email = st.text_input("Email").strip().lower()
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", use_container_width=True):
                if (not allowed or email in allowed) and hmac.compare_digest(
                        password.encode(), str(access["password"]).encode()):
                    st.session_state["lolos_password"] = True
                    st.session_state["email_masuk"] = email
                    st.rerun()
                st.error("Incorrect email or password.")
        st.stop()

    st.error("Login settings are incomplete. Please contact the dashboard administrator.")
    st.stop()


SIGNED_IN_EMAIL = login_gate()


# =========================
# AKSI INTERAKTIF (pending)
# =========================

def request_change(change):
    st.session_state["pending"] = change
    st.rerun()


pending = st.session_state.pop("pending", None)
if pending:
    for key, value in pending.items():
        if value is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = value
    for key in CHART_LOCK:
        st.session_state.pop(key, None)


def selected_points(event):
    try:
        return event["selection"]["points"]
    except (KeyError, TypeError):
        return []


SECTION_ICONS = {
    "What happens in social media": "📰", "Performance over time": "📈",
    "Tower › Campaign › Sub Campaign": "🗂️", "Best time to post": "🕒",
    "Content map": "🎯", "Quick rankings": "🏆", "Top content": "⭐",
    "Contribution by platform": "📱", "Contribution by profile": "👤",
    "Brand watch": "📡", "Pillar": "🧱", "Content type": "🎞️", "Media type": "🖼️", "Other labels": "🏷️",
}
HOW_TO_READ = {
    "Performance over time": "A rising line means performance is improving. Turn on comparison to see "
        "the previous period. Tap the chart to see the numbers.",
    "Tower › Campaign › Sub Campaign": "Bigger boxes/bars mean higher results. "
        "Click to filter the whole dashboard to that campaign.",
    "Content map": "Top right = best content (seen by many and highly engaged). "
        "Bottom right = widely seen but rarely engaged.",
    "Brand watch": "An index of 1.5× means those posts get 1.5 times the average "
        "engagement of all posts. All figures come from our own accounts' posts.",
    "Best time to post": "Darker color = higher average result on that day and hour.",
    "What happens in social media": "This summary is generated automatically from the numbers and only shown "
        "when enough posts support it.",
}


def section(title, description, anchor=None):
    if anchor:
        st.markdown(f"<div class='jangkar' id='{anchor}'></div>", unsafe_allow_html=True)
    icon = SECTION_ICONS.get(title, "📊")
    st.markdown(f"<div class='judul-bagian'><span class='ikon'>{icon}</span>"
                f"<span class='teks'>{title}</span></div>"
                f"<div class='sub'>{description}</div>", unsafe_allow_html=True)
    if title in HOW_TO_READ:
        st.markdown(f"<div class='cara'>💡 <b>How to read:</b> {HOW_TO_READ[title]}</div>",
                    unsafe_allow_html=True)


KPI_MEANING = {
    "Content": ("📝", "Number of posts in this period"),
    "Reach": ("👥", "Estimated number of accounts that saw the content"),
    "Impressions": ("👁️", "How many times content was displayed"),
    "Engagements": ("💬", "Likes, comments, shares, and saves"),
    "Engagement rate (impr.)": ("⚡", "Share of impressions that got a response"),
    "Video views": ("▶️", "How many times videos were watched"),
}


KPI_ACCENT = {"Content": "#64748B", "Reach": "#2a78d6", "Impressions": "#1baf7a",
             "Engagements": "#eb6834", "Engagement rate (impr.)": "#6250d6"}


def kpi_card(container, name, value_text, changes):
    icon, meaning = KPI_MEANING.get(name, ("📊", ""))
    accent = KPI_ACCENT.get(name, "#2a78d6")
    if changes is None:
        delta = "<span class='delta datar'>– no comparison yet</span>"
    else:
        css_class = "naik" if changes > 0.0005 else ("turun" if changes < -0.0005 else "datar")
        arrow = {"naik": "▲", "turun": "▼", "datar": "■"}[css_class]
        delta = f"<span class='delta {css_class}'>{arrow} {abs(changes):.1%}<span class='vs'> vs previous period</span></span>"
    title = "Engagement rate" if name.startswith("Engagement rate") else name
    container.markdown(f"<div class='kpi utama' style='--aksen:{accent}'><div class='atas'><span class='ikon'>{icon}</span>{title}</div>"
                   f"<div class='angka'>{value_text}</div><div class='arti'>{meaning}</div>{delta}</div>",
                   unsafe_allow_html=True)


def mini_card(container, title, value, meaning="", delta="", accent="#2a78d6"):
    """Kartu angka dengan gaya yang SAMA seperti kartu KPI (ikon, angka, keterangan, perubahan)."""
    if title[:1] and not title[0].isalnum():
        icon, _, text = title.partition(" ")
    else:
        icon, text = "📊", title
    container.markdown(f"<div class='kpi' style='--aksen:{accent}'><div class='atas'><span class='ikon'>{icon}</span>"
                   f"{text}</div><div class='angka'>{value}</div><div class='arti'>{meaning}</div>{delta}</div>",
                   unsafe_allow_html=True)


def delta_points(now, before, higher_is_better=True):
    """Perubahan dalam poin persen, berwarna sesuai arti (naik baik / naik buruk / netral)."""
    if before is None:
        return "<span class='delta datar'>– no comparison yet</span>"
    d = (now - before) * 100
    if abs(d) < 0.05:
        css_class = "datar"
    elif higher_is_better is None:
        css_class = "datar"
    else:
        css_class = "naik" if (d > 0) == higher_is_better else "turun"
    arrow = "▲" if d > 0.05 else ("▼" if d < -0.05 else "■")
    return f"<span class='delta {css_class}'>{arrow} {abs(d):.1f} pts<span class='vs'> vs previous period</span></span>"


def note_text(text):
    st.markdown(f"<div class='catatan'>{text}</div>", unsafe_allow_html=True)


REPORT_SOURCE = "Emplifi Feed report (emailed to Gmail, updated automatically)"
EMPLIFI_COLUMNS = {"Reach": "Total reach", "Impressions": "Total impressions",
                 "Engagements": "Engagements", "Link clicks": "Link clicks",
                 "Post clicks": "Post clicks", "Video views": "Video view count",
                 "Engagement rate (impr.)": "Engagements ÷ Total impressions",
                 "Engagement rate (reach)": "Engagements ÷ Total reach"}


def source_column(m):
    return EMPLIFI_COLUMNS.get(m, m)


def source(text):
    """Keterangan singkat dari mana data grafik/bagian ini diambil."""
    st.markdown(f"<div class='sumber'>📌 <b>Data source:</b> {text}</div>", unsafe_allow_html=True)


def download_button(df, name, key):
    """Unduhan data DIMATIKAN (dashboard publik). Aktifkan lewat TAMPIL["unduh"] = True."""
    if not SHOW.get("unduh"):
        return
    df = D.excel_ready(df)
    a, b, _ = st.columns([1, 1, 6])
    a.download_button("CSV", df.to_csv(index=False).encode("utf-8-sig"),
                      file_name=f"{name}.csv", mime="text/csv", key=f"csv_{key}")
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    b.download_button("Excel", buffer.getvalue(), file_name=f"{name}.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      key=f"xlsx_{key}")


# =========================
# BAGIAN YANG DITAMPILKAN (dibuat ringkas agar nyaman di HP)
# Ubah ke True untuk memunculkan kembali bagian tersebut.
# =========================
SHOW = {
    "topik": False,          # grafik hashtag / keyword / kategori AI di "What happens"
    "kompetitor": False,     # tab Competitors di Brand watch
    "campaign": False,       # Tower › Campaign › Sub Campaign
    "pillar_format": False,  # Pillar, Other labels, Content type, Media type
    "waktu_peta": False,     # Best time to post & Content map
    "kontribusi": False,     # Contribution by platform & by profile
    "tren": False,           # Performance over time
    "topik_komentar": False, # What the comments are about
    "unduh": False,          # tombol CSV/Excel & ikon unduh tabel (dashboard publik -> mati)
}


# =========================
# DATA + DETEKSI PEMBARUAN
# =========================

# Cache ikut dibuang jika data.py berubah (mencegah data lama tanpa kolom baru).
CODE_VERSION = int(Path(D.__file__).stat().st_mtime)


@st.cache_data(max_entries=2, show_spinner="Loading data...")
def load_data(signature, code_version):
    return D.fetch_data()


def safe_status():
    try:
        return D.fetch_status(), None
    except Exception as error:
        return None, str(error)


status, error_status = safe_status()
if status:
    try:
        content, label = load_data(status["signature"], CODE_VERSION)
        st.session_state["data_valid"] = (content, label, status)
        st.session_state["signature_tampil"] = status["signature"]
    except Exception as error:
        error_status = str(error)

if "data_valid" not in st.session_state:
    print(f"[status] data tidak bisa dimuat: {error_status}")     # detail hanya di log
    st.error("The dashboard data could not be loaded right now. Please try again in a few "
             "minutes. (Administrator: see Manage app → logs for details.)")
    st.stop()

content, label, display_status = st.session_state["data_valid"]
content = D.complete_columns(content)
# Akun kompetitor (dikenali dari nama profil) dipisah: SEMUA bagian lain dashboard hanya
# memakai akun sendiri; kompetitor hanya tampil di tab Kompetitor pada Brand watch.
content, rival = D.split_competitors(content, D.competitor_list(_secrets("kompetitor")))


@st.cache_data(max_entries=2, show_spinner=False)
def load_ai_summary(signature, code_version):
    return D.fetch_ai_summary()


try:
    ai_summary = load_ai_summary(display_status["signature"], CODE_VERSION)
except Exception:
    ai_summary = pd.DataFrame()


def ai_summary_for(scope):
    if ai_summary.empty:
        return None
    x = ai_summary[ai_summary["cakupan"] == scope]
    return None if x.empty else x.iloc[0]


def show_ai_summary(r, content_data):
    start, end = pd.Timestamp(r["periode_awal"]), pd.Timestamp(r["periode_akhir"])
    st.markdown(f"<div class='ai-judul'>🤖 AI summary · {start:%d %b} – {end:%d %b %Y}</div>",
                unsafe_allow_html=True)
    st.markdown(D.refs_to_links(r["teks"], r["rujukan"], content_data))
    note_text("Written by AI (Gemini) from numbers calculated by the system. Before display, "
            "code checks that every number exactly matches the data and every [P] reference is "
            "a real post; if not, the summary is not shown. "
            "Fixed period: last 7 days of data, not affected by filters.")
    with st.expander("View the facts used by the AI (for checking)"):
        try:
            st.json(json.loads(r["fakta"]), expanded=False)
        except (TypeError, ValueError):
            st.write(r["fakta"])


@st.fragment(run_every=UPDATE_CHECK_SECONDS)
def status_panel():
    latest, err = safe_status()
    if latest and latest["signature"] != st.session_state.get("signature_tampil"):
        st.rerun(scope="app")

    info = latest or display_status
    timestamp = info["last_imported_at"]
    ts = pd.Timestamp(timestamp) if timestamp is not None else None
    text = (ts.tz_convert("Asia/Jakarta").strftime("%d %b %Y, %H:%M WIB")
            if ts is not None and ts.tzinfo else (str(timestamp) if timestamp else "–"))
    if err:
        css_class, status = "warn", "Database unreadable"
    elif info.get("last_status") == "failed":
        css_class, status = "gagal", "Last update failed"
    else:
        css_class, status = "ok", "Live · auto-updated"
    account = content["akun"].dropna().nunique()
    platform = _html.escape(", ".join(D.options(content["platform"])[:5]) or "-")
    st.markdown(f"""
<div class="banner">
  <div class="kiri">
    <div class="logo">📊</div>
    <div>
      <div class="eyebrow">Social Media Analytics</div>
      <div class="b-judul">Emplifi Performance Dashboard</div>
      <div class="b-sub">{account} accounts monitored · {platform}</div>
    </div>
  </div>
  <div class="kanan">
    <span class="pill"><span class="titik {css_class}"></span>{status}</span>
    <div class="info">Last update<br><b>{text}</b><br>{info['content_count']:,} posts · checked {datetime.now():%H:%M}</div>
  </div>
</div>""", unsafe_allow_html=True)
    if err:
        print(f"[status] database tidak terbaca: {err}")      # detail hanya di log Manage app
        st.warning("Database cannot be read right now. Showing the last valid data.")
    elif info.get("last_status") == "failed":
        attempt = pd.Timestamp(info["last_attempt_at"]) if info.get("last_attempt_at") else None
        when = attempt.tz_convert("Asia/Jakarta").strftime("%d %b %Y, %H:%M WIB") if attempt is not None and attempt.tzinfo else "-"
        print(f"[status] pembaruan gagal: {info.get('last_pesan')}")   # detail hanya di log
        st.warning(f"The last data update ({when}) did not complete, so the previous valid "
                   "data is shown. The administrator has been notified.")
    elif info.get("db_mb", 0) > 70:
        st.warning(f"Database is {info['db_mb']:.0f} MB (safe limit 70 MB). "
                   "The administrator needs to move storage to the next tier.")
    elif ts is not None and ts.tzinfo:
        age = (datetime.now(timezone.utc) - ts.tz_convert("UTC")).total_seconds() / 3600
        if age > STALE_DATA_HOURS:
            st.warning(f"No new data for {age:.0f} hours. There may be no new report from Emplifi yet.")


# =========================
# HEADER
# =========================

status_panel()

try:                                              # versi portofolio: data fiktif
    from settings import read_config
    DEMO = bool(read_config().get("demo"))
except Exception:
    DEMO = False
if DEMO:
    st.markdown("<div class='sumber'>🧪 <b>Demo:</b> the brand \"Kopi Rimbun\", its accounts, "
                "ambassadors, posts, and all figures are fictional and generated for this portfolio. "
                "AI results are pre-generated with the same validation rules as production. "
                "Post links point to example.com.</div>", unsafe_allow_html=True)
left, right = st.columns([5, 1])
with left:
    note_text("Set the period and filters below, then scroll for details. "
            "Tap or hover over a chart to see the numbers.")
with right:
    st.toggle("🌙 Dark mode", key="mode_gelap",
              help="Switch to a dark theme. Charts and colors adapt too.")
    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if SIGNED_IN_EMAIL:
        note_text(f"Signed in as {SIGNED_IN_EMAIL}")
        if _secrets("auth"):
            st.button("Sign out", on_click=st.logout, use_container_width=True)
        elif st.button("Sign out", use_container_width=True):
            st.session_state.pop("lolos_password", None)
            st.rerun()


# =========================
# PANEL FILTER (atas, bisa disembunyikan)
# =========================

date_min, date_max = D.default_range(content)
if "preset" not in st.session_state:
    st.session_state["preset"] = "All data"

auto_range = D.preset_range(st.session_state["preset"], date_min, date_max)
if auto_range:
    st.session_state["f_tanggal"] = auto_range
elif "f_tanggal" not in st.session_state:
    st.session_state["f_tanggal"] = (date_min, date_max)
else:
    value = st.session_state["f_tanggal"]
    if isinstance(value, (tuple, list)) and len(value) == 2:
        start = min(max(value[0], date_min), date_max)
        st.session_state["f_tanggal"] = (start, min(max(value[1], start), date_max))


def make_custom():
    st.session_state["preset"] = "Custom"


def safe_multiselect(container, title, options, key):
    if key in st.session_state:
        st.session_state[key] = [v for v in st.session_state[key] if v in options]
    return container.multiselect(title, options, key=key, placeholder="All")


with st.expander("⚙️  Filters & period", expanded=False):
    c1, c2 = st.columns([3, 2])
    c1.radio("Period", D.PRESET, key="preset", horizontal=True,
             help=f"Counted from the latest data date ({date_max:%d %b %Y}).")
    date_range = c2.date_input("Posting date", min_value=date_min, max_value=date_max,
                            key="f_tanggal", on_change=make_custom)

    f = {}
    a, b, c, d = st.columns(4)
    f["platform"] = safe_multiselect(a, "Platform", D.options(content["platform"]), "f_platform")
    f["profile"] = safe_multiselect(b, "Account", D.options(content["akun"]), "f_profile")
    f["content_type"] = safe_multiselect(c, "Content type", D.options(content["content_type"]),
                                         "f_content_type")
    f["media_type"] = safe_multiselect(d, "Media type", D.options(content["media_type"]),
                                       "f_media_type")

    a, b, c, d = st.columns(4)
    hier = label[label["label_type"] == "TOWER_CAMPAIGN"]
    f["tower"] = safe_multiselect(a, "Tower", D.options(hier["tower"]), "f_tower")
    if f["tower"]:
        hier = hier[hier["tower"].isin(f["tower"])]
    f["campaign"] = safe_multiselect(b, "Campaign", D.options(hier["campaign"]), "f_campaign")
    if f["campaign"]:
        hier = hier[hier["campaign"].isin(f["campaign"])]
    f["sub_campaign"] = safe_multiselect(c, "Sub Campaign", D.options(hier["sub_campaign"]),
                                         "f_sub_campaign")
    f["pillar"] = safe_multiselect(
        d, "Pillar", D.options(label.loc[label["label_type"] == "PILLAR", "pillar"]), "f_pillar")
    other_options = D.options(label.loc[label["label_type"] == "LAINNYA", "label_lain"])
    if other_options:
        f["label_lain"] = safe_multiselect(
            st, "Other labels", other_options, "f_label_lain")

    a, b, c = st.columns([3, 2, 1])
    search_text = a.text_input(
        "Search", key="f_cari", placeholder="Words in caption, label, or Content ID",
        help="Several words = content containing all of them.")
    metric_list = list(D.METRICS) + list(D.RATIOS)
    if any(SHOW[k] for k in ("kontribusi", "tren", "campaign", "pillar_format", "waktu_peta")):
        metric = b.selectbox("Chart metric", metric_list, index=1, key="metrik")
    else:                                         # tidak ada grafik yang memakai pilihan ini
        metric = st.session_state.get("metrik", "Impressions")
    c.write("")
    if c.button("Reset all", use_container_width=True):
        request_change({**{k: None for k in FILTER_LIST}, "f_tanggal": None,
               "preset": "All data", "f_cari": ""})

if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
    st.info("Select a start and end date.")
    st.stop()
f["tanggal"] = tuple(date_range)

chip = [(k, v) for k in FILTER_LIST for v in st.session_state.get(k, [])]
if chip:
    column = st.columns(min(len(chip), 6))
    for i, (key, value) in enumerate(chip[:6]):
        if column[i].button(f"✕ {FILTER_LIST[key]}: {value}", key=f"chip_{key}_{value}",
                           use_container_width=True):
            request_change({key: [v for v in st.session_state[key] if v != value]})


# =========================
# HITUNG
# =========================

df = D.search(D.filter_content(content, label, f), search_text)
prev_f = {**f, "tanggal": D.previous_period(*f["tanggal"])}
df_prev = D.search(D.filter_content(content, label, prev_f), search_text)

total = D.summary(df)
prev_total = D.summary(df_prev) if not df_prev.empty else None

hier_labels = D.filtered_hierarchy_labels(label, f)
hier_labels = label if hier_labels is None else hier_labels
pill_label = D.filtered_pillar_labels(label, f)
pill_label = label if pill_label is None else pill_label

if df.empty:
    st.info("No content matches these filters.")
    st.stop()


# =========================
# KPI
# =========================

card = ["Content", "Reach", "Impressions", "Engagements", "Engagement rate (impr.)"]
for container, name in zip(st.columns(len(card)), card):
    value = total[name]
    changes = D.change(value, prev_total[name] if prev_total else None)
    kpi_card(container, name, f"{value:,}" if name == "Content" else V.format_value(value, name), changes)
prev_start, prev_end = prev_f["tanggal"]
note_text(f"{f['tanggal'][0]:%d %b %Y} – {f['tanggal'][1]:%d %b %Y}. Change compared with "
        f"{prev_start:%d %b %Y} – {prev_end:%d %b %Y} with the same filters."
        + ("" if prev_total else " No data in the comparison period."))
source(f"{REPORT_SOURCE} · columns Total reach, Total impressions, Engagements, Video view count · "
       "each post counted once, by posting date (Date column).")
st.markdown("<div class='menu'>"
            "<a href='#ringkasan'>📰 Summary</a><a href='#brandwatch'>📡 Brand watch</a>"
            + ("<a href='#tren'>📈 Trend</a>" if SHOW["tren"] else "")
            + ("<a href='#campaign'>🗂️ Campaign</a>" if SHOW["campaign"] else "")
            + ("<a href='#pillar'>🧱 Pillar & format</a>" if SHOW["pillar_format"] else "")
            + ("<a href='#waktu'>🕒 Posting time</a>" if SHOW["waktu_peta"] else "")
            + "<a href='#peringkat'>🏆 Rankings</a><a href='#top'>⭐ Top content</a></div>", unsafe_allow_html=True)


# =========================
# KOMPONEN
# =========================

def contribution_card(column, title, description, key, action):
    with st.container(border=True):
        section(title, description)
        data, used = D.contribution(df, column, metric)
        source(f"{REPORT_SOURCE} · {'Platform' if column == 'platform' else 'Profile name'} "
               f"column + {source_column(used)}, summed per group.")
        kind, reason = V.pick_contribution_visual(len(data))
        if kind == "kosong":
            st.info("No data.")
            return
        if kind == "angka":
            st.metric(str(data.iloc[0][column]), "100%")
        else:
            fig = V.contribution_chart(data, column, used, kind)
            if kind == "bar":
                event = chart(fig, use_container_width=True, key=key,
                                        on_select="rerun", selection_mode="points")
                points = selected_points(event)
                if points and points[0].get("y") is not None:
                    request_change(action(points[0]["y"]))
            else:
                chart(fig, use_container_width=True)
        extra = "" if used == metric else f" Ratios cannot be shown as contribution, so this uses {used}."
        hint = " Tap the chart to see the numbers; use the filters above to narrow down."
        note_text(f"Visual: {reason}.{extra}{hint}")


def breakdown_card(data, column, title, description, total_ref, key, action, additive):
    with st.container(border=True):
        section(title, description)
        kind, reason = V.pick_category_visual(len(data))
        if kind == "kosong":
            st.info("No data.")
            return
        if kind == "angka":
            r = data.iloc[0]
            st.metric(str(r[column]), V.format_value(r[metric], metric),
                      help=f"{int(r['Content'])} posts")
        else:
            event = chart(V.category_chart(data, column, metric, kind),
                                    use_container_width=True, key=key,
                                    on_select="rerun", selection_mode="points")
            points = selected_points(event)
            if points and points[0].get("y") not in (None, D.NO_LABEL):
                request_change(action(points[0]["y"]))
        text = f"Visual: {reason}."
        if not additive and D.breakdown_sum_exceeds_total(data, total_ref, metric):
            text += (" Category values add up to more than the total because some content "
                     "has more than one label; each category's figure is still correct.")
        note_text(text)


def show_detail(content_id):
    row = df[df["content_id"] == content_id]
    if row.empty:
        return
    single = row.iloc[0]
    link = single.get("content_url")
    image = single.get("content_image")
    if isinstance(image, str) and image:
        st.image(image, width=220)
    st.markdown(f"**Content details `{content_id}`**"
                + (f" · [Open post ↗]({link})" if isinstance(link, str) and link else ""))
    if isinstance(link, str) and link:
        note_text(f"Link: {link} (from column '{single.get('kolom_link') or '-'}')")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Reach", V.format_value(single["total_reach"], "Reach"))
    k2.metric("Impressions", V.format_value(single["total_impressions"], "Impressions"))
    k3.metric("Engagements", V.format_value(single["engagements"], "Engagements"))
    er = single["impressions_engagement_rate"]
    k4.metric("ER (impr.) original Emplifi value", "–" if pd.isna(er) else f"{er:g}")
    if pd.notna(single.get("komentar_negatif")) or pd.notna(single.get("komentar_positif")):
        note_text(f"Comments: {int(single.get('komentar_positif') or 0)} positive · "
                f"{int(single.get('komentar_netral') or 0)} neutral · "
                f"{int(single.get('komentar_negatif') or 0)} negative"
                + (f" · post sentiment: {single.get('sentimen')}" if single.get("sentimen") else ""))
    caption_text = str(single.get("caption") or "").strip()
    if caption_text:
        st.markdown(f"> {caption_text[:600]}{'…' if len(caption_text) > 600 else ''}")
    note_text(f"{single['platform']} · {single['profile_name']} · {single['content_type']} / "
            f"{single['media_type']} · posted {single['post_date']} · source {single['source_file']}")
    lbl = label[label["content_id"] == content_id].drop(columns=["content_id"])
    if not lbl.empty:
        st.dataframe(lbl, hide_index=True, use_container_width=True)


# =========================
# KARTU KONTEN (pengganti tabel ala Excel)
# =========================


CARD_METRICS = [("Reach", "total_reach"), ("Impressions", "total_impressions"),
                ("Engagements", "engagements"), ("Video views", "video_views"),
                ("Link clicks", "link_clicks")]


def _card_number(value, name):
    if value is None or pd.isna(value):
        return None
    return V.format_value(float(value), name)


def content_card(row, order, highlight=None, short=False, custom_number=None, extra=""):
    """Satu postingan sebagai kartu: peringkat, thumbnail, akun · platform · tanggal,
    cuplikan caption (klik = buka postingan), dan angka utama."""
    url = row.get("content_url")
    has_link = D._valid_link(url)
    platform = str(row.get("platform") or "")
    color = V.PLATFORM_COLORS.get(platform.lower(), "#64748B")
    date_str = pd.to_datetime(row.get("post_date"), errors="coerce")
    date_str = date_str.strftime("%d %b %Y") if pd.notna(date_str) else "-"
    caption = D.short_text(row.get("caption"), 90 if short else 160) or "(no caption)"
    caption = _html.escape(caption)
    title = (f"<a class='k-cap' href='{_html.escape(url)}' target='_blank' rel='noopener'>{caption}</a>"
             if has_link else f"<div class='k-cap'>{caption}</div>")
    image = row.get("content_image")
    thumb = (f"<div class='k-thumb' style=\"background-image:url('{_html.escape(image)}')\"></div>"
             if isinstance(image, str) and image.startswith("http") and not short else "")
    number = list(custom_number or [])
    items = ([] if custom_number is not None else
              [(highlight, D.METRICS.get(highlight, highlight))] if short and highlight else CARD_METRICS)
    for name, column in items:
        text = _card_number(row.get(column), name)
        if text is None or (name in ("Video views", "Link clicks") and text == "0"):
            continue
        css_class = "k-m utama" if name == highlight else "k-m"
        number.append(f"<span class='{css_class}'><b>{text}</b> {name}</span>")
    if not short and custom_number is None:
        er = row.get("Engagement rate (impr.)")
        if er is not None and pd.notna(er):
            css_class = "k-m utama" if highlight == "Engagement rate (impr.)" else "k-m"
            number.append(f"<span class='{css_class}'><b>{er:.2%}</b> ER</span>")
    open_db = (f"<a class='k-buka' href='{_html.escape(url)}' target='_blank' rel='noopener'>Open ↗</a>"
            if has_link else "")
    return (f"<div class='k-post'><div class='k-rank'>{order}</div>{thumb}<div class='k-isi'>"
            f"<div class='k-meta'><span class='k-chip' style='--c:{color}'>{_html.escape(platform)}</span>"
            f"<span>{_html.escape(str(row.get('akun') or row.get('profile_name') or ''))} · {date_str}</span>{open_db}</div>"
            f"{title}<div class='k-angka'>{''.join(number)}</div>{extra}</div></div>")


def card_list(data, highlight=None, short=False):
    if data.empty:
        st.info("No content for these filters.")
        return
    st.markdown("".join(content_card(r, i, highlight, short)
                        for i, (_, r) in enumerate(data.iterrows(), 1)),
                unsafe_allow_html=True)


def pill(value, label, primary=False):
    return f"<span class='k-m{' utama' if primary else ''}'><b>{value}</b> {label}</span>"


def brand_sentiment_list(data):
    """Per akun: bar persentase positif/netral/negatif + angka, bergaya kartu."""
    w = V.SENTIMENT_COLORS
    row = []
    for _, r in data.iterrows():
        bar = "".join(f"<span style='width:{max(float(r[k]), 0) * 100:.1f}%;background:{w[k]}'></span>"
                      for k in ["Positive", "Neutral", "Negative"])
        number = [pill(f"{r['Positive']:.0%}", "positive"), pill(f"{r['Neutral']:.0%}", "neutral"),
                 pill(f"{r['Negative']:.0%}", "negative", primary=False),
                 pill(f"{int(r['total']):,}", "comments")]
        row.append(f"<div class='k-post'><div class='k-isi'>"
                     f"<div class='k-cap' style='margin-top:0'>{_html.escape(str(r['profile_name']))}</div>"
                     f"<div class='s-bar'>{bar}</div><div class='k-angka'>{''.join(number)}</div>"
                     f"</div></div>")
    st.markdown("".join(row), unsafe_allow_html=True)


def show_comment_topics(result):
    """Positif / netral / negatif: topik postingan yang paling banyak menerima komentar itu."""
    st.markdown("---")
    st.markdown("**What the comments are about**")
    source(f"{REPORT_SOURCE} · comment counts per sentiment (Emplifi classification) × the topic "
           "category of each post (Gemini AI, fixed list). The Feed report contains comment "
           "counts, not comment text, so this shows which post topics received each type of comment.")
    if not result:
        st.info("Appears automatically once posts have AI topic categories "
                "(the Gemini key is active and the daily analysis has run).")
        return
    w = V.SENTIMENT_COLORS
    for tab, name in zip(st.tabs(["😊 Positive", "😐 Neutral", "😟 Negative"]),
                         ["Positive", "Neutral", "Negative"]):
        with tab:
            h = result.get(name)
            if not h:
                st.info(f"Fewer than {D.MIN_BRAND_COMMENTS} {name.lower()} comments on analysed posts.")
                continue
            card = []
            for i, r in enumerate(h["baris"], 1):
                c = r["contoh"]
                url = c.get("content_url")
                text = _html.escape(D.short_text(c.get("caption"), 80) or "(no caption)")
                sample = (f"<a href='{_html.escape(url)}' target='_blank' rel='noopener'>{text}</a>"
                          if D._valid_link(url) else text)
                number = [pill(f"{r['Share']:.0%}", f"of {name.lower()} comments", primary=True),
                         pill(f"{r['Comments']:,}", "comments"), pill(f"{r['Posts']:,}", "posts")]
                card.append(
                    f"<div class='k-post'><div class='k-rank'>{i}</div><div class='k-isi'>"
                    f"<div class='k-cap' style='margin-top:0'>{_html.escape(r['Topic'])}</div>"
                    f"<div class='s-bar'><span style='width:{r['Share'] * 100:.1f}%;"
                    f"background:{w[name]}'></span></div>"
                    f"<div class='k-angka'>{''.join(number)}</div>"
                    f"<div class='k-info'>Most-commented post: {sample}</div></div></div>")
            st.markdown("".join(card), unsafe_allow_html=True)
            if h["cakupan"] is not None and h["cakupan"] < 0.995:
                note_text(f"Covers {h['cakupan']:.0%} of {name.lower()} comments "
                        "(posts not yet analysed by AI are not included).")


def entity_list(data, column_name="Name"):
    """Ringkasan per nama (ambassador/kolaborator) sebagai baris kartu, bukan tabel."""
    row = []
    for i, (_, r) in enumerate(data.iterrows(), 1):
        number = [pill(f"{int(r['Posts']):,}", "posts"),
                 pill(V.format_value(r["Avg. engagements"], "Engagements"), "avg. engagements")]
        if pd.notna(r.get("Index")):
            number.append(pill(f"{r['Index']:.1f}×", "vs average", primary=r["Index"] >= 1))
        if pd.notna(r.get("ER")):
            number.append(pill(f"{r['ER']:.2%}", "ER"))
        if pd.notna(r.get("Negative")):
            number.append(pill(f"{r['Negative']:.0%}", "negative comments"))
        row.append(f"<div class='k-post'><div class='k-rank'>{i}</div><div class='k-isi'>"
                     f"<div class='k-cap' style='margin-top:2px'>{_html.escape(str(r[column_name]))}</div>"
                     f"<div class='k-angka'>{''.join(number)}</div></div></div>")
    st.markdown("".join(row), unsafe_allow_html=True)


# =========================
# WHAT HAPPENS IN SOCIAL MEDIA
# =========================

with st.container(border=True):
    section("What happens in social media",
           "Automatic summary of posts from the brand's own accounts "
           "in the selected period, compared with the previous period", anchor="ringkasan")
    source(f"{REPORT_SOURCE} · post text (Content column), Engagements, Labels, and comment columns "
           "of our own accounts. The AI summary is written by Gemini AI from these figures.")
    r_ai = ai_summary_for("sendiri")
    if r_ai is not None:
        show_ai_summary(r_ai, content)
        st.markdown("---")
    left, right = st.columns([1, 1]) if SHOW["topik"] else (st.container(), None)
    with left:
        st.markdown("**Highlights this period**")
        points = D.highlights(df, df_prev, label)
        if points:
            st.markdown("\n".join(f"- {p}" for p in points))
        else:
            st.info("No highlights are sufficiently supported by data in this period.")
    if right is not None:
        with right:
            if D.has_caption(df):
                topic_choice = (["Category (AI)"] if D.has_ai(df) else []) + ["Hashtag", "Keyword"]
                if st.session_state.get("jenis_topik") not in topic_choice:
                    st.session_state.pop("jenis_topik", None)
                kind = st.radio("Topic", topic_choice, horizontal=True,
                                 key="jenis_topik", label_visibility="collapsed")
                kind_code = {"Category (AI)": "ai", "Hashtag": "hashtag"}.get(kind, "kata")
                topic = D.analyze_topics(df, df_prev, kind_code)
                if topic.empty:
                    st.info(f"No {kind.lower()} in posts this period.")
                else:
                    chart(V.topic_chart(topic, "#" if kind == "Hashtag" else ""),
                                    use_container_width=True)
                    if kind_code == "ai":
                        note_text("Categories are chosen by AI from a fixed list (it cannot invent new "
                                "ones). Posts not yet analysed by AI are not counted.")
            else:
                st.info("Post text is not available in the data, so topic analysis cannot "
                        "be shown yet.")


    note_text("Calculated from our own accounts' post text and figures (not public conversation). "
            f"Highlights are only shown when supported by at least {D.MIN_POSTS} posts. "
            + (" Each post is counted once per topic." if SHOW["topik"] else ""))

    # ----- Sentimen komentar audiens -----
    st.markdown("---")
    st.markdown("**Audience comment sentiment**")
    source("Emplifi's own comment classification · Positive, Neutral, and Negative comments "
           "columns in the Feed report.")
    sen, prev_sen = D.sentiment_summary(df), D.sentiment_summary(df_prev)
    if not D.has_sentiment(df):
        st.info("Comment sentiment data is not available for this period.")
    elif sen is None:
        st.info(f"Classified comments in this period are fewer than {D.MIN_COMMENTS}, "
                "too few to draw conclusions.")
    else:
        def previous(k):
            return prev_sen[k] if prev_sen else None
        k1, k2, k3, k4 = st.columns(4)
        mini_card(k1, "😊 Positive", f"{sen['pos%']:.0%}", "of classified comments",
                   delta_points(sen["pos%"], previous("pos%"), True), accent="#16A34A")
        mini_card(k2, "😐 Neutral", f"{sen['netral%']:.0%}", "of classified comments",
                   delta_points(sen["netral%"], previous("netral%"), None), accent="#94A3B8")
        mini_card(k3, "😟 Negative", f"{sen['neg%']:.0%}", "of classified comments",
                   delta_points(sen["neg%"], previous("neg%"), False), accent="#DC2626")
        mini_card(k4, "⚖️ Net sentiment", f"{sen['net']:+.0%}", "positive minus negative",
                   delta_points(sen["net"], previous("net"), True))
        st.write("")

        left, right = st.columns([1, 1])
        with left:
            per_brand = D.sentiment_per_brand(df)
            if len(per_brand) >= 1:
                st.markdown("**Sentiment by account**")
                brand_sentiment_list(per_brand)
            else:
                note_text(f"No brand has at least {D.MIN_BRAND_COMMENTS} classified comments yet.")
        with right:
            st.markdown("**Most-commented posts by sentiment**")
            account_options = ["All"] + [a for a in D.TP.ACCOUNT_ORDER if a in set(df["akun"])]
            sent_options = ["😟 Negative", "😊 Positive", "😐 Neutral"]
            for key, options in [("akun_sentimen", account_options), ("arah_sentimen", sent_options)]:
                if st.session_state.get(key) not in options:
                    st.session_state[key] = options[0]
            selected_account = st.segmented_control("Account", account_options, key="akun_sentimen",
                                              label_visibility="collapsed") or "All"
            direction = st.segmented_control("Sentiment", sent_options, key="arah_sentimen",
                                        label_visibility="collapsed") or sent_options[0]
            kind = direction.split(" ", 1)[1]                     # Negative / Positive / Neutral
            col_k = D.SENTIMENTS[kind]
            account_source = df if selected_account == "All" else df[df["akun"] == selected_account]
            items = account_source[account_source[col_k].fillna(0) > 0].nlargest(5, col_k)
            if items.empty:
                st.info(f"No posts with {kind.lower()} comments"
                        + ("" if selected_account == "All" else f" on {selected_account}") + " in this period.")
            else:
                sent_col = list(D.SENTIMENTS.values())
                card = []
                for i, (_, r) in enumerate(items.iterrows(), 1):
                    total_k = sum(float(r[k]) for k in sent_col if pd.notna(r[k]))
                    number = [pill(f"{int(r[col_k]):,}", f"{kind.lower()} comments", primary=True)]
                    if total_k:
                        number.append(pill(f"{r[col_k] / total_k:.0%}", "of its comments"))
                        number.append(pill(f"{int(total_k):,}", "classified comments"))
                    card.append(content_card(r, i, short=True, custom_number=number))
                st.markdown("".join(card), unsafe_allow_html=True)
                note_text("Tap a post to open it on its platform.")
        if SHOW["topik_komentar"]:
            show_comment_topics(D.comment_topics(df))
        note_text(f"Sentiment classification from Emplifi. Percentages are based on the number of "
                f"classified comments ({int(sen['total']):,} comments), compared with the previous period. "
                f"Brand comparison only covers brands with at least {D.MIN_BRAND_COMMENTS} comments.")


# =========================
# BRAND WATCH: aplikasi brand dan brand ambassador
# =========================

def entity_table(data, title_name):
    entity_list(data)


def entity_chart(data, key):
    if len(data) >= 2:
        g = data.rename(columns={"Posts": "Content"})
        chart(V.category_chart(g, "Name", "Engagements",
                                 "bar" if len(g) <= V.BAR_LIMIT else "bar_top"),
               use_container_width=True, key=key)


def mention_table(data, mask, origin, name, key, n=10):
    """Postingan yang menyebut 'nama' sebagai kartu + cara terdeteksinya (bisa diaudit)."""
    x = data[mask].copy()
    if x.empty:
        return
    x["_asal"] = origin[mask]
    x["_kutipan"] = D.ai_evidence(x, name)
    x = x.nlargest(n, "engagements")
    card = []
    for i, (_, r) in enumerate(x.iterrows(), 1):
        number = [pill(V.format_value(r["engagements"], "Engagements"), "Engagements", primary=True)]
        imp_text = _card_number(r.get("total_impressions"), "Impressions")
        if imp_text:
            number.append(pill(imp_text, "Impressions"))
        info = f"<div class='k-info'>Detected via: <b>{_html.escape(str(r['_asal']))}</b>"
        if isinstance(r["_kutipan"], str) and r["_kutipan"]:
            info += f" · AI quote: “{_html.escape(r['_kutipan'])}”"
        card.append(content_card(r, i, short=True, custom_number=number, extra=info + "</div>"))
    st.markdown("".join(card), unsafe_allow_html=True)


watch = D.watch_list(_secrets("pantau"))
with st.container(border=True):
    section("Brand watch",
           "The brand app, brand ambassadors, and collaborators "
           "in the selected period and filters", anchor="brandwatch")
    tab_brand = st.tabs(["📱 Rimbun App", "⭐ Ambassadors", "🤝 Collaborators"]
                        + (["🆚 Competitors"] if SHOW["kompetitor"] else []))
    tab_app, tab_amb, tab_collab = tab_brand[:3]
    tab_comp = tab_brand[3] if SHOW["kompetitor"] else None

    # ----- Aplikasi brand -----
    with tab_app:
        source(f"{REPORT_SOURCE} · post text (Content), Labels, and Collaborators columns, "
               "matched with app keywords + an AI check (Gemini) with verified quotes.")
        mask, origin = D.mentions(df, "Rimbun App", watch["app"])
        r = D.summarize_topics(df, mask)
        if r is None:
            st.info("No posts mention Rimbun App in this period and filters.")
        else:
            sentences = D.topic_sentence("Rimbun App", r)
            if sentences:
                st.markdown(sentences)
            a, b, c, d = st.columns(4)
            mini_card(a, "📝 Posts", f"{r['Posts']:,}", f"{r['Share']:.0%} of all posts")
            mini_card(b, "💬 Avg. engagements", V.format_value(r["Avg. engagements"], "Engagements"),
                       "per Rimbun App post")
            mini_card(c, "📊 Index", f"{r['Index']:.1f}×" if r.get("Index") else "–",
                       "vs average of all posts")
            mini_card(d, "😟 Negative comments", f"{r['Negative']:.0%}" if r.get("Negative") is not None else "–",
                       "of classified comments" if r.get("Negative") is not None
                       else f"too few comments (< {D.MIN_BRAND_COMMENTS})")
            st.write("")
            st.markdown("**Top Rimbun App posts by engagement**")
            mention_table(df, mask, origin, "Rimbun App", "t_app")
        note_text("Detected from captions, labels, and collaborators using keywords ("
                + ", ".join(watch["app"]) + "), plus AI findings backed by "
                "caption quotes verified by code.")

    # ----- Brand ambassador -----
    with tab_amb:
        source(f"{REPORT_SOURCE} · post text (Content), Labels, and Collaborators columns, "
               "matched with each ambassador's name + an AI check (Gemini) with verified quotes.")
        amb_result = []
        for name, words in watch["ambassador"].items():
            m, src = D.mentions(df, name, words)
            amb_result.append((name, m, src, D.summarize_topics(df, m)))
        amb_col = st.columns(max(1, min(len(amb_result), 3)))
        for i, (name, m, src, r) in enumerate(amb_result):
            note = D.DESCRIPTIONS.get(name, "")
            if r is None:
                mini_card(amb_col[i % len(amb_col)], f"⭐ {name}", "0 posts",
                           f"{note}<br>not mentioned in this period")
            else:
                details = [f"{V.format_value(r['Avg. engagements'], 'Engagements')} engagements/post"]
                if r.get("Index"):
                    details.append(f"{r['Index']:.1f}× average")
                if r.get("ER") is not None and pd.notna(r.get("ER")):
                    details.append(f"ER {r['ER']:.2%}")
                if r.get("Negative") is not None:
                    details.append(f"{r['Negative']:.0%} negative comments")
                mini_card(amb_col[i % len(amb_col)], f"⭐ {name}",
                           f"{r['Posts']:,} posts", f"{note}<br>{' · '.join(details)}")
        st.write("")
        found = [h for h in amb_result if h[1].any()]
        if not found:
            st.info("No posts mention a brand ambassador in this period and filters.")
        else:
            amb_options = [h[0] for h in found]
            if st.session_state.get("pilih_amb") not in amb_options:
                st.session_state.pop("pilih_amb", None)
            pick = st.radio("View posts", amb_options, horizontal=True, key="pilih_amb")
            for name, m, src, _ in found:
                if name == pick:
                    mention_table(df, m, src, name, f"t_amb_{name}")
        note_text("Clear keywords (e.g. \"wening asmara\", \"bagas jenggala\") are counted directly. "
                "Ambiguous mentions like \"Tara\" (also the Indonesian \"ta-da!\") are only counted if "
                "the AI confirms them and the quote really exists in the caption. \"Detected via\" under each post "
                "shows where each finding came from. One post can mention more than one name.")

    # ----- Kolaborator -----
    with tab_collab:
        source(f"{REPORT_SOURCE} · Collaborators column (collab posts tagged on the platform).")
        col = D.collaborators(df)
        if col.empty:
            st.info("No collaboration posts in this period and filters.")
        else:
            entity_table(col, "Collaborator")
        note_text("Taken automatically from the Collaborators column in the Emplifi report (actual data, not guesses).")

    # ----- Kompetitor -----
    if tab_comp is not None:
        with tab_comp:
            comp = D.filter_rivals(rival, f, search_text)
            if rival.empty:
                st.info("No competitor account data in the Emplifi reports yet. Once competitor accounts "
                        "(e.g. Kopi Senja, Teh Lembah, Kopi Kilat) are added to the Feed report "
                        "sent to Gmail, this section fills in automatically.")
            elif comp.empty:
                st.info("No competitor posts in this period and filters.")
            else:
                r_k = ai_summary_for("kompetitor")
                if r_k is not None:
                    show_ai_summary(r_k, rival)
                    st.markdown("---")
                table_b, platform_b = D.compare_brands(df, comp)
                st.markdown(f"**Share of Total interactions by brand** · platform: {', '.join(platform_b)}")
                chart(V.brand_chart(table_b, D.TP.OWN_COMPETITOR_LABEL), use_container_width=True,
                       key="c_brand")
                shown_b = table_b.copy()
                for k in ["Interaction share", "Post share"]:
                    shown_b[k] = shown_b[k] * 100
                st.dataframe(shown_b, hide_index=True, use_container_width=True, column_config={
                    "Interactions": st.column_config.NumberColumn(format="%d"),
                    "Interactions per post": st.column_config.NumberColumn(format="%d"),
                    "Interaction share": st.column_config.ProgressColumn(
                        format="%.0f%%", min_value=0, max_value=100),
                    "Post share": st.column_config.NumberColumn(format="%.0f%%"),
                })
                t_brand = D.topics_per_brand(df, comp, platform_b)
                if not t_brand.empty:
                    st.markdown("**What each brand talks about** (AI topic categories, share of posts)")
                    st.dataframe((t_brand * 100).round(0), use_container_width=True,
                                 column_config={c: st.column_config.NumberColumn(format="%.0f%%")
                                                for c in t_brand.columns})
                st.markdown("**Top competitor posts by interactions**")
                top_k = D.rival_posts(comp)
                all_links = bool(top_k["punya_link"].all())
                st.dataframe(
                    top_k.drop(columns=["punya_link"] + ([] if all_links else ["Content"])),
                    hide_index=True, use_container_width=True, key="t_komp", column_config={
                        "brand": "Brand", "profile_name": "Account", "platform": "Platform",
                        "Content": st.column_config.LinkColumn(
                            "Post (click to open)", display_text=r"#konten=(.*)$", width="large"),
                        "ai_topik": "Topic (AI)",
                        "total_interactions": st.column_config.NumberColumn("Interactions", format="%d"),
                    })
            note_text("Competitors are identified by ACCOUNT NAME in the Emplifi report, not by caption text, "
                    "so own posts that mention competitors are not counted. Competitors' public "
                    "accounts have no reach/impressions, so the comparison uses Total "
                    "interactions and only on platforms available for competitors. Competitor "
                    "data is never included in KPIs, charts, or other tables on the dashboard.")


# =========================
# 1. KONTRIBUSI PLATFORM & PROFILE
# =========================

if SHOW["kontribusi"]:
    left, right = st.columns(2)
    with left:
        contribution_card("platform", "Contribution by platform",
                         f"Each platform's share of total {metric if metric in D.METRICS else 'Impressions'} in the selected period",
                         "c_platform", lambda v: {"f_platform": [v]})
    with right:
        contribution_card("profile_name", "Contribution by profile",
                         "Each account's share of the total in the selected period",
                         "c_profile", lambda v: {"f_profile": [v]})


# =========================
# 2. TREN
# =========================

if SHOW["tren"]:
    with st.container(border=True):
        section("Performance over time",
               f"{metric} per period by content posting date", anchor="tren")
        source(f"{REPORT_SOURCE} · {source_column(metric)}, grouped by posting date (Date column).")
        auto, granularity_reason = V.pick_granularity(*f["tanggal"])
        a, b = st.columns([3, 2])
        choice = a.radio("Granularity", ["Auto", "Daily", "Weekly", "Monthly"],
                          horizontal=True, key="granularitas", label_visibility="collapsed")
        comparison = b.toggle("Compare with previous period", key="banding")
        gran = auto if choice == "Auto" else choice

        trend_data = D.trend(df, metric, gran)
        kind, reason = V.pick_trend_visual(len(trend_data))
        if kind == "kosong":
            st.info("No data.")
        elif comparison:
            chart(V.comparison_trend_chart(trend_data, D.trend(df_prev, metric, gran), metric),
                            use_container_width=True)
        elif kind == "angka":
            st.metric(str(trend_data.iloc[0]["periode"].date()),
                      V.format_value(trend_data.iloc[0][metric], metric))
        else:
            event = chart(V.trend_chart(trend_data, metric, kind),
                                    use_container_width=True, key="c_tren",
                                    on_select="rerun", selection_mode="points")
            points = selected_points(event)
            if points and points[0].get("x") is not None:
                start, end = D.period_range(points[0]["x"], gran, date_min, date_max)
                request_change({"preset": "Custom", "f_tanggal": (start, end)})
        if not trend_data.empty:
            download_button(trend_data.assign(periode=trend_data["periode"].dt.date),
                         f"tren_{metric}_{gran}".replace(" ", "_"), "tren")
        note_text(f"Visual: {reason}. Auto granularity: {granularity_reason}."
                )


# =========================
# 3. TOWER > CAMPAIGN > SUB CAMPAIGN (menyatu)
# =========================

if SHOW["campaign"]:
    with st.container(border=True):
        section("Tower › Campaign › Sub Campaign",
               "All three levels in one view. Each piece of content is counted once per category.", anchor="campaign")
        source(f"{REPORT_SOURCE} · Labels column in the format Tower - Campaign - Sub Campaign.")
        h_tower, h_camp, h_sub, additive = D.hierarchy(df, hier_labels)
        path_count = int((h_sub["tower"] != D.NO_LABEL).sum())
        recommendation, reason = V.pick_hierarchy_visual(additive, path_count)

        view_choice = ["Treemap", "Bar per path", "Table per Sub Campaign", "Nested table"]
        default = {"treemap": 0, "bar": 1, "kosong": 2}[recommendation]
        view = st.radio("View", view_choice, index=default, horizontal=True,
                            key="tampilan_hier", label_visibility="collapsed")

        size_column = {"Reach": "Reach", "Impressions": "Impressions",
                        "Engagements": "Engagements"}.get(metric, "Impressions")
        bar_col = "ER (impr.)" if metric == "Engagement rate (impr.)" else size_column

        if path_count == 0:
            st.info("Content in these filters has no Tower–Campaign–Sub Campaign labels.")
        elif view == "Treemap":
            if additive:
                chart(V.treemap_chart(h_tower, h_camp, h_sub, size_column),
                                use_container_width=True)
                note_text(f"Box size = {size_column}, color = Engagement rate. "
                        "Click a box to drill down, click the title above to go back.")
            else:
                st.warning("Treemap not shown: some content has more than one label "
                           "path, so Tower and Campaign figures would be double-counted. "
                           "Use 'Bar per path' or 'Nested table'.")
        elif view == "Bar per path":
            event = chart(V.path_chart(h_sub, bar_col, metric),
                                    use_container_width=True, key="c_jalur",
                                    on_select="rerun", selection_mode="points")
            points = selected_points(event)
            if points and points[0].get("customdata"):
                t, c, s = points[0]["customdata"][:3]
                request_change({"f_tower": [t], "f_campaign": [c], "f_sub_campaign": [s]})
            note_text("Each bar = one Campaign › Sub Campaign path, color = Tower. "
                    "Click a bar to filter to that path.")
        else:
            if view == "Table per Sub Campaign":
                table = D.path_table(h_sub)
                table_key, note = "t_jalur", "One row = one Tower › Campaign › Sub Campaign path."
            else:
                table = D.hierarchy_table(h_tower, h_camp, h_sub)
                table_key, note = "t_hier", ("Tower and Campaign rows are level totals; "
                                              "Sub Campaign rows are the breakdown.")
            shown = table.copy()
            shown["ER (impr.)"] = shown["ER (impr.)"] * 100
            event = st.dataframe(
                shown, hide_index=True, use_container_width=True, key=table_key,
                on_select="rerun", selection_mode="single-row",
                height=min(600, 38 + 35 * len(shown)),
                column_config={
                    "Reach": st.column_config.NumberColumn(format="%d"),
                    "Impressions": st.column_config.NumberColumn(format="%d"),
                    "Engagements": st.column_config.NumberColumn(format="%d"),
                    "ER (impr.)": st.column_config.NumberColumn(format="%.2f%%"),
                })
            try:
                row = event["selection"]["rows"]
            except (KeyError, TypeError):
                row = []
            if row:
                r = table.iloc[row[0]]
                if r["Tower"] != D.NO_LABEL:
                    request_change({"f_tower": [r["Tower"]],
                           "f_campaign": [r["Campaign"]] if r["Campaign"] else [],
                           "f_sub_campaign": [r["Sub Campaign"]] if r["Sub Campaign"] else []})
            download_button(table, "tower_campaign_sub_campaign", table_key)
            note_text(f"{note} Click a row to filter the dashboard to it.")
        note_text(f"Auto recommendation: {reason}.")


# =========================
# 4. PILLAR & FORMAT
# =========================

if SHOW["pillar_format"]:
    st.markdown("<div class='jangkar' id='pillar'></div>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        breakdown_card(D.label_breakdown(df, pill_label, "pillar", metric, "PILLAR"), "pillar",
                        "Pillar", f"{metric} per content pillar", total[metric], "c_pillar",
                        lambda v: {"f_pillar": [v]}, False)
        if (label["label_type"] == "LAINNYA").any():
            breakdown_card(D.label_breakdown(df, label, "label_lain", metric, "LAINNYA"),
                            "label_lain", "Other labels",
                            f"{metric} per label not in Pillar or "
                            "Tower - Campaign - Sub Campaign format", total[metric], "c_lain",
                            lambda v: {"f_label_lain": [v]}, False)
    with right:
        breakdown_card(D.attribute_breakdown(df, "content_type", metric), "content_type",
                        "Content type", f"{metric} per content type", total[metric], "c_ctype",
                        lambda v: {"f_content_type": [v]}, True)
        breakdown_card(D.attribute_breakdown(df, "media_type", metric), "media_type",
                        "Media type", f"{metric} per media type", total[metric], "c_mtype",
                        lambda v: {"f_media_type": [v]}, True)


# =========================
# 5. WAKTU POSTING & PETA KONTEN
# =========================

if SHOW["waktu_peta"]:
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            unit = "recalculated from totals" if V.is_ratio(metric) else "average per content"
            section("Best time to post",
                   f"{metric} by posting day and hour (WIB), {unit}", anchor="waktu")
            source(f"{REPORT_SOURCE} · Date column (posting time, WIB) + {source_column(metric)}.")
            timestamp = D.local_time(df["posted_at"])
            kind, reason = V.pick_time_visual(D.has_time_of_day(timestamp), int(timestamp.notna().sum()))
            if kind == "kosong":
                st.info("No posting time data.")
            elif kind == "heatmap":
                chart(V.heatmap_chart(D.post_time(df, metric), metric, D.WEEKDAYS),
                                use_container_width=True)
            else:
                chart(V.day_chart(D.per_day(df, metric), metric),
                                use_container_width=True)
            note_text(f"Visual: {reason}. Slots with little content are not conclusive.")

    with right:
        with st.container(border=True):
            section("Content map", "Impressions vs Engagement rate per content; dashed lines = median")
            source(f"{REPORT_SOURCE} · Total impressions and Engagements per post.")
            map_data = D.content_map(df)
            kind, log_x, reason = V.pick_map_visual(map_data)
            selected = None
            if kind == "kosong":
                st.info("No content with Impressions > 0.")
            elif kind == "tabel":
                st.dataframe(map_data[["content_id", "total_impressions", "er"]],
                             hide_index=True, use_container_width=True)
            else:
                event = chart(V.map_chart(map_data, log_x), use_container_width=True,
                                        key="c_peta", on_select="rerun", selection_mode="points")
                points = selected_points(event)
                if points and points[0].get("customdata"):
                    selected = points[0]["customdata"][0]
            note_text(f"Visual: {reason}. Click a point to see details.")
            if selected:
                show_detail(selected)


# =========================
# 6. PERINGKAT CEPAT
# =========================

with st.container(border=True):
    section("Quick rankings",
           "Top 5 content for each metric in the selected period and filters", anchor="peringkat")
    source(f"{REPORT_SOURCE} · per-post metric columns; post links from the "
           "View on platform column.")
    found, is_empty = D.available_metrics(df)
    if not found:
        st.info("No content with metric values for these filters.")
    else:
        for tab, name in zip(st.tabs(found), found):
            with tab:
                column = D.METRICS[name]
                data = df[df[column].fillna(0) > 0].nlargest(5, column)
                card_list(data, highlight=name, short=True)
    text = "Tap the post text to open it on its platform."
    if not D.has_link(df):
        text = "Post links are not available yet, so posts cannot be opened."
    if is_empty:
        text += f" Not shown because there is no data for these filters: {', '.join(is_empty)}."
    note_text(text)


# =========================
# 7. TOP KONTEN
# =========================

with st.container(border=True):
    section("Top content",
           "Content ranked by the selected metric", anchor="top")
    source(f"{REPORT_SOURCE} · one post per Content ID with its Emplifi figures; "
           "post links from the View on platform column.")
    sort_choice = D.RANKING + list(D.RATIOS)
    if st.session_state.get("urut_konten") not in sort_choice:
        st.session_state["urut_konten"] = metric if metric in sort_choice else "Impressions"
    a, b = st.columns([3, 1])
    sort_by = a.selectbox("Sort by", sort_choice, key="urut_konten")
    count = b.selectbox("Show", [10, 25, 50], index=0, key="jumlah_konten")

    table = df.copy()
    for name_r, (top, bottom) in D.RATIOS.items():
        table[name_r] = table[top] / table[bottom].where(table[bottom] != 0)
    table = table.sort_values(D.METRICS.get(sort_by, sort_by), ascending=False,
                              na_position="last").head(count).reset_index(drop=True)
    card_list(table, highlight=sort_by)
    download_button(df.drop(columns=["labels_raw"], errors="ignore"),
                 f"emplifi_konten_{f['tanggal'][0]:%Y%m%d}_{f['tanggal'][1]:%Y%m%d}", "konten")
    note_text("Tap the post text or 'Open ↗' to view the post.")


# =========================
# DEFINISI + FOOTER
# =========================

with st.expander("Metric definitions"):
    st.markdown("""
- **Reach** = sum of per-content reach from Emplifi, **not** unique people.
- **Engagement rate** on cards and charts = Σ Engagements ÷ Σ Impressions (or ÷ Σ Reach).
- **Totals** are always calculated from unique content; nothing is counted twice.
- **Tower, Campaign, Sub Campaign, and Pillar** are not additive: one piece of content can have several
  labels. The treemap is only shown when each piece of content belongs to one path.
- **Contribution** is only shown for Platform and Profile, because each piece of content has exactly one value.
- **Posting time** uses the average per piece of content for count metrics.
- **Quick periods** are counted from the latest data date and move forward when new data arrives.
- **Light/dark theme**: use the Dark mode switch at the top.
""")

st.markdown("<div class='footer'>Data source: Emplifi reports, updated automatically. "
            "Confidential data; do not share without permission.</div>",
            unsafe_allow_html=True)
