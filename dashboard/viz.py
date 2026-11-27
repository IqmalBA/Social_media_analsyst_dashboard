"""
Aturan pemilihan visual adaptif.

Visual dipilih dari BENTUK data (jenis dimensi, jumlah kategori,
jumlah periode), bukan di-hardcode per kategori. Setiap pilihan
membawa alasan yang ditampilkan di dashboard agar transparan.
"""

import pandas as pd

from data import RASIO, TANPA_LABEL as TANPA_LABEL_V

BATAS_BAR = 15          # lebih dari ini -> tampilkan top N + tabel lengkap
WARNA = "#2a78d6"
# Palet kategorikal tervalidasi ramah buta warna (urutan tetap, tidak diputar).
PALET = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
# Warna mengikuti ENTITAS: platform yang sama selalu berwarna sama di semua grafik.
# Urutan mengikuti palet tervalidasi (3 platform pertama aman di semua pasangan warna).
WARNA_PLATFORM = {"instagram": "#2a78d6", "tiktok": "#eb6834", "facebook": "#1baf7a",
                  "youtube": "#eda100", "x": "#e87ba4", "twitter": "#e87ba4",
                  "linkedin": "#008300", "threads": "#6250d6"}
FONT = "Plus Jakarta Sans, system-ui, sans-serif"


def peta_warna(nilai, kolom=None):
    """{kategori: warna}. Platform memakai warna tetap; lainnya urutan abjad -> palet."""
    unik = sorted({str(v) for v in nilai if v is not None and str(v) != "nan"})
    hasil, sisa = {}, iter(PALET)
    for v in unik:
        tetap = WARNA_PLATFORM.get(v.lower()) if kolom == "platform" else None
        hasil[v] = tetap or next(sisa, "#8b8b85")
    return hasil


def is_rasio(metrik):
    return metrik in RASIO


def format_nilai(nilai, metrik):
    if nilai is None or nilai != nilai:     # None atau NaN
        return "–"
    if is_rasio(metrik):
        return f"{nilai:.2%}"
    if abs(nilai) >= 1_000_000:
        return f"{nilai / 1_000_000:,.2f}M"
    if abs(nilai) >= 1_000:
        return f"{nilai / 1_000:,.1f}K"
    return f"{nilai:,.0f}"


# =========================
# ATURAN
# =========================

def pilih_granularitas(awal, akhir):
    hari = (akhir - awal).days + 1
    if hari <= 45:
        return "Daily", f"range {hari} days → daily"
    if hari <= 180:
        return "Weekly", f"range {hari} days → weekly"
    return "Monthly", f"range {hari} days → monthly"


def pilih_visual_tren(jumlah_periode):
    if jumlah_periode == 0:
        return "kosong", "no data in this range"
    if jumlah_periode == 1:
        return "angka", "only 1 period, trend cannot be shown"
    if jumlah_periode <= 3:
        return "bar", f"{jumlah_periode} periods → bar (too few for a line)"
    return "line", f"{jumlah_periode} periods → line chart"


def pilih_visual_kategori(jumlah_kategori):
    if jumlah_kategori == 0:
        return "kosong", "no data"
    if jumlah_kategori == 1:
        return "angka", "only 1 category"
    if jumlah_kategori <= BATAS_BAR:
        return "bar", f"{jumlah_kategori} categories → sorted bar chart"
    return "bar_top", (
        f"{jumlah_kategori} categories → top {BATAS_BAR} in the chart, "
        "the rest in the table"
    )


# =========================
# PEMBUAT GRAFIK
# =========================

def _gaya(fig, metrik, tinggi=None):
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=tinggi,
        font=dict(size=13, family=FONT),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        barcornerradius=4, bargap=0.35,
        hoverlabel=dict(font=dict(family=FONT)),
    )
    if any(t.type in ("bar", "scatter", "heatmap") for t in fig.data):
        fig.update_xaxes(showgrid=False, zeroline=False, linecolor="rgba(127,127,127,0.25)")
        fig.update_yaxes(gridcolor="rgba(127,127,127,0.16)", zeroline=False)
    return fig


