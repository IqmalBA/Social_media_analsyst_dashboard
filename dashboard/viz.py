"""
Aturan pemilihan visual adaptif.

Visual dipilih dari BENTUK data (jenis dimensi, jumlah kategori,
jumlah periode), bukan di-hardcode per kategori. Setiap pilihan
membawa alasan yang ditampilkan di dashboard agar transparan.
"""

import pandas as pd

from data import RATIOS, NO_LABEL as NO_LABEL_V

BAR_LIMIT = 15          # lebih dari ini -> tampilkan top N + tabel lengkap
COLOR = "#2a78d6"
# Palet kategorikal tervalidasi ramah buta warna (urutan tetap, tidak diputar).
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
# Warna mengikuti ENTITAS: platform yang sama selalu berwarna sama di semua grafik.
# Urutan mengikuti palet tervalidasi (3 platform pertama aman di semua pasangan warna).
PLATFORM_COLORS = {"instagram": "#2a78d6", "tiktok": "#eb6834", "facebook": "#1baf7a",
                  "youtube": "#eda100", "x": "#e87ba4", "twitter": "#e87ba4",
                  "linkedin": "#008300", "threads": "#6250d6"}
FONT = "Plus Jakarta Sans, system-ui, sans-serif"


def color_map(value, column=None):
    """{kategori: warna}. Platform memakai warna tetap; lainnya urutan abjad -> palet."""
    unique = sorted({str(v) for v in value if v is not None and str(v) != "nan"})
    result, remaining = {}, iter(PALETTE)
    for v in unique:
        fixed = PLATFORM_COLORS.get(v.lower()) if column == "platform" else None
        result[v] = fixed or next(remaining, "#8b8b85")
    return result


def is_ratio(metric):
    return metric in RATIOS


def format_value(value, metric):
    if value is None or value != value:     # None atau NaN
        return "–"
    if is_ratio(metric):
        return f"{value:.2%}"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:,.1f}K"
    return f"{value:,.0f}"


# =========================
# ATURAN
# =========================

def pick_granularity(start, end):
    days = (end - start).days + 1
    if days <= 45:
        return "Daily", f"range {days} days → daily"
    if days <= 180:
        return "Weekly", f"range {days} days → weekly"
    return "Monthly", f"range {days} days → monthly"


def pick_trend_visual(period_count):
    if period_count == 0:
        return "kosong", "no data in this range"
    if period_count == 1:
        return "angka", "only 1 period, trend cannot be shown"
    if period_count <= 3:
        return "bar", f"{period_count} periods → bar (too few for a line)"
    return "line", f"{period_count} periods → line chart"


def pick_category_visual(category_count):
    if category_count == 0:
        return "kosong", "no data"
    if category_count == 1:
        return "angka", "only 1 category"
    if category_count <= BAR_LIMIT:
        return "bar", f"{category_count} categories → sorted bar chart"
    return "bar_top", (
        f"{category_count} categories → top {BAR_LIMIT} in the chart, "
        "the rest in the table"
    )


# =========================
# PEMBUAT GRAFIK
# =========================

def _style(fig, metric, height=None):
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=height,
        font=dict(size=13, family=FONT),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        barcornerradius=4, bargap=0.35,
        hoverlabel=dict(font=dict(family=FONT)),
    )
    if any(t.type in ("bar", "scatter", "heatmap") for t in fig.data):
        fig.update_xaxes(showgrid=False, zeroline=False, linecolor="rgba(127,127,127,0.25)")
        fig.update_yaxes(gridcolor="rgba(127,127,127,0.16)", zeroline=False)
    return fig


def trend_chart(data, metric, kind):
    import plotly.express as px

    if kind == "line":
        fig = px.line(data, x="periode", y=metric, markers=True, labels={"periode": "Period"},
                      hover_data={"Content": True})
    else:
        fig = px.bar(data, x="periode", y=metric, hover_data={"Content": True},
                     labels={"periode": "Period"})
    if kind == "line":
        fig.update_traces(marker_color=COLOR, line_color=COLOR, line_width=2.5,
                          marker_size=8)
    else:
        fig.update_traces(marker_color=COLOR)      # bar tidak punya garis
    fig.update_xaxes(title=None)
    if is_ratio(metric):
        fig.update_yaxes(tickformat=".1%")
    return _style(fig, metric, 360)


