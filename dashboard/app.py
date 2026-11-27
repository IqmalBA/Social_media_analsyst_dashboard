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

CEK_PEMBARUAN_DETIK = 60
BATAS_DATA_LAMA_JAM = 36

FILTER_LIST = {
    "f_platform": "Platform", "f_profile": "Profile", "f_tower": "Tower",
    "f_campaign": "Campaign", "f_sub_campaign": "Sub Campaign",
    "f_pillar": "Pillar", "f_label_lain": "Other labels", "f_content_type": "Content type",
    "f_media_type": "Media type",
}
KUNCI_GRAFIK = ["c_lain", "c_platform", "c_jalur", "t_jalur", "c_pillar", "c_ctype", "c_mtype", "c_tren",
                "c_peta", "t_konten", "t_hier", "c_profile"]

GELAP = bool(st.session_state.get("mode_gelap", False))

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


def grafik(fig, *args, **kwargs):
    """Semua grafik: ikut mode terang/gelap, dan DIAM saat disentuh (nyaman di HP):
    tanpa zoom/geser/toolbar, legenda tidak bisa diklik, ketukan tidak memfilter dashboard.
    Mengetuk/mengarahkan kursor tetap menampilkan angka."""
    kwargs.setdefault("theme", None)
    kwargs.pop("on_select", None)
    kwargs.pop("selection_mode", None)
    kwargs.setdefault("config", {"displayModeBar": False, "scrollZoom": False,
                                 "doubleClick": False, "showTips": False, "responsive": True})
    fig = V.terapkan_tema(fig, GELAP)
    fig.update_layout(dragmode=False, hovermode="closest" if fig.layout.hovermode is None
                      else fig.layout.hovermode,
                      legend=dict(itemclick=False, itemdoubleclick=False))
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return st.plotly_chart(fig, *args, **kwargs)

# Mode gelap: menimpa warna latar, kartu, teks, dan input
if GELAP:
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


def _secrets(nama):
    try:
        return st.secrets.get(nama)
    except Exception:
        return None


def _pengguna():
    return getattr(st, "user", None) or getattr(st, "experimental_user", None)


def gerbang_login():
    akses = _secrets("akses")
    if not akses:
        return None                                  # mode lokal: tanpa login
    izin = [e.strip().lower() for e in akses.get("email", []) if e.strip()]

    kunci_sah = akses.get("kunci_link") or []
    if isinstance(kunci_sah, str):
        kunci_sah = [kunci_sah]
    if kunci_sah:                                    # link rahasia: tanpa login
        if st.session_state.get("lolos_kunci"):
            return None
        kunci = str(st.query_params.get("kunci", "")).strip()
        if kunci and any(hmac.compare_digest(kunci.encode(), str(k).encode())
                         for k in kunci_sah if str(k).strip()):
            st.session_state["lolos_kunci"] = True
            return None
        if not (_secrets("auth") or akses.get("password")):
            st.markdown("<div style='max-width:460px;margin:18vh auto;text-align:center'>"
                        "<h2>Emplifi Performance Dashboard</h2>"
                        "<p style='opacity:.7'>This link is invalid or has expired. "
                        "Please ask the dashboard administrator for the latest link.</p></div>",
                        unsafe_allow_html=True)
            st.stop()

    if _secrets("auth"):                             # login Google
        user = _pengguna()
        if not getattr(user, "is_logged_in", False):
            st.markdown("<div style='max-width:420px;margin:12vh auto;text-align:center'>"
                        "<h2>Emplifi Performance Dashboard</h2>"
                        "<p style='opacity:.7'>Sign in with a registered Google account.</p>"
                        "</div>", unsafe_allow_html=True)
            _, tengah, _ = st.columns([2, 1, 2])
            tengah.button("Sign in with Google", on_click=st.login,
                          type="primary", use_container_width=True)
            st.stop()
        email = (getattr(user, "email", "") or "").lower()
        if izin and email not in izin:
            st.error(f"Account {email} does not have access to this dashboard. "
                     "Contact the administrator to be registered.")
            st.button("Sign out", on_click=st.logout)
            st.stop()
        return email

    if akses.get("password"):                        # cadangan: password bersama
        if st.session_state.get("lolos_password"):
            return st.session_state.get("email_masuk", "")
        st.markdown("<h2 style='text-align:center;margin-top:10vh'>Emplifi Performance "
                    "Dashboard</h2>", unsafe_allow_html=True)
        _, tengah, _ = st.columns([1, 1, 1])
        with tengah.form("masuk"):
            email = st.text_input("Email").strip().lower()
            sandi = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", use_container_width=True):
                if (not izin or email in izin) and hmac.compare_digest(
                        sandi.encode(), str(akses["password"]).encode()):
                    st.session_state["lolos_password"] = True
                    st.session_state["email_masuk"] = email
                    st.rerun()
                st.error("Incorrect email or password.")
        st.stop()

    st.error("Login settings are incomplete. Please contact the dashboard administrator.")
    st.stop()


EMAIL_MASUK = gerbang_login()


# =========================
# AKSI INTERAKTIF (pending)
# =========================

def minta(perubahan):
    st.session_state["pending"] = perubahan
    st.rerun()


pending = st.session_state.pop("pending", None)
if pending:
    for kunci, nilai in pending.items():
        if nilai is None:
            st.session_state.pop(kunci, None)
        else:
            st.session_state[kunci] = nilai
    for kunci in KUNCI_GRAFIK:
        st.session_state.pop(kunci, None)


def poin_terpilih(event):
    try:
        return event["selection"]["points"]
    except (KeyError, TypeError):
        return []