def grafik_tren(data, metrik, jenis):
    import plotly.express as px

    if jenis == "line":
        fig = px.line(data, x="periode", y=metrik, markers=True, labels={"periode": "Period"},
                      hover_data={"Content": True})
    else:
        fig = px.bar(data, x="periode", y=metrik, hover_data={"Content": True},
                     labels={"periode": "Period"})
    if jenis == "line":
        fig.update_traces(marker_color=WARNA, line_color=WARNA, line_width=2.5,
                          marker_size=8)
    else:
        fig.update_traces(marker_color=WARNA)      # bar tidak punya garis
    fig.update_xaxes(title=None)
    if is_rasio(metrik):
        fig.update_yaxes(tickformat=".1%")
    return _gaya(fig, metrik, 360)


def grafik_kategori(data, kolom, metrik, jenis):
    import plotly.express as px

    tampil = data.dropna(subset=[metrik])
    if jenis == "bar_top":
        tampil = tampil.head(BATAS_BAR)
    tampil = tampil.iloc[::-1]          # terbesar di atas

    fig = px.bar(
        tampil, x=metrik, y=kolom, orientation="h",
        hover_data={"Content": True},
        text=[format_nilai(v, metrik) for v in tampil[metrik]],
    )
    fig.update_traces(marker_color=WARNA, textposition="outside",
                      cliponaxis=False)
    fig.update_yaxes(title=None, type="category")
    if is_rasio(metrik):
        fig.update_xaxes(tickformat=".1%")
    tinggi = max(220, 34 * len(tampil) + 60)
    return _gaya(fig, metrik, tinggi)


# =========================
# PERBANDINGAN PERIODE
# =========================

WARNA_LALU = "#94A3B8"