def category_chart(data, column, metric, kind):
    import plotly.express as px

    shown = data.dropna(subset=[metric])
    if kind == "bar_top":
        shown = shown.head(BAR_LIMIT)
    shown = shown.iloc[::-1]          # terbesar di atas

    fig = px.bar(
        shown, x=metric, y=column, orientation="h",
        hover_data={"Content": True},
        text=[format_value(v, metric) for v in shown[metric]],
    )
    fig.update_traces(marker_color=COLOR, textposition="outside",
                      cliponaxis=False)
    fig.update_yaxes(title=None, type="category")
    if is_ratio(metric):
        fig.update_xaxes(tickformat=".1%")
    height = max(220, 34 * len(shown) + 60)
    return _style(fig, metric, height)


# =========================
# PERBANDINGAN PERIODE
# =========================

PREVIOUS_COLOR = "#94A3B8"


def comparison_trend_chart(now, previous, metric):
    """Dua periode disejajarkan per urutan (periode ke-1, ke-2, ...)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for data, name, color, line in [
        (previous, "Previous period", PREVIOUS_COLOR, "dash"),
        (now, "Selected period", COLOR, "solid"),
    ]:
        if data.empty:
            continue
        fig.add_trace(go.Scatter(
            x=list(range(1, len(data) + 1)), y=data[metric],
            name=name, mode="lines+markers",
            line=dict(color=color, dash=line),
            customdata=data["periode"].dt.strftime("%d %b %Y"),
            hovertemplate="%{customdata}<br>%{y}<extra>" + name + "</extra>",
        ))
    fig.update_xaxes(title="Period #", dtick=1 if len(now) <= 31 else None)
    if is_ratio(metric):
        fig.update_yaxes(tickformat=".1%")
    fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
    return _style(fig, metric, 380)


# =========================
# WAKTU POSTING
# =========================

MIN_HEATMAP_CONTENT = 30


def pick_time_visual(has_time, content_count):
    if content_count == 0:
        return "kosong", "no data"
    if not has_time:
        return "hari", "source data has no posting hour → by day only"
    if content_count < MIN_HEATMAP_CONTENT:
        return "hari", (f"{content_count} posts, too few for a "
                        f"day × hour heatmap (min. {MIN_HEATMAP_CONTENT}) → by day")
    return "heatmap", f"{content_count} posts with posting hour → day × hour heatmap"


def heatmap_chart(data, metric, day_name):
    import plotly.graph_objects as go

    z = [[None] * 24 for _ in range(7)]
    n = [[0] * 24 for _ in range(7)]
    for _, b in data.iterrows():
        h, j = int(b["hari"]), int(b["jam"])
        z[h][j] = None if pd.isna(b["nilai"]) else float(b["nilai"])
        n[h][j] = int(b["Content"])

    format_hover = "%{z:.2%}" if is_ratio(metric) else "%{z:,.0f}"
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{j:02d}" for j in range(24)], y=day_name,
        customdata=n, colorscale="Blues", hoverongaps=False,
        hovertemplate="%{y} %{x}:00<br>" + format_hover +
                      "<br>%{customdata} posts<extra></extra>",
        colorbar=dict(tickformat=".1%" if is_ratio(metric) else ",.0f"),
    ))
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(title="Posting hour (WIB)")
    return _style(fig, metric, 360)


def day_chart(data, metric):
    import plotly.express as px

    fig = px.bar(data, x="nama_hari", y="nilai", hover_data={"Content": True},
                 text=[format_value(v, metric) for v in data["nilai"]])
    fig.update_traces(marker_color=COLOR, textposition="outside", cliponaxis=False)
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=metric, tickformat=".1%" if is_ratio(metric) else None)
    return _style(fig, metric, 340)


# =========================
# PETA KONTEN
# =========================

def pick_map_visual(data):
    n = len(data)
    if n == 0:
        return "kosong", False, "no content with Impressions > 0"
    if n < 3:
        return "tabel", False, f"only {n} posts → table"
    ratio = data["total_impressions"].max() / max(data["total_impressions"].min(), 1)
    if ratio > 100:
        return "scatter", True, (f"{n} posts, Impressions differ >100× "
                                 "→ logarithmic Impressions axis")
    return "scatter", False, f"{n} posts → scatter plot"


def map_chart(data, log_x):
    import plotly.express as px

    fig = px.scatter(
        data, x="total_impressions", y="er", color="platform",
        color_discrete_map=color_map(data["platform"], "platform"),
        log_x=log_x, custom_data=["content_id"],
        hover_data={"content_id": True, "post_date": True, "profile_name": True,
                    "engagements": ":,", "total_impressions": ":,", "er": ":.2%",
                    "platform": False},
        labels={"total_impressions": "Impressions",
                "er": "Engagement rate (impr.)", "platform": "Platform"},
    )
    med_x = data["total_impressions"].median()
    med_y = data["er"].median()
    fig.add_vline(x=med_x, line_dash="dot", line_color=PREVIOUS_COLOR)
    fig.add_hline(y=med_y, line_dash="dot", line_color=PREVIOUS_COLOR)
    for x, y, text, xa, yes in [
        (1, 1, "High reach & engagement", "right", "top"),
        (0, 1, "High engagement, low reach", "left", "top"),
        (1, 0, "High reach, low engagement", "right", "bottom"),
    ]:
        fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=text,
                           showarrow=False, xanchor=xa, yanchor=yes,
                           font=dict(size=11, color="#64748B"))
    fig.update_traces(marker=dict(size=10, opacity=0.75))
    fig.update_yaxes(tickformat=".1%")
    fig.update_layout(legend=dict(orientation="h", y=-0.15, x=0))
    return _style(fig, "Engagement rate (impr.)", 460)


# =========================
# KONTRIBUSI
# =========================




def pick_contribution_visual(n):
    if n == 0:
        return "kosong", "no data"
    if n == 1:
        return "angka", "only 1 category (100%)"
    if n <= 6:
        return "donut", f"{n} categories → donut (share of total)"
    return "bar", f"{n} categories → percent bar (too many for a donut)"


def contribution_chart(data, column, value, kind):
    import plotly.express as px

    if kind == "donut":
        fig = px.pie(data, names=column, values=value, hole=0.6,
                     color=column, color_discrete_map=color_map(data[column], column))
        fig.update_traces(textinfo="percent", sort=True,
                          hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>")
        fig.update_layout(legend=dict(orientation="v", x=1, y=0.5))
        return _style(fig, value, 300)

    shown = data.head(BAR_LIMIT).iloc[::-1]
    fig = px.bar(shown, x="Percent", y=column, orientation="h",
                 text=[f"{p:.1%}" for p in shown["Percent"]],
                 hover_data={value: ":,.0f", "Percent": ":.1%"})
    fig.update_traces(marker_color=COLOR, textposition="outside", cliponaxis=False)
    fig.update_xaxes(tickformat=".0%", title=None)
    fig.update_yaxes(title=None, type="category")
    return _style(fig, value, max(220, 34 * len(shown) + 60))


# =========================
# TOWER > CAMPAIGN > SUB CAMPAIGN
# =========================

def pick_hierarchy_visual(additive, path_count):
    if path_count == 0:
        return "kosong", "no data"
    if additive and path_count >= 2:
        return "treemap", ("each post has only 1 Tower–Campaign–Sub path → "
                           "treemap (parent = sum of children)")
    if not additive:
        return "bar", ("some content has more than 1 label path → treemap not "
                       "used because parent figures would be double-counted; shown "
                       "per path")
    return "bar", "only 1 path"


def treemap_chart(tower, campaign, sub, size):
    """ukuran = metrik jumlah (Reach/Impressions/Engagements). Warna = ER."""
    import plotly.graph_objects as go

    ids, labels, parents, values, er, content = [], [], [], [], [], []

    def add(id_, label, parent, row):
        ids.append(id_); labels.append(label); parents.append(parent)
        v = row[size]
        values.append(0 if pd.isna(v) else float(v))
        er.append(None if pd.isna(row["ER (impr.)"]) else float(row["ER (impr.)"]))
        content.append(int(row["Content"]))

    for _, t in tower.iterrows():
        add(f"T|{t['tower']}", t["tower"], "", t)
    for _, c in campaign.iterrows():
        if c["campaign"] == NO_LABEL_V:
            continue
        add(f"C|{c['tower']}|{c['campaign']}", c["campaign"], f"T|{c['tower']}", c)
    for _, s in sub.iterrows():
        if s["sub_campaign"] == NO_LABEL_V:
            continue
        add(f"S|{s['tower']}|{s['campaign']}|{s['sub_campaign']}", s["sub_campaign"],
               f"C|{s['tower']}|{s['campaign']}", s)

    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values,
        branchvalues="total", customdata=list(zip(content, er)),
        marker=dict(colors=[e if e is not None else 0 for e in er],
                    colorscale="Blues", showscale=True,
                    colorbar=dict(title="ER", tickformat=".1%")),
        texttemplate="<b>%{label}</b><br>%{value:,.0f}",
        hovertemplate=("<b>%{label}</b><br>" + size + ": %{value:,.0f}"
                       "<br>Content: %{customdata[0]}"
                       "<br>ER (impr.): %{customdata[1]:.2%}<extra></extra>"),
        root_color="rgba(0,0,0,0)",
    ))
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=480)
    return fig


def path_chart(sub, metric_column, metric):
    """Bar per jalur lengkap Tower › Campaign › Sub, diwarnai per Tower."""
    import plotly.express as px

    data = sub[sub["tower"] != NO_LABEL_V].copy()
    data["Path"] = data["tower"] + " › " + data["campaign"] + " › " + data["sub_campaign"]
    data = data.dropna(subset=[metric_column]).sort_values(metric_column, ascending=False)
    data = data.head(BAR_LIMIT * 2).iloc[::-1]
    fig = px.bar(
        data, x=metric_column, y="Path", color="tower", orientation="h",
        custom_data=["tower", "campaign", "sub_campaign"],
        color_discrete_map=color_map(data["tower"]),
        hover_data={"Content": True, "tower": True, "campaign": True,
                    "sub_campaign": True, "Path": False},
        labels={"tower": "Tower", "campaign": "Campaign",
                "sub_campaign": "Sub Campaign", metric_column: metric},
    )
    fig.update_yaxes(title=None, type="category")
    if is_ratio(metric):
        fig.update_xaxes(tickformat=".1%")
    fig.update_layout(legend=dict(orientation="h", y=1.02, x=0, title=None))
    return _style(fig, metric, max(260, 30 * len(data) + 90))


# =========================
# TOPIK / HASHTAG
# =========================

def topic_chart(data, prefix=""):
    """Bar horizontal: jumlah postingan per topik, warna = engagement rate."""
    import plotly.express as px

    shown = data.copy()
    shown["label"] = prefix + shown["topik"].astype(str)
    shown = shown.iloc[::-1]
    fig = px.bar(shown, x="Posts", y="label", orientation="h", color="ER",
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
    return _style(fig, "Posts", max(240, 32 * len(shown) + 70))


# =========================
# SENTIMEN KOMENTAR
# =========================

SENTIMENT_COLORS = {"Positive": "#16A34A", "Neutral": "#94A3B8", "Negative": "#DC2626"}


def brand_sentiment_chart(data):
    """Bar 100% bertumpuk per brand: porsi komentar positif / netral / negatif."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for name in ["Positive", "Neutral", "Negative"]:
        fig.add_trace(go.Bar(
            y=data["profile_name"], x=data[name], name=name, orientation="h",
            marker_color=SENTIMENT_COLORS[name],
            text=[f"{v:.0%}" if v >= 0.06 else "" for v in data[name]],
            textposition="inside", customdata=data["total"],
            hovertemplate="%{y}<br>" + name + ": %{x:.1%}<br>%{customdata:,.0f} comments"
                          "<extra></extra>"))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(tickformat=".0%", range=[0, 1], title=None)
    fig.update_yaxes(title=None, type="category")
    return _style(fig, "Positive", max(200, 40 * len(data) + 90))