IKON_BAGIAN = {
    "What happens in social media": "📰", "Performance over time": "📈",
    "Tower › Campaign › Sub Campaign": "🗂️", "Best time to post": "🕒",
    "Content map": "🎯", "Quick rankings": "🏆", "Top content": "⭐",
    "Contribution by platform": "📱", "Contribution by profile": "👤",
    "Brand watch": "📡", "Pillar": "🧱", "Content type": "🎞️", "Media type": "🖼️", "Other labels": "🏷️",
}
CARA_MEMBACA = {
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


def bagian(judul, keterangan, jangkar=None):
    if jangkar:
        st.markdown(f"<div class='jangkar' id='{jangkar}'></div>", unsafe_allow_html=True)
    ikon = IKON_BAGIAN.get(judul, "📊")
    st.markdown(f"<div class='judul-bagian'><span class='ikon'>{ikon}</span>"
                f"<span class='teks'>{judul}</span></div>"
                f"<div class='sub'>{keterangan}</div>", unsafe_allow_html=True)
    if judul in CARA_MEMBACA:
        st.markdown(f"<div class='cara'>💡 <b>How to read:</b> {CARA_MEMBACA[judul]}</div>",
                    unsafe_allow_html=True)


ARTI_KPI = {
    "Content": ("📝", "Number of posts in this period"),
    "Reach": ("👥", "Estimated number of accounts that saw the content"),
    "Impressions": ("👁️", "How many times content was displayed"),
    "Engagements": ("💬", "Likes, comments, shares, and saves"),
    "Engagement rate (impr.)": ("⚡", "Share of impressions that got a response"),
    "Video views": ("▶️", "How many times videos were watched"),
}


AKSEN_KPI = {"Content": "#64748B", "Reach": "#2a78d6", "Impressions": "#1baf7a",
             "Engagements": "#eb6834", "Engagement rate (impr.)": "#6250d6"}


def kartu_kpi(wadah, nama, teks_nilai, ubah):
    ikon, arti = ARTI_KPI.get(nama, ("📊", ""))
    aksen = AKSEN_KPI.get(nama, "#2a78d6")
    if ubah is None:
        delta = "<span class='delta datar'>– no comparison yet</span>"
    else:
        kelas = "naik" if ubah > 0.0005 else ("turun" if ubah < -0.0005 else "datar")
        panah = {"naik": "▲", "turun": "▼", "datar": "■"}[kelas]
        delta = f"<span class='delta {kelas}'>{panah} {abs(ubah):.1%}<span class='vs'> vs previous period</span></span>"
    judul = "Engagement rate" if nama.startswith("Engagement rate") else nama
    wadah.markdown(f"<div class='kpi utama' style='--aksen:{aksen}'><div class='atas'><span class='ikon'>{ikon}</span>{judul}</div>"
                   f"<div class='angka'>{teks_nilai}</div><div class='arti'>{arti}</div>{delta}</div>",
                   unsafe_allow_html=True)


def kartu_mini(wadah, judul, nilai, arti="", delta="", aksen="#2a78d6"):
    """Kartu angka dengan gaya yang SAMA seperti kartu KPI (ikon, angka, keterangan, perubahan)."""
    if judul[:1] and not judul[0].isalnum():
        ikon, _, teks = judul.partition(" ")
    else:
        ikon, teks = "📊", judul
    wadah.markdown(f"<div class='kpi' style='--aksen:{aksen}'><div class='atas'><span class='ikon'>{ikon}</span>"
                   f"{teks}</div><div class='angka'>{nilai}</div><div class='arti'>{arti}</div>{delta}</div>",
                   unsafe_allow_html=True)


def delta_poin(sekarang, sebelum, naik_baik=True):
    """Perubahan dalam poin persen, berwarna sesuai arti (naik baik / naik buruk / netral)."""
    if sebelum is None:
        return "<span class='delta datar'>– no comparison yet</span>"
    d = (sekarang - sebelum) * 100
    if abs(d) < 0.05:
        kelas = "datar"
    elif naik_baik is None:
        kelas = "datar"
    else:
        kelas = "naik" if (d > 0) == naik_baik else "turun"
    panah = "▲" if d > 0.05 else ("▼" if d < -0.05 else "■")
    return f"<span class='delta {kelas}'>{panah} {abs(d):.1f} pts<span class='vs'> vs previous period</span></span>"


def catatan(teks):
    st.markdown(f"<div class='catatan'>{teks}</div>", unsafe_allow_html=True)


SUMBER_LAPORAN = "Emplifi Feed report (emailed to Gmail, updated automatically)"
KOLOM_EMPLIFI = {"Reach": "Total reach", "Impressions": "Total impressions",
                 "Engagements": "Engagements", "Link clicks": "Link clicks",
                 "Post clicks": "Post clicks", "Video views": "Video view count",
                 "Engagement rate (impr.)": "Engagements ÷ Total impressions",
                 "Engagement rate (reach)": "Engagements ÷ Total reach"}


def kolom_sumber(m):
    return KOLOM_EMPLIFI.get(m, m)


def sumber(teks):
    """Keterangan singkat dari mana data grafik/bagian ini diambil."""
    st.markdown(f"<div class='sumber'>📌 <b>Data source:</b> {teks}</div>", unsafe_allow_html=True)


def tombol_unduh(df, nama, kunci):
    """Unduhan data DIMATIKAN (dashboard publik). Aktifkan lewat TAMPIL["unduh"] = True."""
    if not TAMPIL.get("unduh"):
        return
    df = D.siap_excel(df)
    a, b, _ = st.columns([1, 1, 6])
    a.download_button("CSV", df.to_csv(index=False).encode("utf-8-sig"),
                      file_name=f"{nama}.csv", mime="text/csv", key=f"csv_{kunci}")
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    b.download_button("Excel", buffer.getvalue(), file_name=f"{nama}.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      key=f"xlsx_{kunci}")


# =========================
# BAGIAN YANG DITAMPILKAN (dibuat ringkas agar nyaman di HP)
# Ubah ke True untuk memunculkan kembali bagian tersebut.
# =========================
TAMPIL = {
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
VERSI_KODE = int(Path(D.__file__).stat().st_mtime)


@st.cache_data(max_entries=2, show_spinner="Loading data...")
def muat_data(signature, versi_kode):
    return D.ambil_data()


def status_aman():
    try:
        return D.ambil_status(), None
    except Exception as error:
        return None, str(error)


status, error_status = status_aman()
if status:
    try:
        konten, label = muat_data(status["signature"], VERSI_KODE)
        st.session_state["data_valid"] = (konten, label, status)
        st.session_state["signature_tampil"] = status["signature"]
    except Exception as error:
        error_status = str(error)

if "data_valid" not in st.session_state:
    print(f"[status] data tidak bisa dimuat: {error_status}")     # detail hanya di log
    st.error("The dashboard data could not be loaded right now. Please try again in a few "
             "minutes. (Administrator: see Manage app → logs for details.)")
    st.stop()

konten, label, status_tampil = st.session_state["data_valid"]
konten = D.lengkapi_kolom(konten)
# Akun kompetitor (dikenali dari nama profil) dipisah: SEMUA bagian lain dashboard hanya
# memakai akun sendiri; kompetitor hanya tampil di tab Kompetitor pada Brand watch.
konten, pesaing = D.pisahkan(konten, D.daftar_kompetitor(_secrets("kompetitor")))


@st.cache_data(max_entries=2, show_spinner=False)
def muat_ringkasan_ai(signature, versi_kode):
    return D.ambil_ringkasan_ai()


try:
    ringkasan_ai = muat_ringkasan_ai(status_tampil["signature"], VERSI_KODE)
except Exception:
    ringkasan_ai = pd.DataFrame()


def ringkasan_ai_untuk(cakupan):
    if ringkasan_ai.empty:
        return None
    x = ringkasan_ai[ringkasan_ai["cakupan"] == cakupan]
    return None if x.empty else x.iloc[0]


def tampil_ringkasan_ai(r, data_konten):
    awal, akhir = pd.Timestamp(r["periode_awal"]), pd.Timestamp(r["periode_akhir"])
    st.markdown(f"<div class='ai-judul'>🤖 AI summary · {awal:%d %b} – {akhir:%d %b %Y}</div>",
                unsafe_allow_html=True)
    st.markdown(D.rujukan_ke_link(r["teks"], r["rujukan"], data_konten))
    catatan("Written by AI (Gemini) from numbers calculated by the system. Before display, "
            "code checks that every number exactly matches the data and every [P] reference is "
            "a real post; if not, the summary is not shown. "
            "Fixed period: last 7 days of data, not affected by filters.")
    with st.expander("View the facts used by the AI (for checking)"):
        try:
            st.json(json.loads(r["fakta"]), expanded=False)
        except (TypeError, ValueError):
            st.write(r["fakta"])


@st.fragment(run_every=CEK_PEMBARUAN_DETIK)
def panel_status():
    terbaru, err = status_aman()
    if terbaru and terbaru["signature"] != st.session_state.get("signature_tampil"):
        st.rerun(scope="app")

    info = terbaru or status_tampil
    waktu = info["last_imported_at"]
    ts = pd.Timestamp(waktu) if waktu is not None else None
    teks = (ts.tz_convert("Asia/Jakarta").strftime("%d %b %Y, %H:%M WIB")
            if ts is not None and ts.tzinfo else (str(waktu) if waktu else "–"))
    if err:
        kelas, status = "warn", "Database unreadable"
    elif info.get("last_status") == "failed":
        kelas, status = "gagal", "Last update failed"
    else:
        kelas, status = "ok", "Live · auto-updated"
    akun = konten["akun"].dropna().nunique()
    platform = _html.escape(", ".join(D.opsi(konten["platform"])[:5]) or "-")
    st.markdown(f"""
<div class="banner">
  <div class="kiri">
    <div class="logo">📊</div>
    <div>
      <div class="eyebrow">Social Media Analytics</div>
      <div class="b-judul">Emplifi Performance Dashboard</div>
      <div class="b-sub">{akun} accounts monitored · {platform}</div>
    </div>
  </div>
  <div class="kanan">
    <span class="pill"><span class="titik {kelas}"></span>{status}</span>
    <div class="info">Last update<br><b>{teks}</b><br>{info['content_count']:,} posts · checked {datetime.now():%H:%M}</div>
  </div>
</div>""", unsafe_allow_html=True)
    if err:
        print(f"[status] database tidak terbaca: {err}")      # detail hanya di log Manage app
        st.warning("Database cannot be read right now. Showing the last valid data.")
    elif info.get("last_status") == "failed":
        coba = pd.Timestamp(info["last_attempt_at"]) if info.get("last_attempt_at") else None
        kapan = coba.tz_convert("Asia/Jakarta").strftime("%d %b %Y, %H:%M WIB") if coba is not None and coba.tzinfo else "-"
        print(f"[status] pembaruan gagal: {info.get('last_pesan')}")   # detail hanya di log
        st.warning(f"The last data update ({kapan}) did not complete, so the previous valid "
                   "data is shown. The administrator has been notified.")
    elif info.get("db_mb", 0) > 70:
        st.warning(f"Database is {info['db_mb']:.0f} MB (safe limit 70 MB). "
                   "The administrator needs to move storage to the next tier.")
    elif ts is not None and ts.tzinfo:
        umur = (datetime.now(timezone.utc) - ts.tz_convert("UTC")).total_seconds() / 3600
        if umur > BATAS_DATA_LAMA_JAM:
            st.warning(f"No new data for {umur:.0f} hours. There may be no new report from Emplifi yet.")


# =========================
# HEADER
# =========================

panel_status()

try:                                              # versi portofolio: data fiktif
    from konfigurasi import baca_config
    DEMO = bool(baca_config().get("demo"))
except Exception:
    DEMO = False
if DEMO:
    st.markdown("<div class='sumber'>🧪 <b>Demo:</b> the brand \"Kopi Rimbun\", its accounts, "
                "ambassadors, posts, and all figures are fictional and generated for this portfolio. "
                "AI results are pre-generated with the same validation rules as production. "
                "Post links point to example.com.</div>", unsafe_allow_html=True)
kiri, kanan = st.columns([5, 1])
with kiri:
    catatan("Set the period and filters below, then scroll for details. "
            "Tap or hover over a chart to see the numbers.")
with kanan:
    st.toggle("🌙 Dark mode", key="mode_gelap",
              help="Switch to a dark theme. Charts and colors adapt too.")
    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if EMAIL_MASUK:
        catatan(f"Signed in as {EMAIL_MASUK}")
        if _secrets("auth"):
            st.button("Sign out", on_click=st.logout, use_container_width=True)
        elif st.button("Sign out", use_container_width=True):
            st.session_state.pop("lolos_password", None)
            st.rerun()


# =========================
# PANEL FILTER (atas, bisa disembunyikan)
# =========================

tgl_min, tgl_max = D.rentang_default(konten)
if "preset" not in st.session_state:
    st.session_state["preset"] = "All data"

rentang_otomatis = D.rentang_preset(st.session_state["preset"], tgl_min, tgl_max)
if rentang_otomatis:
    st.session_state["f_tanggal"] = rentang_otomatis
elif "f_tanggal" not in st.session_state:
    st.session_state["f_tanggal"] = (tgl_min, tgl_max)
else:
    nilai = st.session_state["f_tanggal"]
    if isinstance(nilai, (tuple, list)) and len(nilai) == 2:
        awal = min(max(nilai[0], tgl_min), tgl_max)
        st.session_state["f_tanggal"] = (awal, min(max(nilai[1], awal), tgl_max))


def jadi_kustom():
    st.session_state["preset"] = "Custom"


def multiselect_aman(wadah, judul, opsi, kunci):
    if kunci in st.session_state:
        st.session_state[kunci] = [v for v in st.session_state[kunci] if v in opsi]
    return wadah.multiselect(judul, opsi, key=kunci, placeholder="All")


with st.expander("⚙️  Filters & period", expanded=False):
    c1, c2 = st.columns([3, 2])
    c1.radio("Period", D.PRESET, key="preset", horizontal=True,
             help=f"Counted from the latest data date ({tgl_max:%d %b %Y}).")
    rentang = c2.date_input("Posting date", min_value=tgl_min, max_value=tgl_max,
                            key="f_tanggal", on_change=jadi_kustom)

    f = {}
    a, b, c, d = st.columns(4)
    f["platform"] = multiselect_aman(a, "Platform", D.opsi(konten["platform"]), "f_platform")
    f["profile"] = multiselect_aman(b, "Account", D.opsi(konten["akun"]), "f_profile")
    f["content_type"] = multiselect_aman(c, "Content type", D.opsi(konten["content_type"]),
                                         "f_content_type")
    f["media_type"] = multiselect_aman(d, "Media type", D.opsi(konten["media_type"]),
                                       "f_media_type")

    a, b, c, d = st.columns(4)
    hier = label[label["label_type"] == "TOWER_CAMPAIGN"]
    f["tower"] = multiselect_aman(a, "Tower", D.opsi(hier["tower"]), "f_tower")
    if f["tower"]:
        hier = hier[hier["tower"].isin(f["tower"])]
    f["campaign"] = multiselect_aman(b, "Campaign", D.opsi(hier["campaign"]), "f_campaign")
    if f["campaign"]:
        hier = hier[hier["campaign"].isin(f["campaign"])]
    f["sub_campaign"] = multiselect_aman(c, "Sub Campaign", D.opsi(hier["sub_campaign"]),
                                         "f_sub_campaign")
    f["pillar"] = multiselect_aman(
        d, "Pillar", D.opsi(label.loc[label["label_type"] == "PILLAR", "pillar"]), "f_pillar")
    opsi_lain = D.opsi(label.loc[label["label_type"] == "LAINNYA", "label_lain"])
    if opsi_lain:
        f["label_lain"] = multiselect_aman(
            st, "Other labels", opsi_lain, "f_label_lain")

    a, b, c = st.columns([3, 2, 1])
    teks_cari = a.text_input(
        "Search", key="f_cari", placeholder="Words in caption, label, or Content ID",
        help="Several words = content containing all of them.")
    daftar_metrik = list(D.METRIK) + list(D.RASIO)
    if any(TAMPIL[k] for k in ("kontribusi", "tren", "campaign", "pillar_format", "waktu_peta")):
        metrik = b.selectbox("Chart metric", daftar_metrik, index=1, key="metrik")
    else:                                         # tidak ada grafik yang memakai pilihan ini
        metrik = st.session_state.get("metrik", "Impressions")
    c.write("")
    if c.button("Reset all", use_container_width=True):
        minta({**{k: None for k in FILTER_LIST}, "f_tanggal": None,
               "preset": "All data", "f_cari": ""})

if not isinstance(rentang, (tuple, list)) or len(rentang) != 2:
    st.info("Select a start and end date.")
    st.stop()
f["tanggal"] = tuple(rentang)

chip = [(k, v) for k in FILTER_LIST for v in st.session_state.get(k, [])]
if chip:
    kolom = st.columns(min(len(chip), 6))
    for i, (kunci, nilai) in enumerate(chip[:6]):
        if kolom[i].button(f"✕ {FILTER_LIST[kunci]}: {nilai}", key=f"chip_{kunci}_{nilai}",
                           use_container_width=True):
            minta({kunci: [v for v in st.session_state[kunci] if v != nilai]})


# =========================
# HITUNG
# =========================

df = D.cari(D.filter_konten(konten, label, f), teks_cari)
f_lalu = {**f, "tanggal": D.periode_sebelumnya(*f["tanggal"])}
df_lalu = D.cari(D.filter_konten(konten, label, f_lalu), teks_cari)

total = D.ringkasan(df)
total_lalu = D.ringkasan(df_lalu) if not df_lalu.empty else None

label_hier = D.label_hierarki_terfilter(label, f)
label_hier = label if label_hier is None else label_hier
label_pil = D.label_pillar_terfilter(label, f)
label_pil = label if label_pil is None else label_pil

if df.empty:
    st.info("No content matches these filters.")
    st.stop()


# =========================
# KPI
# =========================

kartu = ["Content", "Reach", "Impressions", "Engagements", "Engagement rate (impr.)"]
for wadah, nama in zip(st.columns(len(kartu)), kartu):
    nilai = total[nama]
    ubah = D.perubahan(nilai, total_lalu[nama] if total_lalu else None)
    kartu_kpi(wadah, nama, f"{nilai:,}" if nama == "Content" else V.format_nilai(nilai, nama), ubah)
awal_lalu, akhir_lalu = f_lalu["tanggal"]
catatan(f"{f['tanggal'][0]:%d %b %Y} – {f['tanggal'][1]:%d %b %Y}. Change compared with "
        f"{awal_lalu:%d %b %Y} – {akhir_lalu:%d %b %Y} with the same filters."
        + ("" if total_lalu else " No data in the comparison period."))
sumber(f"{SUMBER_LAPORAN} · columns Total reach, Total impressions, Engagements, Video view count · "
       "each post counted once, by posting date (Date column).")
st.markdown("<div class='menu'>"
            "<a href='#ringkasan'>📰 Summary</a><a href='#brandwatch'>📡 Brand watch</a>"
            + ("<a href='#tren'>📈 Trend</a>" if TAMPIL["tren"] else "")
            + ("<a href='#campaign'>🗂️ Campaign</a>" if TAMPIL["campaign"] else "")
            + ("<a href='#pillar'>🧱 Pillar & format</a>" if TAMPIL["pillar_format"] else "")
            + ("<a href='#waktu'>🕒 Posting time</a>" if TAMPIL["waktu_peta"] else "")
            + "<a href='#peringkat'>🏆 Rankings</a><a href='#top'>⭐ Top content</a></div>", unsafe_allow_html=True)


# =========================
# KOMPONEN
# =========================

def kartu_kontribusi(kolom, judul, keterangan, kunci, aksi):
    with st.container(border=True):
        bagian(judul, keterangan)
        data, dipakai = D.kontribusi(df, kolom, metrik)
        sumber(f"{SUMBER_LAPORAN} · {'Platform' if kolom == 'platform' else 'Profile name'} "
               f"column + {kolom_sumber(dipakai)}, summed per group.")
        jenis, alasan = V.pilih_visual_kontribusi(len(data))
        if jenis == "kosong":
            st.info("No data.")
            return
        if jenis == "angka":
            st.metric(str(data.iloc[0][kolom]), "100%")
        else:
            fig = V.grafik_kontribusi(data, kolom, dipakai, jenis)
            if jenis == "bar":
                event = grafik(fig, use_container_width=True, key=kunci,
                                        on_select="rerun", selection_mode="points")
                poin = poin_terpilih(event)
                if poin and poin[0].get("y") is not None:
                    minta(aksi(poin[0]["y"]))
            else:
                grafik(fig, use_container_width=True)
        tambahan = "" if dipakai == metrik else f" Ratios cannot be shown as contribution, so this uses {dipakai}."
        petunjuk = " Tap the chart to see the numbers; use the filters above to narrow down."
        catatan(f"Visual: {alasan}.{tambahan}{petunjuk}")


def kartu_breakdown(data, kolom, judul, keterangan, total_ref, kunci, aksi, aditif):
    with st.container(border=True):
        bagian(judul, keterangan)
        jenis, alasan = V.pilih_visual_kategori(len(data))
        if jenis == "kosong":
            st.info("No data.")
            return
        if jenis == "angka":
            r = data.iloc[0]
            st.metric(str(r[kolom]), V.format_nilai(r[metrik], metrik),
                      help=f"{int(r['Content'])} posts")
        else:
            event = grafik(V.grafik_kategori(data, kolom, metrik, jenis),
                                    use_container_width=True, key=kunci,
                                    on_select="rerun", selection_mode="points")
            poin = poin_terpilih(event)
            if poin and poin[0].get("y") not in (None, D.TANPA_LABEL):
                minta(aksi(poin[0]["y"]))
        teks = f"Visual: {alasan}."
        if not aditif and D.total_jumlah_breakdown_melebihi(data, total_ref, metrik):
            teks += (" Category values add up to more than the total because some content "
                     "has more than one label; each category's figure is still correct.")
        catatan(teks)


def tampil_detail(content_id):
    baris = df[df["content_id"] == content_id]
    if baris.empty:
        return
    satu = baris.iloc[0]
    link = satu.get("content_url")
    gambar = satu.get("content_image")
    if isinstance(gambar, str) and gambar:
        st.image(gambar, width=220)
    st.markdown(f"**Content details `{content_id}`**"
                + (f" · [Open post ↗]({link})" if isinstance(link, str) and link else ""))
    if isinstance(link, str) and link:
        catatan(f"Link: {link} (from column '{satu.get('kolom_link') or '-'}')")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Reach", V.format_nilai(satu["total_reach"], "Reach"))
    k2.metric("Impressions", V.format_nilai(satu["total_impressions"], "Impressions"))
    k3.metric("Engagements", V.format_nilai(satu["engagements"], "Engagements"))
    er = satu["impressions_engagement_rate"]
    k4.metric("ER (impr.) original Emplifi value", "–" if pd.isna(er) else f"{er:g}")
    if pd.notna(satu.get("komentar_negatif")) or pd.notna(satu.get("komentar_positif")):
        catatan(f"Comments: {int(satu.get('komentar_positif') or 0)} positive · "
                f"{int(satu.get('komentar_netral') or 0)} neutral · "
                f"{int(satu.get('komentar_negatif') or 0)} negative"
                + (f" · post sentiment: {satu.get('sentimen')}" if satu.get("sentimen") else ""))
    teks_caption = str(satu.get("caption") or "").strip()
    if teks_caption:
        st.markdown(f"> {teks_caption[:600]}{'…' if len(teks_caption) > 600 else ''}")
    catatan(f"{satu['platform']} · {satu['profile_name']} · {satu['content_type']} / "
            f"{satu['media_type']} · posted {satu['post_date']} · source {satu['source_file']}")
    lbl = label[label["content_id"] == content_id].drop(columns=["content_id"])
    if not lbl.empty:
        st.dataframe(lbl, hide_index=True, use_container_width=True)


# =========================
# KARTU KONTEN (pengganti tabel ala Excel)
# =========================


METRIK_KARTU = [("Reach", "total_reach"), ("Impressions", "total_impressions"),
                ("Engagements", "engagements"), ("Video views", "video_views"),
                ("Link clicks", "link_clicks")]


def _angka_kartu(nilai, nama):
    if nilai is None or pd.isna(nilai):
        return None
    return V.format_nilai(float(nilai), nama)


def kartu_konten(baris, urutan, sorot=None, ringkas=False, angka_khusus=None, tambahan=""):
    """Satu postingan sebagai kartu: peringkat, thumbnail, akun · platform · tanggal,
    cuplikan caption (klik = buka postingan), dan angka utama."""
    url = baris.get("content_url")
    ada_link = D._link_valid(url)
    platform = str(baris.get("platform") or "")
    warna = V.WARNA_PLATFORM.get(platform.lower(), "#64748B")
    tgl = pd.to_datetime(baris.get("post_date"), errors="coerce")
    tgl = tgl.strftime("%d %b %Y") if pd.notna(tgl) else "-"
    caption = D.teks_singkat(baris.get("caption"), 90 if ringkas else 160) or "(no caption)"
    caption = _html.escape(caption)
    judul = (f"<a class='k-cap' href='{_html.escape(url)}' target='_blank' rel='noopener'>{caption}</a>"
             if ada_link else f"<div class='k-cap'>{caption}</div>")
    gambar = baris.get("content_image")
    thumb = (f"<div class='k-thumb' style=\"background-image:url('{_html.escape(gambar)}')\"></div>"
             if isinstance(gambar, str) and gambar.startswith("http") and not ringkas else "")
    angka = list(angka_khusus or [])
    daftar = ([] if angka_khusus is not None else
              [(sorot, D.METRIK.get(sorot, sorot))] if ringkas and sorot else METRIK_KARTU)
    for nama, kolom in daftar:
        teks = _angka_kartu(baris.get(kolom), nama)
        if teks is None or (nama in ("Video views", "Link clicks") and teks == "0"):
            continue
        kelas = "k-m utama" if nama == sorot else "k-m"
        angka.append(f"<span class='{kelas}'><b>{teks}</b> {nama}</span>")
    if not ringkas and angka_khusus is None:
        er = baris.get("Engagement rate (impr.)")
        if er is not None and pd.notna(er):
            kelas = "k-m utama" if sorot == "Engagement rate (impr.)" else "k-m"
            angka.append(f"<span class='{kelas}'><b>{er:.2%}</b> ER</span>")
    buka = (f"<a class='k-buka' href='{_html.escape(url)}' target='_blank' rel='noopener'>Open ↗</a>"
            if ada_link else "")
    return (f"<div class='k-post'><div class='k-rank'>{urutan}</div>{thumb}<div class='k-isi'>"
            f"<div class='k-meta'><span class='k-chip' style='--c:{warna}'>{_html.escape(platform)}</span>"
            f"<span>{_html.escape(str(baris.get('akun') or baris.get('profile_name') or ''))} · {tgl}</span>{buka}</div>"
            f"{judul}<div class='k-angka'>{''.join(angka)}</div>{tambahan}</div></div>")


def daftar_kartu(data, sorot=None, ringkas=False):
    if data.empty:
        st.info("No content for these filters.")
        return
    st.markdown("".join(kartu_konten(r, i, sorot, ringkas)
                        for i, (_, r) in enumerate(data.iterrows(), 1)),
                unsafe_allow_html=True)


def pil(nilai, label, utama=False):
    return f"<span class='k-m{' utama' if utama else ''}'><b>{nilai}</b> {label}</span>"


def daftar_sentimen_brand(data):
    """Per akun: bar persentase positif/netral/negatif + angka, bergaya kartu."""
    w = V.WARNA_SENTIMEN
    baris = []
    for _, r in data.iterrows():
        bar = "".join(f"<span style='width:{max(float(r[k]), 0) * 100:.1f}%;background:{w[k]}'></span>"
                      for k in ["Positive", "Neutral", "Negative"])
        angka = [pil(f"{r['Positive']:.0%}", "positive"), pil(f"{r['Neutral']:.0%}", "neutral"),
                 pil(f"{r['Negative']:.0%}", "negative", utama=False),
                 pil(f"{int(r['total']):,}", "comments")]
        baris.append(f"<div class='k-post'><div class='k-isi'>"
                     f"<div class='k-cap' style='margin-top:0'>{_html.escape(str(r['profile_name']))}</div>"
                     f"<div class='s-bar'>{bar}</div><div class='k-angka'>{''.join(angka)}</div>"
                     f"</div></div>")
    st.markdown("".join(baris), unsafe_allow_html=True)


def tampil_topik_komentar(hasil):
    """Positif / netral / negatif: topik postingan yang paling banyak menerima komentar itu."""
    st.markdown("---")
    st.markdown("**What the comments are about**")
    sumber(f"{SUMBER_LAPORAN} · comment counts per sentiment (Emplifi classification) × the topic "
           "category of each post (Gemini AI, fixed list). The Feed report contains comment "
           "counts, not comment text, so this shows which post topics received each type of comment.")
    if not hasil:
        st.info("Appears automatically once posts have AI topic categories "
                "(the Gemini key is active and the daily analysis has run).")
        return
    w = V.WARNA_SENTIMEN
    for tab, nama in zip(st.tabs(["😊 Positive", "😐 Neutral", "😟 Negative"]),
                         ["Positive", "Neutral", "Negative"]):
        with tab:
            h = hasil.get(nama)
            if not h:
                st.info(f"Fewer than {D.MIN_KOMENTAR_BRAND} {nama.lower()} comments on analysed posts.")
                continue
            kartu = []
            for i, r in enumerate(h["baris"], 1):
                c = r["contoh"]
                url = c.get("content_url")
                teks = _html.escape(D.teks_singkat(c.get("caption"), 80) or "(no caption)")
                contoh = (f"<a href='{_html.escape(url)}' target='_blank' rel='noopener'>{teks}</a>"
                          if D._link_valid(url) else teks)
                angka = [pil(f"{r['Share']:.0%}", f"of {nama.lower()} comments", utama=True),
                         pil(f"{r['Comments']:,}", "comments"), pil(f"{r['Posts']:,}", "posts")]
                kartu.append(
                    f"<div class='k-post'><div class='k-rank'>{i}</div><div class='k-isi'>"
                    f"<div class='k-cap' style='margin-top:0'>{_html.escape(r['Topic'])}</div>"
                    f"<div class='s-bar'><span style='width:{r['Share'] * 100:.1f}%;"
                    f"background:{w[nama]}'></span></div>"
                    f"<div class='k-angka'>{''.join(angka)}</div>"
                    f"<div class='k-info'>Most-commented post: {contoh}</div></div></div>")
            st.markdown("".join(kartu), unsafe_allow_html=True)
            if h["cakupan"] is not None and h["cakupan"] < 0.995:
                catatan(f"Covers {h['cakupan']:.0%} of {nama.lower()} comments "
                        "(posts not yet analysed by AI are not included).")


def daftar_entitas(data, nama_kolom="Name"):
    """Ringkasan per nama (ambassador/kolaborator) sebagai baris kartu, bukan tabel."""
    baris = []
    for i, (_, r) in enumerate(data.iterrows(), 1):
        angka = [pil(f"{int(r['Posts']):,}", "posts"),
                 pil(V.format_nilai(r["Avg. engagements"], "Engagements"), "avg. engagements")]
        if pd.notna(r.get("Index")):
            angka.append(pil(f"{r['Index']:.1f}×", "vs average", utama=r["Index"] >= 1))
        if pd.notna(r.get("ER")):
            angka.append(pil(f"{r['ER']:.2%}", "ER"))
        if pd.notna(r.get("Negative")):
            angka.append(pil(f"{r['Negative']:.0%}", "negative comments"))
        baris.append(f"<div class='k-post'><div class='k-rank'>{i}</div><div class='k-isi'>"
                     f"<div class='k-cap' style='margin-top:2px'>{_html.escape(str(r[nama_kolom]))}</div>"
                     f"<div class='k-angka'>{''.join(angka)}</div></div></div>")
    st.markdown("".join(baris), unsafe_allow_html=True)


# =========================
# WHAT HAPPENS IN SOCIAL MEDIA
# =========================

with st.container(border=True):
    bagian("What happens in social media",
           "Automatic summary of posts from the brand's own accounts "
           "in the selected period, compared with the previous period", jangkar="ringkasan")
    sumber(f"{SUMBER_LAPORAN} · post text (Content column), Engagements, Labels, and comment columns "
           "of our own accounts. The AI summary is written by Gemini AI from these figures.")
    r_ai = ringkasan_ai_untuk("sendiri")
    if r_ai is not None:
        tampil_ringkasan_ai(r_ai, konten)
        st.markdown("---")
    kiri, kanan = st.columns([1, 1]) if TAMPIL["topik"] else (st.container(), None)
    with kiri:
        st.markdown("**Highlights this period**")
        poin = D.sorotan(df, df_lalu, label)
        if poin:
            st.markdown("\n".join(f"- {p}" for p in poin))
        else:
            st.info("No highlights are sufficiently supported by data in this period.")
    if kanan is not None:
        with kanan:
            if D.ada_caption(df):
                pilihan_topik = (["Category (AI)"] if D.ada_ai(df) else []) + ["Hashtag", "Keyword"]
                if st.session_state.get("jenis_topik") not in pilihan_topik:
                    st.session_state.pop("jenis_topik", None)
                jenis = st.radio("Topic", pilihan_topik, horizontal=True,
                                 key="jenis_topik", label_visibility="collapsed")
                kode_jenis = {"Category (AI)": "ai", "Hashtag": "hashtag"}.get(jenis, "kata")
                topik = D.analisis_topik(df, df_lalu, kode_jenis)
                if topik.empty:
                    st.info(f"No {jenis.lower()} in posts this period.")
                else:
                    grafik(V.grafik_topik(topik, "#" if jenis == "Hashtag" else ""),
                                    use_container_width=True)
                    if kode_jenis == "ai":
                        catatan("Categories are chosen by AI from a fixed list (it cannot invent new "
                                "ones). Posts not yet analysed by AI are not counted.")
            else:
                st.info("Post text is not available in the data, so topic analysis cannot "
                        "be shown yet.")


    catatan("Calculated from our own accounts' post text and figures (not public conversation). "
            f"Highlights are only shown when supported by at least {D.MIN_POSTINGAN} posts. "
            + (" Each post is counted once per topic." if TAMPIL["topik"] else ""))

    # ----- Sentimen komentar audiens -----
    st.markdown("---")
    st.markdown("**Audience comment sentiment**")
    sumber("Emplifi's own comment classification · Positive, Neutral, and Negative comments "
           "columns in the Feed report.")
    sen, sen_lalu = D.ringkasan_sentimen(df), D.ringkasan_sentimen(df_lalu)
    if not D.ada_sentimen(df):
        st.info("Comment sentiment data is not available for this period.")
    elif sen is None:
        st.info(f"Classified comments in this period are fewer than {D.MIN_KOMENTAR}, "
                "too few to draw conclusions.")
    else:
        def lalu(k):
            return sen_lalu[k] if sen_lalu else None
        k1, k2, k3, k4 = st.columns(4)
        kartu_mini(k1, "😊 Positive", f"{sen['pos%']:.0%}", "of classified comments",
                   delta_poin(sen["pos%"], lalu("pos%"), True), aksen="#16A34A")
        kartu_mini(k2, "😐 Neutral", f"{sen['netral%']:.0%}", "of classified comments",
                   delta_poin(sen["netral%"], lalu("netral%"), None), aksen="#94A3B8")
        kartu_mini(k3, "😟 Negative", f"{sen['neg%']:.0%}", "of classified comments",
                   delta_poin(sen["neg%"], lalu("neg%"), False), aksen="#DC2626")
        kartu_mini(k4, "⚖️ Net sentiment", f"{sen['net']:+.0%}", "positive minus negative",
                   delta_poin(sen["net"], lalu("net"), True))
        st.write("")

        kiri, kanan = st.columns([1, 1])
        with kiri:
            per_brand = D.sentimen_per_brand(df)
            if len(per_brand) >= 1:
                st.markdown("**Sentiment by account**")
                daftar_sentimen_brand(per_brand)
            else:
                catatan(f"No brand has at least {D.MIN_KOMENTAR_BRAND} classified comments yet.")
        with kanan:
            st.markdown("**Most-commented posts by sentiment**")
            opsi_akun = ["All"] + [a for a in D.TP.URUTAN_AKUN if a in set(df["akun"])]
            opsi_sen = ["😟 Negative", "😊 Positive", "😐 Neutral"]
            for kunci, opsi in [("akun_sentimen", opsi_akun), ("arah_sentimen", opsi_sen)]:
                if st.session_state.get(kunci) not in opsi:
                    st.session_state[kunci] = opsi[0]
            pilih_akun = st.segmented_control("Account", opsi_akun, key="akun_sentimen",
                                              label_visibility="collapsed") or "All"
            arah = st.segmented_control("Sentiment", opsi_sen, key="arah_sentimen",
                                        label_visibility="collapsed") or opsi_sen[0]
            jenis = arah.split(" ", 1)[1]                     # Negative / Positive / Neutral
            kolom_k = D.SENTIMEN[jenis]
            sumber_akun = df if pilih_akun == "All" else df[df["akun"] == pilih_akun]
            daftar = sumber_akun[sumber_akun[kolom_k].fillna(0) > 0].nlargest(5, kolom_k)
            if daftar.empty:
                st.info(f"No posts with {jenis.lower()} comments"
                        + ("" if pilih_akun == "All" else f" on {pilih_akun}") + " in this period.")
            else:
                kolom_sen = list(D.SENTIMEN.values())
                kartu = []
                for i, (_, r) in enumerate(daftar.iterrows(), 1):
                    total_k = sum(float(r[k]) for k in kolom_sen if pd.notna(r[k]))
                    angka = [pil(f"{int(r[kolom_k]):,}", f"{jenis.lower()} comments", utama=True)]
                    if total_k:
                        angka.append(pil(f"{r[kolom_k] / total_k:.0%}", "of its comments"))
                        angka.append(pil(f"{int(total_k):,}", "classified comments"))
                    kartu.append(kartu_konten(r, i, ringkas=True, angka_khusus=angka))
                st.markdown("".join(kartu), unsafe_allow_html=True)
                catatan("Tap a post to open it on its platform.")
        if TAMPIL["topik_komentar"]:
            tampil_topik_komentar(D.topik_komentar(df))
        catatan(f"Sentiment classification from Emplifi. Percentages are based on the number of "
                f"classified comments ({int(sen['total']):,} comments), compared with the previous period. "
                f"Brand comparison only covers brands with at least {D.MIN_KOMENTAR_BRAND} comments.")


# =========================
# BRAND WATCH: aplikasi brand dan brand ambassador
# =========================

def tabel_entitas(data, judul_nama):
    daftar_entitas(data)


def grafik_entitas(data, kunci):
    if len(data) >= 2:
        g = data.rename(columns={"Posts": "Content"})
        grafik(V.grafik_kategori(g, "Name", "Engagements",
                                 "bar" if len(g) <= V.BATAS_BAR else "bar_top"),
               use_container_width=True, key=kunci)


def tabel_sebutan(data, mask, asal, nama, kunci, n=10):
    """Postingan yang menyebut 'nama' sebagai kartu + cara terdeteksinya (bisa diaudit)."""
    x = data[mask].copy()
    if x.empty:
        return
    x["_asal"] = asal[mask]
    x["_kutipan"] = D.bukti_ai(x, nama)
    x = x.nlargest(n, "engagements")
    kartu = []
    for i, (_, r) in enumerate(x.iterrows(), 1):
        angka = [pil(V.format_nilai(r["engagements"], "Engagements"), "Engagements", utama=True)]
        teks_imp = _angka_kartu(r.get("total_impressions"), "Impressions")
        if teks_imp:
            angka.append(pil(teks_imp, "Impressions"))
        info = f"<div class='k-info'>Detected via: <b>{_html.escape(str(r['_asal']))}</b>"
        if isinstance(r["_kutipan"], str) and r["_kutipan"]:
            info += f" · AI quote: “{_html.escape(r['_kutipan'])}”"
        kartu.append(kartu_konten(r, i, ringkas=True, angka_khusus=angka, tambahan=info + "</div>"))
    st.markdown("".join(kartu), unsafe_allow_html=True)


pantau = D.daftar_pantau(_secrets("pantau"))
with st.container(border=True):
    bagian("Brand watch",
           "The brand app, brand ambassadors, and collaborators "
           "in the selected period and filters", jangkar="brandwatch")
    tab_brand = st.tabs(["📱 Rimbun App", "⭐ Ambassadors", "🤝 Collaborators"]
                        + (["🆚 Competitors"] if TAMPIL["kompetitor"] else []))
    tab_app, tab_amb, tab_kol = tab_brand[:3]
    tab_komp = tab_brand[3] if TAMPIL["kompetitor"] else None

    # ----- Aplikasi brand -----
    with tab_app:
        sumber(f"{SUMBER_LAPORAN} · post text (Content), Labels, and Collaborators columns, "
               "matched with app keywords + an AI check (Gemini) with verified quotes.")
        mask, asal = D.sebutan(df, "Rimbun App", pantau["app"])
        r = D.ringkas_topik(df, mask)
        if r is None:
            st.info("No posts mention Rimbun App in this period and filters.")
        else:
            kalimat = D.kalimat_topik("Rimbun App", r)
            if kalimat:
                st.markdown(kalimat)
            a, b, c, d = st.columns(4)
            kartu_mini(a, "📝 Posts", f"{r['Posts']:,}", f"{r['Share']:.0%} of all posts")
            kartu_mini(b, "💬 Avg. engagements", V.format_nilai(r["Avg. engagements"], "Engagements"),
                       "per Rimbun App post")
            kartu_mini(c, "📊 Index", f"{r['Index']:.1f}×" if r.get("Index") else "–",
                       "vs average of all posts")
            kartu_mini(d, "😟 Negative comments", f"{r['Negative']:.0%}" if r.get("Negative") is not None else "–",
                       "of classified comments" if r.get("Negative") is not None
                       else f"too few comments (< {D.MIN_KOMENTAR_BRAND})")
            st.write("")
            st.markdown("**Top Rimbun App posts by engagement**")
            tabel_sebutan(df, mask, asal, "Rimbun App", "t_app")
        catatan("Detected from captions, labels, and collaborators using keywords ("
                + ", ".join(pantau["app"]) + "), plus AI findings backed by "
                "caption quotes verified by code.")

    # ----- Brand ambassador -----
    with tab_amb:
        sumber(f"{SUMBER_LAPORAN} · post text (Content), Labels, and Collaborators columns, "
               "matched with each ambassador's name + an AI check (Gemini) with verified quotes.")
        hasil_amb = []
        for nama, kata in pantau["ambassador"].items():
            m, src = D.sebutan(df, nama, kata)
            hasil_amb.append((nama, m, src, D.ringkas_topik(df, m)))
        kolom_amb = st.columns(max(1, min(len(hasil_amb), 3)))
        for i, (nama, m, src, r) in enumerate(hasil_amb):
            ket = D.KETERANGAN.get(nama, "")
            if r is None:
                kartu_mini(kolom_amb[i % len(kolom_amb)], f"⭐ {nama}", "0 posts",
                           f"{ket}<br>not mentioned in this period")
            else:
                rincian = [f"{V.format_nilai(r['Avg. engagements'], 'Engagements')} engagements/post"]
                if r.get("Index"):
                    rincian.append(f"{r['Index']:.1f}× average")
                if r.get("ER") is not None and pd.notna(r.get("ER")):
                    rincian.append(f"ER {r['ER']:.2%}")
                if r.get("Negative") is not None:
                    rincian.append(f"{r['Negative']:.0%} negative comments")
                kartu_mini(kolom_amb[i % len(kolom_amb)], f"⭐ {nama}",
                           f"{r['Posts']:,} posts", f"{ket}<br>{' · '.join(rincian)}")
        st.write("")
        ada = [h for h in hasil_amb if h[1].any()]
        if not ada:
            st.info("No posts mention a brand ambassador in this period and filters.")
        else:
            opsi_amb = [h[0] for h in ada]
            if st.session_state.get("pilih_amb") not in opsi_amb:
                st.session_state.pop("pilih_amb", None)
            pilih = st.radio("View posts", opsi_amb, horizontal=True, key="pilih_amb")
            for nama, m, src, _ in ada:
                if nama == pilih:
                    tabel_sebutan(df, m, src, nama, f"t_amb_{nama}")
        catatan("Clear keywords (e.g. \"wening asmara\", \"bagas jenggala\") are counted directly. "
                "Ambiguous mentions like \"Tara\" (also the Indonesian \"ta-da!\") are only counted if "
                "the AI confirms them and the quote really exists in the caption. \"Detected via\" under each post "
                "shows where each finding came from. One post can mention more than one name.")

    # ----- Kolaborator -----
    with tab_kol:
        sumber(f"{SUMBER_LAPORAN} · Collaborators column (collab posts tagged on the platform).")
        kol = D.kolaborator(df)
        if kol.empty:
            st.info("No collaboration posts in this period and filters.")
        else:
            tabel_entitas(kol, "Collaborator")
        catatan("Taken automatically from the Collaborators column in the Emplifi report (actual data, not guesses).")

    # ----- Kompetitor -----
    if tab_komp is not None:
        with tab_komp:
            komp = D.filter_pesaing(pesaing, f, teks_cari)
            if pesaing.empty:
                st.info("No competitor account data in the Emplifi reports yet. Once competitor accounts "
                        "(e.g. Kopi Senja, Teh Lembah, Kopi Kilat) are added to the Feed report "
                        "sent to Gmail, this section fills in automatically.")
            elif komp.empty:
                st.info("No competitor posts in this period and filters.")
            else:
                r_k = ringkasan_ai_untuk("kompetitor")
                if r_k is not None:
                    tampil_ringkasan_ai(r_k, pesaing)
                    st.markdown("---")
                tabel_b, platform_b = D.banding_brand(df, komp)
                st.markdown(f"**Share of Total interactions by brand** · platform: {', '.join(platform_b)}")
                grafik(V.grafik_brand(tabel_b, D.TP.KOMPETITOR_SENDIRI), use_container_width=True,
                       key="c_brand")
                tampil_b = tabel_b.copy()
                for k in ["Interaction share", "Post share"]:
                    tampil_b[k] = tampil_b[k] * 100
                st.dataframe(tampil_b, hide_index=True, use_container_width=True, column_config={
                    "Interactions": st.column_config.NumberColumn(format="%d"),
                    "Interactions per post": st.column_config.NumberColumn(format="%d"),
                    "Interaction share": st.column_config.ProgressColumn(
                        format="%.0f%%", min_value=0, max_value=100),
                    "Post share": st.column_config.NumberColumn(format="%.0f%%"),
                })
                t_brand = D.topik_per_brand(df, komp, platform_b)
                if not t_brand.empty:
                    st.markdown("**What each brand talks about** (AI topic categories, share of posts)")
                    st.dataframe((t_brand * 100).round(0), use_container_width=True,
                                 column_config={c: st.column_config.NumberColumn(format="%.0f%%")
                                                for c in t_brand.columns})
                st.markdown("**Top competitor posts by interactions**")
                top_k = D.postingan_pesaing(komp)
                semua_link = bool(top_k["punya_link"].all())
                st.dataframe(
                    top_k.drop(columns=["punya_link"] + ([] if semua_link else ["Content"])),
                    hide_index=True, use_container_width=True, key="t_komp", column_config={
                        "brand": "Brand", "profile_name": "Account", "platform": "Platform",
                        "Content": st.column_config.LinkColumn(
                            "Post (click to open)", display_text=r"#konten=(.*)$", width="large"),
                        "ai_topik": "Topic (AI)",
                        "total_interactions": st.column_config.NumberColumn("Interactions", format="%d"),
                    })
            catatan("Competitors are identified by ACCOUNT NAME in the Emplifi report, not by caption text, "
                    "so own posts that mention competitors are not counted. Competitors' public "
                    "accounts have no reach/impressions, so the comparison uses Total "
                    "interactions and only on platforms available for competitors. Competitor "
                    "data is never included in KPIs, charts, or other tables on the dashboard.")


# =========================
# 1. KONTRIBUSI PLATFORM & PROFILE
# =========================

if TAMPIL["kontribusi"]:
    kiri, kanan = st.columns(2)
    with kiri:
        kartu_kontribusi("platform", "Contribution by platform",
                         f"Each platform's share of total {metrik if metrik in D.METRIK else 'Impressions'} in the selected period",
                         "c_platform", lambda v: {"f_platform": [v]})
    with kanan:
        kartu_kontribusi("profile_name", "Contribution by profile",
                         "Each account's share of the total in the selected period",
                         "c_profile", lambda v: {"f_profile": [v]})


# =========================
# 2. TREN
# =========================

if TAMPIL["tren"]:
    with st.container(border=True):
        bagian("Performance over time",
               f"{metrik} per period by content posting date", jangkar="tren")
        sumber(f"{SUMBER_LAPORAN} · {kolom_sumber(metrik)}, grouped by posting date (Date column).")
        otomatis, alasan_gran = V.pilih_granularitas(*f["tanggal"])
        a, b = st.columns([3, 2])
        pilihan = a.radio("Granularity", ["Auto", "Daily", "Weekly", "Monthly"],
                          horizontal=True, key="granularitas", label_visibility="collapsed")
        banding = b.toggle("Compare with previous period", key="banding")
        gran = otomatis if pilihan == "Auto" else pilihan

        data_tren = D.tren(df, metrik, gran)
        jenis, alasan = V.pilih_visual_tren(len(data_tren))
        if jenis == "kosong":
            st.info("No data.")
        elif banding:
            grafik(V.grafik_tren_banding(data_tren, D.tren(df_lalu, metrik, gran), metrik),
                            use_container_width=True)
        elif jenis == "angka":
            st.metric(str(data_tren.iloc[0]["periode"].date()),
                      V.format_nilai(data_tren.iloc[0][metrik], metrik))
        else:
            event = grafik(V.grafik_tren(data_tren, metrik, jenis),
                                    use_container_width=True, key="c_tren",
                                    on_select="rerun", selection_mode="points")
            poin = poin_terpilih(event)
            if poin and poin[0].get("x") is not None:
                awal, akhir = D.rentang_periode(poin[0]["x"], gran, tgl_min, tgl_max)
                minta({"preset": "Custom", "f_tanggal": (awal, akhir)})
        if not data_tren.empty:
            tombol_unduh(data_tren.assign(periode=data_tren["periode"].dt.date),
                         f"tren_{metrik}_{gran}".replace(" ", "_"), "tren")
        catatan(f"Visual: {alasan}. Auto granularity: {alasan_gran}."
                )


# =========================
# 3. TOWER > CAMPAIGN > SUB CAMPAIGN (menyatu)
# =========================

if TAMPIL["campaign"]:
    with st.container(border=True):
        bagian("Tower › Campaign › Sub Campaign",
               "All three levels in one view. Each piece of content is counted once per category.", jangkar="campaign")
        sumber(f"{SUMBER_LAPORAN} · Labels column in the format Tower - Campaign - Sub Campaign.")
        h_tower, h_camp, h_sub, aditif = D.hierarki(df, label_hier)
        jumlah_jalur = int((h_sub["tower"] != D.TANPA_LABEL).sum())
        rekomendasi, alasan = V.pilih_visual_hierarki(aditif, jumlah_jalur)

        pilihan_tampilan = ["Treemap", "Bar per path", "Table per Sub Campaign", "Nested table"]
        default = {"treemap": 0, "bar": 1, "kosong": 2}[rekomendasi]
        tampilan = st.radio("View", pilihan_tampilan, index=default, horizontal=True,
                            key="tampilan_hier", label_visibility="collapsed")

        kolom_ukuran = {"Reach": "Reach", "Impressions": "Impressions",
                        "Engagements": "Engagements"}.get(metrik, "Impressions")
        kolom_bar = "ER (impr.)" if metrik == "Engagement rate (impr.)" else kolom_ukuran

        if jumlah_jalur == 0:
            st.info("Content in these filters has no Tower–Campaign–Sub Campaign labels.")
        elif tampilan == "Treemap":
            if aditif:
                grafik(V.grafik_treemap(h_tower, h_camp, h_sub, kolom_ukuran),
                                use_container_width=True)
                catatan(f"Box size = {kolom_ukuran}, color = Engagement rate. "
                        "Click a box to drill down, click the title above to go back.")
            else:
                st.warning("Treemap not shown: some content has more than one label "
                           "path, so Tower and Campaign figures would be double-counted. "
                           "Use 'Bar per path' or 'Nested table'.")
        elif tampilan == "Bar per path":
            event = grafik(V.grafik_jalur(h_sub, kolom_bar, metrik),
                                    use_container_width=True, key="c_jalur",
                                    on_select="rerun", selection_mode="points")
            poin = poin_terpilih(event)
            if poin and poin[0].get("customdata"):
                t, c, s = poin[0]["customdata"][:3]
                minta({"f_tower": [t], "f_campaign": [c], "f_sub_campaign": [s]})
            catatan("Each bar = one Campaign › Sub Campaign path, color = Tower. "
                    "Click a bar to filter to that path.")
        else:
            if tampilan == "Table per Sub Campaign":
                tabel = D.tabel_jalur(h_sub)
                kunci_tabel, ket = "t_jalur", "One row = one Tower › Campaign › Sub Campaign path."
            else:
                tabel = D.tabel_hierarki(h_tower, h_camp, h_sub)
                kunci_tabel, ket = "t_hier", ("Tower and Campaign rows are level totals; "
                                              "Sub Campaign rows are the breakdown.")
            tampil = tabel.copy()
            tampil["ER (impr.)"] = tampil["ER (impr.)"] * 100
            event = st.dataframe(
                tampil, hide_index=True, use_container_width=True, key=kunci_tabel,
                on_select="rerun", selection_mode="single-row",
                height=min(600, 38 + 35 * len(tampil)),
                column_config={
                    "Reach": st.column_config.NumberColumn(format="%d"),
                    "Impressions": st.column_config.NumberColumn(format="%d"),
                    "Engagements": st.column_config.NumberColumn(format="%d"),
                    "ER (impr.)": st.column_config.NumberColumn(format="%.2f%%"),
                })
            try:
                baris = event["selection"]["rows"]
            except (KeyError, TypeError):
                baris = []
            if baris:
                r = tabel.iloc[baris[0]]
                if r["Tower"] != D.TANPA_LABEL:
                    minta({"f_tower": [r["Tower"]],
                           "f_campaign": [r["Campaign"]] if r["Campaign"] else [],
                           "f_sub_campaign": [r["Sub Campaign"]] if r["Sub Campaign"] else []})
            tombol_unduh(tabel, "tower_campaign_sub_campaign", kunci_tabel)
            catatan(f"{ket} Click a row to filter the dashboard to it.")
        catatan(f"Auto recommendation: {alasan}.")


# =========================
# 4. PILLAR & FORMAT
# =========================

if TAMPIL["pillar_format"]:
    st.markdown("<div class='jangkar' id='pillar'></div>", unsafe_allow_html=True)
    kiri, kanan = st.columns(2)
    with kiri:
        kartu_breakdown(D.breakdown_label(df, label_pil, "pillar", metrik, "PILLAR"), "pillar",
                        "Pillar", f"{metrik} per content pillar", total[metrik], "c_pillar",
                        lambda v: {"f_pillar": [v]}, False)
        if (label["label_type"] == "LAINNYA").any():
            kartu_breakdown(D.breakdown_label(df, label, "label_lain", metrik, "LAINNYA"),
                            "label_lain", "Other labels",
                            f"{metrik} per label not in Pillar or "
                            "Tower - Campaign - Sub Campaign format", total[metrik], "c_lain",
                            lambda v: {"f_label_lain": [v]}, False)
    with kanan:
        kartu_breakdown(D.breakdown_atribut(df, "content_type", metrik), "content_type",
                        "Content type", f"{metrik} per content type", total[metrik], "c_ctype",
                        lambda v: {"f_content_type": [v]}, True)
        kartu_breakdown(D.breakdown_atribut(df, "media_type", metrik), "media_type",
                        "Media type", f"{metrik} per media type", total[metrik], "c_mtype",
                        lambda v: {"f_media_type": [v]}, True)


# =========================
# 5. WAKTU POSTING & PETA KONTEN
# =========================

if TAMPIL["waktu_peta"]:
    kiri, kanan = st.columns(2)
    with kiri:
        with st.container(border=True):
            satuan = "recalculated from totals" if V.is_rasio(metrik) else "average per content"
            bagian("Best time to post",
                   f"{metrik} by posting day and hour (WIB), {satuan}", jangkar="waktu")
            sumber(f"{SUMBER_LAPORAN} · Date column (posting time, WIB) + {kolom_sumber(metrik)}.")
            waktu = D.waktu_lokal(df["posted_at"])
            jenis, alasan = V.pilih_visual_waktu(D.punya_jam(waktu), int(waktu.notna().sum()))
            if jenis == "kosong":
                st.info("No posting time data.")
            elif jenis == "heatmap":
                grafik(V.grafik_heatmap(D.waktu_posting(df, metrik), metrik, D.HARI),
                                use_container_width=True)
            else:
                grafik(V.grafik_hari(D.per_hari(df, metrik), metrik),
                                use_container_width=True)
            catatan(f"Visual: {alasan}. Slots with little content are not conclusive.")

    with kanan:
        with st.container(border=True):
            bagian("Content map", "Impressions vs Engagement rate per content; dashed lines = median")
            sumber(f"{SUMBER_LAPORAN} · Total impressions and Engagements per post.")
            data_peta = D.peta_konten(df)
            jenis, log_x, alasan = V.pilih_visual_peta(data_peta)
            dipilih = None
            if jenis == "kosong":
                st.info("No content with Impressions > 0.")
            elif jenis == "tabel":
                st.dataframe(data_peta[["content_id", "total_impressions", "er"]],
                             hide_index=True, use_container_width=True)
            else:
                event = grafik(V.grafik_peta(data_peta, log_x), use_container_width=True,
                                        key="c_peta", on_select="rerun", selection_mode="points")
                poin = poin_terpilih(event)
                if poin and poin[0].get("customdata"):
                    dipilih = poin[0]["customdata"][0]
            catatan(f"Visual: {alasan}. Click a point to see details.")
            if dipilih:
                tampil_detail(dipilih)


# =========================
# 6. PERINGKAT CEPAT
# =========================

with st.container(border=True):
    bagian("Quick rankings",
           "Top 5 content for each metric in the selected period and filters", jangkar="peringkat")
    sumber(f"{SUMBER_LAPORAN} · per-post metric columns; post links from the "
           "View on platform column.")
    ada, kosong = D.metrik_tersedia(df)
    if not ada:
        st.info("No content with metric values for these filters.")
    else:
        for tab, nama in zip(st.tabs(ada), ada):
            with tab:
                kolom = D.METRIK[nama]
                data = df[df[kolom].fillna(0) > 0].nlargest(5, kolom)
                daftar_kartu(data, sorot=nama, ringkas=True)
    teks = "Tap the post text to open it on its platform."
    if not D.ada_link(df):
        teks = "Post links are not available yet, so posts cannot be opened."
    if kosong:
        teks += f" Not shown because there is no data for these filters: {', '.join(kosong)}."
    catatan(teks)


# =========================
# 7. TOP KONTEN
# =========================

with st.container(border=True):
    bagian("Top content",
           "Content ranked by the selected metric", jangkar="top")
    sumber(f"{SUMBER_LAPORAN} · one post per Content ID with its Emplifi figures; "
           "post links from the View on platform column.")
    pilihan_urut = D.PERINGKAT + list(D.RASIO)
    if st.session_state.get("urut_konten") not in pilihan_urut:
        st.session_state["urut_konten"] = metrik if metrik in pilihan_urut else "Impressions"
    a, b = st.columns([3, 1])
    urut = a.selectbox("Sort by", pilihan_urut, key="urut_konten")
    jumlah = b.selectbox("Show", [10, 25, 50], index=0, key="jumlah_konten")

    tabel = df.copy()
    for nama_r, (atas, bawah) in D.RASIO.items():
        tabel[nama_r] = tabel[atas] / tabel[bawah].where(tabel[bawah] != 0)
    tabel = tabel.sort_values(D.METRIK.get(urut, urut), ascending=False,
                              na_position="last").head(jumlah).reset_index(drop=True)
    daftar_kartu(tabel, sorot=urut)
    tombol_unduh(df.drop(columns=["labels_raw"], errors="ignore"),
                 f"emplifi_konten_{f['tanggal'][0]:%Y%m%d}_{f['tanggal'][1]:%Y%m%d}", "konten")
    catatan("Tap the post text or 'Open ↗' to view the post.")


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