def grafik_tren_banding(sekarang, lalu, metrik):
    """Dua periode disejajarkan per urutan (periode ke-1, ke-2, ...)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for data, nama, warna, garis in [
        (lalu, "Previous period", WARNA_LALU, "dash"),
        (sekarang, "Selected period", WARNA, "solid"),
    ]:
        if data.empty:
            continue
        fig.add_trace(go.Scatter(
            x=list(range(1, len(data) + 1)), y=data[metrik],
            name=nama, mode="lines+markers",
            line=dict(color=warna, dash=garis),
            customdata=data["periode"].dt.strftime("%d %b %Y"),
            hovertemplate="%{customdata}<br>%{y}<extra>" + nama + "</extra>",
        ))
    fig.update_xaxes(title="Period #", dtick=1 if len(sekarang) <= 31 else None)
    if is_rasio(metrik):
        fig.update_yaxes(tickformat=".1%")
    fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
    return _gaya(fig, metrik, 380)


# =========================
# WAKTU POSTING
# =========================

MIN_KONTEN_HEATMAP = 30


def pilih_visual_waktu(ada_jam, jumlah_konten):
    if jumlah_konten == 0:
        return "kosong", "no data"
    if not ada_jam:
        return "hari", "source data has no posting hour → by day only"
    if jumlah_konten < MIN_KONTEN_HEATMAP:
        return "hari", (f"{jumlah_konten} posts, too few for a "
                        f"day × hour heatmap (min. {MIN_KONTEN_HEATMAP}) → by day")
    return "heatmap", f"{jumlah_konten} posts with posting hour → day × hour heatmap"


def grafik_heatmap(data, metrik, nama_hari):
    import plotly.graph_objects as go

    z = [[None] * 24 for _ in range(7)]
    n = [[0] * 24 for _ in range(7)]
    for _, b in data.iterrows():
        h, j = int(b["hari"]), int(b["jam"])
        z[h][j] = None if pd.isna(b["nilai"]) else float(b["nilai"])
        n[h][j] = int(b["Content"])

    format_hover = "%{z:.2%}" if is_rasio(metrik) else "%{z:,.0f}"
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{j:02d}" for j in range(24)], y=nama_hari,
        customdata=n, colorscale="Blues", hoverongaps=False,
        hovertemplate="%{y} %{x}:00<br>" + format_hover +
                      "<br>%{customdata} posts<extra></extra>",
        colorbar=dict(tickformat=".1%" if is_rasio(metrik) else ",.0f"),
    ))
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(title="Posting hour (WIB)")
    return _gaya(fig, metrik, 360)


def grafik_hari(data, metrik):
    import plotly.express as px

    fig = px.bar(data, x="nama_hari", y="nilai", hover_data={"Content": True},
                 text=[format_nilai(v, metrik) for v in data["nilai"]])
    fig.update_traces(marker_color=WARNA, textposition="outside", cliponaxis=False)
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=metrik, tickformat=".1%" if is_rasio(metrik) else None)
    return _gaya(fig, metrik, 340)


# =========================
# PETA KONTEN
# =========================

def pilih_visual_peta(data):
    n = len(data)
    if n == 0:
        return "kosong", False, "no content with Impressions > 0"
    if n < 3:
        return "tabel", False, f"only {n} posts → table"
    rasio = data["total_impressions"].max() / max(data["total_impressions"].min(), 1)
    if rasio > 100:
        return "scatter", True, (f"{n} posts, Impressions differ >100× "
                                 "→ logarithmic Impressions axis")
    return "scatter", False, f"{n} posts → scatter plot"


def grafik_peta(data, log_x):
    import plotly.express as px

    fig = px.scatter(
        data, x="total_impressions", y="er", color="platform",
        color_discrete_map=peta_warna(data["platform"], "platform"),
        log_x=log_x, custom_data=["content_id"],
        hover_data={"content_id": True, "post_date": True, "profile_name": True,
                    "engagements": ":,", "total_impressions": ":,", "er": ":.2%",
                    "platform": False},
        labels={"total_impressions": "Impressions",
                "er": "Engagement rate (impr.)", "platform": "Platform"},
    )
    med_x = data["total_impressions"].median()
    med_y = data["er"].median()
    fig.add_vline(x=med_x, line_dash="dot", line_color=WARNA_LALU)
    fig.add_hline(y=med_y, line_dash="dot", line_color=WARNA_LALU)
    for x, y, teks, xa, ya in [
        (1, 1, "High reach & engagement", "right", "top"),
        (0, 1, "High engagement, low reach", "left", "top"),
        (1, 0, "High reach, low engagement", "right", "bottom"),
    ]:
        fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=teks,
                           showarrow=False, xanchor=xa, yanchor=ya,
                           font=dict(size=11, color="#64748B"))
    fig.update_traces(marker=dict(size=10, opacity=0.75))
    fig.update_yaxes(tickformat=".1%")
    fig.update_layout(legend=dict(orientation="h", y=-0.15, x=0))
    return _gaya(fig, "Engagement rate (impr.)", 460)


# =========================
# KONTRIBUSI
# =========================




def pilih_visual_kontribusi(n):
    if n == 0:
        return "kosong", "no data"
    if n == 1:
        return "angka", "only 1 category (100%)"
    if n <= 6:
        return "donut", f"{n} categories → donut (share of total)"
    return "bar", f"{n} categories → percent bar (too many for a donut)"


def grafik_kontribusi(data, kolom, nilai, jenis):
    import plotly.express as px

    if jenis == "donut":
        fig = px.pie(data, names=kolom, values=nilai, hole=0.6,
                     color=kolom, color_discrete_map=peta_warna(data[kolom], kolom))
        fig.update_traces(textinfo="percent", sort=True,
                          hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>")
        fig.update_layout(legend=dict(orientation="v", x=1, y=0.5))
        return _gaya(fig, nilai, 300)

    tampil = data.head(BATAS_BAR).iloc[::-1]
    fig = px.bar(tampil, x="Percent", y=kolom, orientation="h",
                 text=[f"{p:.1%}" for p in tampil["Percent"]],
                 hover_data={nilai: ":,.0f", "Percent": ":.1%"})
    fig.update_traces(marker_color=WARNA, textposition="outside", cliponaxis=False)
    fig.update_xaxes(tickformat=".0%", title=None)
    fig.update_yaxes(title=None, type="category")
    return _gaya(fig, nilai, max(220, 34 * len(tampil) + 60))


# =========================
# TOWER > CAMPAIGN > SUB CAMPAIGN
# =========================

def pilih_visual_hierarki(aditif, jumlah_jalur):
    if jumlah_jalur == 0:
        return "kosong", "no data"
    if aditif and jumlah_jalur >= 2:
        return "treemap", ("each post has only 1 Tower–Campaign–Sub path → "
                           "treemap (parent = sum of children)")
    if not aditif:
        return "bar", ("some content has more than 1 label path → treemap not "
                       "used because parent figures would be double-counted; shown "
                       "per path")
    return "bar", "only 1 path"


def grafik_treemap(tower, campaign, sub, ukuran):
    """ukuran = metrik jumlah (Reach/Impressions/Engagements). Warna = ER."""
    import plotly.graph_objects as go

    ids, labels, parents, values, er, konten = [], [], [], [], [], []

    def tambah(id_, label, parent, baris):
        ids.append(id_); labels.append(label); parents.append(parent)
        v = baris[ukuran]
        values.append(0 if pd.isna(v) else float(v))
        er.append(None if pd.isna(baris["ER (impr.)"]) else float(baris["ER (impr.)"]))
        konten.append(int(baris["Content"]))

    for _, t in tower.iterrows():
        tambah(f"T|{t['tower']}", t["tower"], "", t)
    for _, c in campaign.iterrows():
        if c["campaign"] == TANPA_LABEL_V:
            continue
        tambah(f"C|{c['tower']}|{c['campaign']}", c["campaign"], f"T|{c['tower']}", c)
    for _, s in sub.iterrows():
        if s["sub_campaign"] == TANPA_LABEL_V:
            continue
        tambah(f"S|{s['tower']}|{s['campaign']}|{s['sub_campaign']}", s["sub_campaign"],
               f"C|{s['tower']}|{s['campaign']}", s)

    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values,
        branchvalues="total", customdata=list(zip(konten, er)),
        marker=dict(colors=[e if e is not None else 0 for e in er],
                    colorscale="Blues", showscale=True,
                    colorbar=dict(title="ER", tickformat=".1%")),
        texttemplate="<b>%{label}</b><br>%{value:,.0f}",
        hovertemplate=("<b>%{label}</b><br>" + ukuran + ": %{value:,.0f}"
                       "<br>Content: %{customdata[0]}"
                       "<br>ER (impr.): %{customdata[1]:.2%}<extra></extra>"),
        root_color="rgba(0,0,0,0)",
    ))
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=480)
    return fig


def grafik_jalur(sub, metrik_kolom, metrik):
    """Bar per jalur lengkap Tower › Campaign › Sub, diwarnai per Tower."""
    import plotly.express as px

    data = sub[sub["tower"] != TANPA_LABEL_V].copy()
    data["Path"] = data["tower"] + " › " + data["campaign"] + " › " + data["sub_campaign"]
    data = data.dropna(subset=[metrik_kolom]).sort_values(metrik_kolom, ascending=False)
    data = data.head(BATAS_BAR * 2).iloc[::-1]
    fig = px.bar(
        data, x=metrik_kolom, y="Path", color="tower", orientation="h",
        custom_data=["tower", "campaign", "sub_campaign"],
        color_discrete_map=peta_warna(data["tower"]),
        hover_data={"Content": True, "tower": True, "campaign": True,
                    "sub_campaign": True, "Path": False},
        labels={"tower": "Tower", "campaign": "Campaign",
                "sub_campaign": "Sub Campaign", metrik_kolom: metrik},
    )
    fig.update_yaxes(title=None, type="category")
    if is_rasio(metrik):
        fig.update_xaxes(tickformat=".1%")
    fig.update_layout(legend=dict(orientation="h", y=1.02, x=0, title=None))
    return _gaya(fig, metrik, max(260, 30 * len(data) + 90))


# =========================
# TOPIK / HASHTAG
# =========================

def grafik_topik(data, awalan=""):
    """Bar horizontal: jumlah postingan per topik, warna = engagement rate."""
    import plotly.express as px

    tampil = data.copy()
    tampil["label"] = awalan + tampil["topik"].astype(str)
    tampil = tampil.iloc[::-1]
    fig = px.bar(tampil, x="Posts", y="label", orientation="h", color="ER",
                 color_continuous_scale="Blues",
                 custom_data=["Posts (prev.)", "Engagements", "ER"],
                 text="Posts")
    fig.update_traces(textposition="outside", cliponaxis=False,
                      hovertemplate="<b>%{y}</b><br>%{x} posts (previously %{customdata[0]})"
                                    "<br>Engagements %{customdata[1]:,.0f}"
                                    "<br>ER %{customdata[2]:.2%}<extra></extra>")
    fig.update_yaxes(title=None, type="category")
    fig.update_xaxes(title="Number of posts")
    fig.update_layout(coloraxis_colorbar=dict(title="ER", tickformat=".1%"))
    return _gaya(fig, "Posts", max(240, 32 * len(tampil) + 70))


# =========================
# SENTIMEN KOMENTAR
# =========================

WARNA_SENTIMEN = {"Positive": "#16A34A", "Neutral": "#94A3B8", "Negative": "#DC2626"}


def grafik_sentimen_brand(data):
    """Bar 100% bertumpuk per brand: porsi komentar positif / netral / negatif."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for nama in ["Positive", "Neutral", "Negative"]:
        fig.add_trace(go.Bar(
            y=data["profile_name"], x=data[nama], name=nama, orientation="h",
            marker_color=WARNA_SENTIMEN[nama],
            text=[f"{v:.0%}" if v >= 0.06 else "" for v in data[nama]],
            textposition="inside", customdata=data["total"],
            hovertemplate="%{y}<br>" + nama + ": %{x:.1%}<br>%{customdata:,.0f} comments"
                          "<extra></extra>"))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(tickformat=".0%", range=[0, 1], title=None)
    fig.update_yaxes(title=None, type="category")
    return _gaya(fig, "Positive", max(200, 40 * len(data) + 90))