# =========================
# KOMPETITOR
# =========================

RIVAL_COLOR = "#94A3B8"


def brand_chart(data, own):
    """Bar horizontal porsi Total interactions per brand; akun sendiri disorot."""
    import plotly.graph_objects as go

    shown = data.iloc[::-1]
    fig = go.Figure(go.Bar(
        y=shown["Brand"], x=shown["Interaction share"], orientation="h",
        marker_color=[COLOR if b == own else RIVAL_COLOR for b in shown["Brand"]],
        text=[f"{v:.0%}" for v in shown["Interaction share"].fillna(0)],
        textposition="outside", cliponaxis=False,
        customdata=shown[["Interactions", "Posts", "Interactions per post"]].to_numpy(),
        hovertemplate="<b>%{y}</b><br>Interaction share %{x:.1%}<br>%{customdata[0]:,.0f} "
                      "interactions from %{customdata[1]:,.0f} posts"
                      "<br>%{customdata[2]:,.0f} per post<extra></extra>"))
    fig.update_xaxes(tickformat=".0%", title="Share of Total interactions")
    fig.update_yaxes(title=None, type="category")
    return _style(fig, "Share", max(220, 40 * len(shown) + 70))


# =========================
# TEMA TERANG / GELAP
# =========================
# Palet gelap = hue yang sama, langkah khusus untuk latar gelap (tervalidasi ramah
# buta warna dan kontras >= 3:1 terhadap kartu gelap #141B2D).
LIGHT_TO_DARK = {
    "#2a78d6": "#3987e5", "#eb6834": "#d95926", "#1baf7a": "#199e70", "#eda100": "#c98500",
    "#e87ba4": "#d55181", "#008300": "#0ca30c", "#6250d6": "#9085e9", "#e34948": "#e66767",
    "#64748b": "#94a3b8", "#94a3b8": "#64748b",
}