# =========================
# KOMPETITOR
# =========================

WARNA_PESAING = "#94A3B8"


def grafik_brand(data, sendiri):
    """Bar horizontal porsi Total interactions per brand; akun sendiri disorot."""
    import plotly.graph_objects as go

    tampil = data.iloc[::-1]
    fig = go.Figure(go.Bar(
        y=tampil["Brand"], x=tampil["Interaction share"], orientation="h",
        marker_color=[WARNA if b == sendiri else WARNA_PESAING for b in tampil["Brand"]],
        text=[f"{v:.0%}" for v in tampil["Interaction share"].fillna(0)],
        textposition="outside", cliponaxis=False,
        customdata=tampil[["Interactions", "Posts", "Interactions per post"]].to_numpy(),
        hovertemplate="<b>%{y}</b><br>Interaction share %{x:.1%}<br>%{customdata[0]:,.0f} "
                      "interactions from %{customdata[1]:,.0f} posts"
                      "<br>%{customdata[2]:,.0f} per post<extra></extra>"))
    fig.update_xaxes(tickformat=".0%", title="Share of Total interactions")
    fig.update_yaxes(title=None, type="category")
    return _gaya(fig, "Share", max(220, 40 * len(tampil) + 70))


# =========================
# TEMA TERANG / GELAP
# =========================
# Palet gelap = hue yang sama, langkah khusus untuk latar gelap (tervalidasi ramah
# buta warna dan kontras >= 3:1 terhadap kartu gelap #141B2D).
TERANG_KE_GELAP = {
    "#2a78d6": "#3987e5", "#eb6834": "#d95926", "#1baf7a": "#199e70", "#eda100": "#c98500",
    "#e87ba4": "#d55181", "#008300": "#0ca30c", "#6250d6": "#9085e9", "#e34948": "#e66767",
    "#64748b": "#94a3b8", "#94a3b8": "#64748b",
}


def _ganti_warna(nilai, peta):
    if isinstance(nilai, str):
        return peta.get(nilai.lower(), nilai)
    if isinstance(nilai, (list, tuple)):
        return [_ganti_warna(v, peta) for v in nilai]
    return nilai


def terapkan_tema(fig, gelap):
    """Dipanggil untuk SETIAP grafik sebelum ditampilkan."""
    teks = "#E2E8F0" if gelap else "#0F172A"
    redup = "#94A3B8" if gelap else "#64748B"
    grid = "rgba(148,163,184,0.16)" if gelap else "rgba(15,23,42,0.07)"
    garis = "rgba(148,163,184,0.30)" if gelap else "rgba(15,23,42,0.18)"
    fig.update_layout(
        template="plotly_dark" if gelap else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=teks, family=FONT),
        legend=dict(font=dict(color=teks)),
        hoverlabel=dict(bgcolor="#0F172A" if gelap else "#FFFFFF",
                        font=dict(color=teks, family=FONT), bordercolor=garis),
    )
    if any(t.type in ("bar", "scatter", "heatmap") for t in fig.data):
        for sumbu in (fig.update_xaxes, fig.update_yaxes):
            sumbu(gridcolor=grid, linecolor=garis, tickfont=dict(color=redup),
                  title_font=dict(color=redup), zeroline=False)
    for a in fig.layout.annotations or []:
        a.font.color = redup
    if gelap:
        for t in fig.data:
            m = getattr(t, "marker", None)
            if m is not None:
                if getattr(m, "color", None) is not None:
                    m.color = _ganti_warna(m.color, TERANG_KE_GELAP)
                if getattr(m, "colors", None) is not None:
                    m.colors = _ganti_warna(list(m.colors), TERANG_KE_GELAP)
            ln = getattr(t, "line", None)
            if ln is not None and getattr(ln, "color", None) is not None:
                ln.color = _ganti_warna(ln.color, TERANG_KE_GELAP)
    for bentuk in fig.layout.shapes or []:                 # garis median peta konten
        if bentuk.line and bentuk.line.color:
            bentuk.line.color = redup
    return fig