def _swap_color(value, lookup):
    if isinstance(value, str):
        return lookup.get(value.lower(), value)
    if isinstance(value, (list, tuple)):
        return [_swap_color(v, lookup) for v in value]
    return value


def apply_theme(fig, dark):
    """Dipanggil untuk SETIAP grafik sebelum ditampilkan."""
    text = "#E2E8F0" if dark else "#0F172A"
    muted = "#94A3B8" if dark else "#64748B"
    grid = "rgba(148,163,184,0.16)" if dark else "rgba(15,23,42,0.07)"
    line = "rgba(148,163,184,0.30)" if dark else "rgba(15,23,42,0.18)"
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=text, family=FONT),
        legend=dict(font=dict(color=text)),
        hoverlabel=dict(bgcolor="#0F172A" if dark else "#FFFFFF",
                        font=dict(color=text, family=FONT), bordercolor=line),
    )
    if any(t.type in ("bar", "scatter", "heatmap") for t in fig.data):
        for axis in (fig.update_xaxes, fig.update_yaxes):
            axis(gridcolor=grid, linecolor=line, tickfont=dict(color=muted),
                  title_font=dict(color=muted), zeroline=False)
    for a in fig.layout.annotations or []:
        a.font.color = muted
    if dark:
        for t in fig.data:
            m = getattr(t, "marker", None)
            if m is not None:
                if getattr(m, "color", None) is not None:
                    m.color = _swap_color(m.color, LIGHT_TO_DARK)
                if getattr(m, "colors", None) is not None:
                    m.colors = _swap_color(list(m.colors), LIGHT_TO_DARK)
            ln = getattr(t, "line", None)
            if ln is not None and getattr(ln, "color", None) is not None:
                ln.color = _swap_color(ln.color, LIGHT_TO_DARK)
    for shape in fig.layout.shapes or []:                 # garis median peta konten
        if shape.line and shape.line.color:
            shape.line.color = muted
    return fig
