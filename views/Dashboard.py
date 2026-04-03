"""
PAGE 2 — DASHBOARD STATISTIQUES
Graphes et indicateurs clés sur les données agricoles de Kolda
Dépendances : plotly, streamlit
"""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))

from utils import get_connection, get_config, DB_PATH

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False


# ══════════════════════════════════════════════════════════════
# CONFIG & THEME
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def load_config() -> dict:
    with get_connection() as conn:
        return get_config(conn)

def cfg(key, default=""):
    return st.session_state.get("_config", {}).get(key, default)

def apply_theme():
    if "_config" not in st.session_state:
        st.session_state["_config"] = load_config()
    primary       = cfg("color_primary",       "#3fb950")
    font          = cfg("font_family",          "IBM Plex Mono, sans-serif").split(",")[0].strip()
    hdr_bg        = cfg("header_bg_color",      "#1c2a1e")
    hdr_border    = cfg("header_border_color",  "#3fb950")
    hdr_text      = cfg("header_text_color",    "#e6edf3")
    tab_active    = cfg("tab_active_color",     "#3fb950")
    subtab_active = cfg("subtab_active_color",  "#58a6ff")
    body_bg       = cfg("body_bg_color",        "#0d1117")   # Nouvelle couleur de fond générale

    def _hex_rgba(h, a=0.07):
        h = h.lstrip("#")
        if len(h) == 6:
            r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"
        return f"rgba(63,185,80,{a})"

    tab_bg    = _hex_rgba(tab_active)    if tab_active.startswith("#")    else "rgba(63,185,80,0.07)"
    subtab_bg = _hex_rgba(subtab_active) if subtab_active.startswith("#") else "rgba(88,166,255,0.07)"

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: '{font}', sans-serif !important; }}
    .main .block-container {{ padding-top: 0 !important; margin-top: 0 !important; }}
    header[data-testid="stHeader"] {{ height: 0 !important; }}
    .stApp {{
        background-color: {body_bg} !important;
    }}
    .stButton > button[kind="primary"] {{ background-color: {primary} !important; border-color: {primary} !important; }}
    [data-baseweb="tab-list"] {{ gap: 0 !important; width: 100% !important; }}
    [data-baseweb="tab"] {{
        flex: 1 1 0 !important; justify-content: center !important;
        padding: 10px 4px !important; font-size: 0.83rem !important;
        font-weight: 500 !important; border-bottom: 2px solid transparent !important;
    }}
    [data-baseweb="tab"][aria-selected="true"] {{
        border-bottom-color: {tab_active} !important;
        color: {tab_active} !important; background: {tab_bg} !important;
    }}
    .stTabs .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        border-bottom-color: {subtab_active} !important;
        color: {subtab_active} !important; background: {subtab_bg} !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    return {"primary": primary, "hdr_bg": hdr_bg,
            "hdr_border": hdr_border, "hdr_text": hdr_text}


def render_header(theme, nb_campagnes, nb_cultures, prod_total, sup_total):
    st.markdown(f"""
<div style='background:{theme["hdr_bg"]};border:1px solid rgba(255,255,255,0.06);
            border-left:4px solid {theme["hdr_border"]};
            border-radius:0 0 12px 12px;padding:18px 32px 16px;margin:-1px 0 20px 0;'>
  <div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>
    <span style='font-size:1.45rem;line-height:1;'>📊</span>
    <h1 style='margin:0;font-size:1.45rem;font-weight:700;color:{theme["hdr_text"]};letter-spacing:-.01em;'>
      Dashboard Statistiques
    </h1>
  </div>
  <p style='margin:0 0 12px;color:#8b949e;font-size:.83rem;text-align:center;'>
    Région de Kolda — Analyses et indicateurs agricoles
  </p>
  <div style='display:flex;justify-content:center;gap:8px;flex-wrap:wrap;'>
    <span style='background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3);border-radius:20px;padding:3px 12px;font-size:.78rem;'>● {nb_campagnes} campagne(s)</span>
    <span style='background:rgba(88,166,255,.1);color:#58a6ff;border:1px solid rgba(88,166,255,.25);border-radius:20px;padding:3px 12px;font-size:.78rem;'>🌾 {nb_cultures} cultures</span>
    <span style='background:rgba(210,153,34,.12);color:#d29922;border:1px solid rgba(210,153,34,.3);border-radius:20px;padding:3px 12px;font-size:.78rem;'>📦 {prod_total:,.0f} T</span>
    <span style='background:rgba(139,148,158,.1);color:#8b949e;border:1px solid rgba(139,148,158,.2);border-radius:20px;padding:3px 12px;font-size:.78rem;'>📐 {sup_total:,.0f} Ha</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# DONNÉES
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def load_productions() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT p.id, c.libelle AS campagne, c.annee_debut, c.annee_fin,
                   l.nom AS localite, l.geo_id AS localite_id, l.type AS type_geo,
                   p.culture, p.type_culture,
                   p.superficie_ha, p.rendement_kgha, p.production_t, p.niveau
            FROM productions p
            JOIN campagnes c ON p.campagne_id = c.id
            JOIN localites l ON p.localite_id = l.geo_id
            ORDER BY c.annee_debut, l.nom, p.culture
        """, conn)


@st.cache_data(ttl=60)
def load_magasins() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT m.*, l.nom AS localite_nom, l.latitude AS lat, l.longitude AS lon
            FROM magasins m LEFT JOIN localites l ON m.localite_id = l.geo_id
        """, conn)


@st.cache_data(ttl=60)
def load_localites() -> pd.DataFrame:
    """Charge la table localites pour l'analyse hiérarchique."""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT geo_id, nom, type, parent_id FROM localites", conn)


# ══════════════════════════════════════════════════════════════
# PALETTES & LAYOUT
# ══════════════════════════════════════════════════════════════

PALETTE_CULTURES = {
    "MIL":"#3fb950","MAIS":"#58a6ff","RIZ":"#d29922","SORGHO":"#e06c75",
    "FONIO":"#c678dd","ARACHIDE HUILERIE":"#e5c07b","NIEBE":"#56b6c2",
    "MANIOC":"#be5046","COTON":"#abb2bf","PASTEQUE":"#98c379","SESAME":"#61afef",
    "DIAKHATOU":"#f0a500","GOMBO":"#ff7eb3","PIMENT":"#ff4500",
}

PALETTE_TYPES = {
    "cereales":"#3fb950","oleagineux":"#d29922","legumineuses":"#58a6ff",
    "tubercules":"#e06c75","maraîchers":"#c678dd","autres":"#abb2bf",
}

SEQ = ["#3fb950","#58a6ff","#d29922","#e06c75","#c678dd",
       "#e5c07b","#56b6c2","#be5046","#98c379","#61afef","#abb2bf","#f0a500"]

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="IBM Plex Mono, sans-serif", color="#c9d1d9", size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor="#30363d",
                borderwidth=1, font=dict(size=11)),
    xaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
    yaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
)

def lay(fig, title="", height=400):
    fig.update_layout(**PLOTLY_LAYOUT, title=title, title_font_size=13, height=height)
    return fig

def make_pie(labels, values, colors, title, height=360, hole=0.42):
    fig = go.Figure(go.Pie(
        labels=labels, values=values, marker_colors=colors, hole=hole,
        textinfo="label+percent", textfont_size=11,
        hovertemplate="<b>%{label}</b><br>%{value:,.1f}<br>%{percent}<extra></extra>",
    ))
    return lay(fig, title, height)


# ══════════════════════════════════════════════════════════════
# ONGLET 1 — VUE D'ENSEMBLE
# ══════════════════════════════════════════════════════════════

def onglet_vue_ensemble(df, df_mag, df_kol):
    if not PLOTLY_OK:
        st.error("📦 Plotly non installé : `pip install plotly`")
        return

    camp_list = sorted(df_kol["campagne"].unique(), reverse=True)
    if not camp_list:
        st.info("Aucune donnée disponible.")
        return

    campagne_ref = st.selectbox("Campagne de référence", camp_list, key="vue_camp")
    df_last = df_kol[df_kol["campagne"] == campagne_ref]
    avant = camp_list[1] if len(camp_list) > 1 and campagne_ref == camp_list[0] else None
    df_prev = df_kol[df_kol["campagne"] == avant] if avant else pd.DataFrame()

    def delta(a, b):
        if b and b > 0:
            return f"{(a-b)/b*100:+.1f}%"
        return None

    prod = df_last["production_t"].sum()
    sup = df_last["superficie_ha"].sum()
    rdt = prod / sup * 1000 if sup > 0 else 0
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🌾 Production (T)", f"{prod:,.0f}",
              delta=delta(prod, df_prev["production_t"].sum() if not df_prev.empty else 0))
    c2.metric("📐 Superficie (Ha)", f"{sup:,.0f}",
              delta=delta(sup, df_prev["superficie_ha"].sum() if not df_prev.empty else 0))
    c3.metric("📈 Rendement (Kg/Ha)", f"{rdt:,.0f}")
    c4.metric("🏪 Magasins bons", f"{int((df_mag['etat']=='Bon').sum())} / {len(df_mag)}" if not df_mag.empty else "—")
    c5.metric("📦 Capacité (T)", f"{df_mag['capacite_t'].sum():,.0f}" if not df_mag.empty else "—")

    st.divider()

    # Barres cultures + Donut types
    col1, col2 = st.columns([3, 2])
    with col1:
        agg = df_last.groupby("culture")["production_t"].sum().sort_values(ascending=True).reset_index()
        fig = go.Figure(go.Bar(
            x=agg["production_t"], y=agg["culture"], orientation="h",
            marker_color=[PALETTE_CULTURES.get(c, "#abb2bf") for c in agg["culture"]],
            text=agg["production_t"].apply(lambda v: f"{v:,.0f} T"), textposition="outside",
        ))
        lay(fig, f"Production par culture — {campagne_ref}", 420)
        fig.update_xaxes(title="Tonnes")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        agg_t = df_last.groupby("type_culture")["production_t"].sum().reset_index()
        st.plotly_chart(make_pie(
            agg_t["type_culture"], agg_t["production_t"],
            [PALETTE_TYPES.get(t, "#abb2bf") for t in agg_t["type_culture"]],
            "Répartition par type", 420), use_container_width=True)

    # Barres localités empilées + Donut localités
    col3, col4 = st.columns([3, 2])
    with col3:
        agg_lc = df_last.groupby(["localite", "culture"])["production_t"].sum().reset_index()
        fig3 = px.bar(agg_lc, x="localite", y="production_t", color="culture",
                      color_discrete_map=PALETTE_CULTURES, barmode="stack",
                      labels={"production_t": "Production (T)", "localite": "Localité", "culture": "Culture"})
        lay(fig3, f"Par localité et culture — {campagne_ref}", 380)
        st.plotly_chart(fig3, use_container_width=True)
    with col4:
        agg_l2 = df_last.groupby("localite")["production_t"].sum().reset_index()
        st.plotly_chart(make_pie(
            agg_l2["localite"], agg_l2["production_t"],
            SEQ[:len(agg_l2)], "Part de chaque localité", 380),
            use_container_width=True)

    # Double axe sup/prod/rendement
    agg_s = df_last.groupby("localite").agg(
        sup=("superficie_ha", "sum"), prod=("production_t", "sum")).reset_index()
    agg_s["rdt"] = agg_s["prod"] / agg_s["sup"].replace(0, float("nan")) * 1000

    layout = PLOTLY_LAYOUT.copy()
    layout['title'] = f"Superficie / Production / Rendement — {campagne_ref}"
    layout['height'] = 360
    layout['barmode'] = "group"
    base_yaxis = layout.get('yaxis', {})
    layout['yaxis'] = {**base_yaxis, 'title': "Ha / Tonnes", 'gridcolor': "#21262d"}
    layout['yaxis2'] = dict(
        title="Kg/Ha",
        overlaying="y",
        side="right",
        gridcolor="rgba(0,0,0,0)"
    )
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(name="Superficie (Ha)", x=agg_s["localite"], y=agg_s["sup"],
                          marker_color="#58a6ff", offsetgroup=0))
    fig4.add_trace(go.Bar(name="Production (T)",  x=agg_s["localite"], y=agg_s["prod"],
                          marker_color="#3fb950", offsetgroup=1))
    fig4.add_trace(go.Scatter(name="Rendement (Kg/Ha)", x=agg_s["localite"], y=agg_s["rdt"],
                              mode="lines+markers", marker=dict(size=9, color="#d29922"),
                              line=dict(color="#d29922", width=2), yaxis="y2"))
    fig4.update_layout(**layout)
    st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — COMPARAISON CAMPAGNES
# ══════════════════════════════════════════════════════════════

def onglet_comparaison(df, df_kol):
    if not PLOTLY_OK: st.error("📦 Plotly non installé."); return
    camps  = sorted(df_kol["campagne"].unique())
    if len(camps) < 2:
        st.info("Ajoutez au moins 2 campagnes pour la comparaison."); return

    cults = sorted(df_kol["culture"].unique())
    sel   = st.multiselect("Cultures à comparer", cults, default=cults[:6], key="comp_cult")
    dfs   = df_kol[df_kol["culture"].isin(sel)] if sel else df_kol
    cols  = [PALETTE_CULTURES.get(c,"#abb2bf") for c in sel]

    col1, col2 = st.columns([3, 2])
    with col1:
        agg = dfs.groupby(["campagne","culture"])["production_t"].sum().reset_index()
        fig = px.line(agg, x="campagne", y="production_t", color="culture",
                      markers=True, color_discrete_sequence=cols,
                      labels={"production_t":"Production (T)","campagne":"Campagne"})
        lay(fig, "Évolution de la production", 360)
        fig.update_traces(line_width=2, marker_size=8)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        last = camps[-1]
        agg2 = dfs[dfs["campagne"]==last].groupby("culture")["production_t"].sum().reset_index()
        st.plotly_chart(make_pie(
            agg2["culture"], agg2["production_t"],
            [PALETTE_CULTURES.get(c,"#abb2bf") for c in agg2["culture"]],
            f"Part par culture — {last}", 360), use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        agg_s = dfs.groupby(["campagne","culture"])["superficie_ha"].sum().reset_index()
        fig_s = px.bar(agg_s, x="campagne", y="superficie_ha", color="culture",
                       barmode="group", color_discrete_sequence=cols,
                       labels={"superficie_ha":"Superficie (Ha)"})
        lay(fig_s, "Superficie emblavée", 340); st.plotly_chart(fig_s, use_container_width=True)
    with col4:
        agg_r = dfs.groupby(["campagne","culture"])["rendement_kgha"].mean().reset_index()
        fig_r = px.bar(agg_r, x="campagne", y="rendement_kgha", color="culture",
                       barmode="group", color_discrete_sequence=cols,
                       labels={"rendement_kgha":"Rendement moyen (Kg/Ha)"})
        lay(fig_r, "Rendement moyen", 340); st.plotly_chart(fig_r, use_container_width=True)

    st.divider()
    pivot = dfs.groupby(["campagne","culture"]).agg(
        Sup=("superficie_ha","sum"), Prod=("production_t","sum"),
        Rdt=("rendement_kgha","mean")).round(1).reset_index()
    pivot.columns = ["Campagne","Culture","Superficie (Ha)","Production (T)","Rendement (Kg/Ha)"]
    st.dataframe(pivot, hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 3 — PAR CULTURE
# ══════════════════════════════════════════════════════════════

def onglet_par_culture(df, df_kol):
    if not PLOTLY_OK: st.error("📦 Plotly non installé."); return

    c1, c2 = st.columns([2,3])
    cult = c1.selectbox("Culture", sorted(df_kol["culture"].unique()), key="cult_det")
    camp = c2.selectbox("Campagne", sorted(df_kol["campagne"].unique(), reverse=True), key="camp_det")

    df_c  = df_kol[df_kol["culture"]==cult]
    df_cc = df_c[df_c["campagne"]==camp]
    if df_cc.empty:
        st.warning(f"Aucune donnée — {cult} / {camp}"); return

    col1,col2,col3,col4 = st.columns(4)
    col1.metric("Production (T)",    f"{df_cc['production_t'].sum():,.1f}")
    col2.metric("Superficie (Ha)",   f"{df_cc['superficie_ha'].sum():,.1f}")
    col3.metric("Rendement (Kg/Ha)", f"{df_cc['rendement_kgha'].mean():,.1f}")
    col4.metric("Localités",         df_cc["localite"].nunique())
    st.divider()

    color = PALETTE_CULTURES.get(cult, "#3fb950")
    col_a, col_b = st.columns([3, 2])
    with col_a:
        fig = px.bar(df_cc.sort_values("production_t", ascending=True),
                     x="production_t", y="localite", orientation="h",
                     color_discrete_sequence=[color], text="production_t",
                     labels={"production_t":"Production (T)","localite":"Localité"})
        fig.update_traces(texttemplate="%{text:,.0f} T", textposition="outside")
        lay(fig, f"{cult} — Par localité ({camp})", 300)
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        st.plotly_chart(make_pie(
            df_cc["localite"], df_cc["production_t"],
            SEQ[:len(df_cc)], "Part par localité", 300), use_container_width=True)

    agg_c = df_c.groupby("campagne").agg(
        prod=("production_t","sum"), rdt=("rendement_kgha","mean")).reset_index()
    col_c, col_d = st.columns([3, 2])
    with col_c:
        fig2 = make_subplots(specs=[[{"secondary_y":True}]])
        fig2.add_trace(go.Bar(name="Production (T)", x=agg_c["campagne"], y=agg_c["prod"],
                              marker_color=color, opacity=0.85), secondary_y=False)
        fig2.add_trace(go.Scatter(name="Rendement (Kg/Ha)", x=agg_c["campagne"], y=agg_c["rdt"],
                                  mode="lines+markers",
                                  marker=dict(size=8,color="#d29922"),
                                  line=dict(color="#d29922",width=2)), secondary_y=True)
        fig2.update_layout(**PLOTLY_LAYOUT, title=f"{cult} — Toutes campagnes", height=300)
        fig2.update_yaxes(title_text="Production (T)", secondary_y=False, gridcolor="#21262d")
        fig2.update_yaxes(title_text="Rendement (Kg/Ha)", secondary_y=True, gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)
    with col_d:
        total_kol = df_kol[df_kol["campagne"]==camp]["production_t"].sum()
        part_cult = df_cc["production_t"].sum() / total_kol * 100 if total_kol > 0 else 0
        st.plotly_chart(make_pie(
            [cult, "Autres cultures"],
            [df_cc["production_t"].sum(), max(0, total_kol - df_cc["production_t"].sum())],
            [color, "#30363d"],
            f"Part de {cult} dans le total Kolda", 300), use_container_width=True)

    st.divider()
    detail = df_c[["campagne","localite","superficie_ha","rendement_kgha","production_t"]].copy()
    detail.columns = ["Campagne","Localité","Superficie (Ha)","Rendement (Kg/Ha)","Production (T)"]
    st.dataframe(detail.sort_values(["Campagne","Localité"]), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — PAR TYPE DE CULTURE
# ══════════════════════════════════════════════════════════════

def onglet_par_type(df, df_kol):
    if not PLOTLY_OK: st.error("📦 Plotly non installé."); return
    types  = sorted(df_kol["type_culture"].unique())
    camps  = sorted(df_kol["campagne"].unique(), reverse=True)

    c1, c2 = st.columns([2, 3])
    type_sel = c1.selectbox("Type de culture", types, key="type_sel")
    camp_sel = c2.selectbox("Campagne",        camps, key="type_camp")

    df_t  = df_kol[df_kol["type_culture"]==type_sel]
    df_tc = df_t[df_t["campagne"]==camp_sel]
    if df_tc.empty:
        st.warning(f"Aucune donnée — type '{type_sel}' / {camp_sel}"); return

    col1,col2,col3,col4 = st.columns(4)
    col1.metric("Production totale (T)",  f"{df_tc['production_t'].sum():,.0f}")
    col2.metric("Superficie totale (Ha)", f"{df_tc['superficie_ha'].sum():,.0f}")
    col3.metric("Cultures",               df_tc["culture"].nunique())
    col4.metric("Localités",              df_tc["localite"].nunique())
    st.divider()

    color_t = PALETTE_TYPES.get(type_sel, "#3fb950")

    col_a, col_b = st.columns([3, 2])
    with col_a:
        agg_c = df_tc.groupby("culture")["production_t"].sum().sort_values(ascending=True).reset_index()
        fig = go.Figure(go.Bar(
            x=agg_c["production_t"], y=agg_c["culture"], orientation="h",
            marker_color=[PALETTE_CULTURES.get(c,color_t) for c in agg_c["culture"]],
            text=agg_c["production_t"].apply(lambda v: f"{v:,.0f} T"), textposition="outside"))
        lay(fig, f"Cultures {type_sel} — {camp_sel}", 320)
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        st.plotly_chart(make_pie(
            agg_c["culture"], agg_c["production_t"],
            [PALETTE_CULTURES.get(c,color_t) for c in agg_c["culture"]],
            f"Part par culture — {type_sel}", 320), use_container_width=True)

    col_c, col_d = st.columns([3, 2])
    with col_c:
        agg_l = df_tc.groupby(["localite","culture"])["production_t"].sum().reset_index()
        fig_l = px.bar(agg_l, x="localite", y="production_t", color="culture",
                       barmode="stack", color_discrete_map=PALETTE_CULTURES,
                       labels={"production_t":"Production (T)","localite":"Localité"})
        lay(fig_l, f"Par localité — {type_sel} ({camp_sel})", 320)
        st.plotly_chart(fig_l, use_container_width=True)
    with col_d:
        agg_l2 = df_tc.groupby("localite")["production_t"].sum().reset_index()
        st.plotly_chart(make_pie(
            agg_l2["localite"], agg_l2["production_t"],
            SEQ[:len(agg_l2)], "Part par localité", 320), use_container_width=True)

    if len(camps) > 1:
        st.divider()
        agg_ev = df_t.groupby(["campagne","culture"])["production_t"].sum().reset_index()
        col_e, col_f = st.columns([3, 2])
        with col_e:
            fig_ev = px.line(agg_ev, x="campagne", y="production_t", color="culture",
                             markers=True, color_discrete_map=PALETTE_CULTURES,
                             labels={"production_t":"Production (T)","campagne":"Campagne"})
            lay(fig_ev, f"Évolution {type_sel} — toutes campagnes", 320)
            fig_ev.update_traces(line_width=2, marker_size=8)
            st.plotly_chart(fig_ev, use_container_width=True)
        with col_f:
            prev = camps[1] if len(camps) > 1 else camps[0]
            agg_prev = df_t[df_t["campagne"]==prev].groupby("culture")["production_t"].sum().reset_index()
            st.plotly_chart(make_pie(
                agg_prev["culture"], agg_prev["production_t"],
                [PALETTE_CULTURES.get(c,color_t) for c in agg_prev["culture"]],
                f"Part par culture — {prev}", 320), use_container_width=True)

    st.divider()
    detail = df_t[["campagne","localite","culture","superficie_ha","rendement_kgha","production_t"]].copy()
    detail.columns = ["Campagne","Localité","Culture","Superficie (Ha)","Rendement (Kg/Ha)","Production (T)"]
    st.dataframe(detail.sort_values(["Campagne","Culture","Localité"]), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 5 — MAGASINS
# ══════════════════════════════════════════════════════════════

def onglet_magasins(df_mag):
    if not PLOTLY_OK: st.error("📦 Plotly non installé."); return
    if df_mag.empty: st.info("Aucune donnée magasin."); return

    col1,col2,col3,col4 = st.columns(4)
    col1.metric("Total magasins",      len(df_mag))
    col2.metric("Capacité totale (T)", f"{df_mag['capacite_t'].sum():,.0f}")
    col3.metric("Bon état",            int((df_mag["etat"]=="Bon").sum()))
    col4.metric("Mauvais état",        int((df_mag["etat"]=="Mauvais").sum()))
    st.divider()

    colors_etat = {"Bon":"#3fb950","Mauvais":"#f85149","En construction":"#d29922","Inconnu":"#6e7681"}
    cap_dept = df_mag.groupby("departement").agg(
        capacite=("capacite_t","sum"), nb=("id","count")).reset_index()

    col_a, col_b = st.columns(2)
    with col_a:
        ec = df_mag["etat"].value_counts().reset_index(); ec.columns=["etat","count"]
        st.plotly_chart(make_pie(ec["etat"], ec["count"],
            [colors_etat.get(e,"#6e7681") for e in ec["etat"]],
            "Magasins par état", 300), use_container_width=True)
    with col_b:
        fig_cap = px.bar(cap_dept.sort_values("capacite", ascending=True),
                         x="capacite", y="departement", orientation="h",
                         color_discrete_sequence=["#58a6ff"], text="nb",
                         labels={"capacite":"Capacité (T)","departement":"Département"})
        fig_cap.update_traces(texttemplate="%{text} mag.", textposition="outside")
        lay(fig_cap, "Capacité par département (T)", 300)
        st.plotly_chart(fig_cap, use_container_width=True)

    col_c, col_d = st.columns(2)
    with col_c:
        st.plotly_chart(make_pie(
            cap_dept["departement"], cap_dept["capacite"],
            SEQ[:len(cap_dept)], "Part de capacité par département", 300),
            use_container_width=True)
    with col_d:
        etat_cap = df_mag.groupby("etat")["capacite_t"].sum().reset_index()
        st.plotly_chart(make_pie(
            etat_cap["etat"], etat_cap["capacite_t"],
            [colors_etat.get(e,"#6e7681") for e in etat_cap["etat"]],
            "Capacité par état (T)", 300), use_container_width=True)

    st.divider()
    dept_opts = ["Tous"] + sorted(df_mag["departement"].dropna().unique().tolist())
    dept_sel  = st.selectbox("Département", dept_opts, key="mag_dash_dept")
    df_show   = df_mag if dept_sel=="Tous" else df_mag[df_mag["departement"]==dept_sel]
    st.dataframe(
        df_show[["departement","commune","village","capacite_t","etat","contact"]].rename(
            columns={"departement":"Département","commune":"Commune","village":"Village",
                     "capacite_t":"Capacité (T)","etat":"État","contact":"Contact"}),
        hide_index=True, use_container_width=True,
        column_config={"Capacité (T)":st.column_config.NumberColumn(format="%.0f")})


# ══════════════════════════════════════════════════════════════
# ONGLET 6 — DONNÉES NATIONALES
# ══════════════════════════════════════════════════════════════

def onglet_national(df):
    if not PLOTLY_OK: st.error("📦 Plotly non installé."); return
    df_nat = df[df["niveau"]=="region"].copy()
    if df_nat.empty: st.info("Aucune donnée nationale."); return

    c1, c2 = st.columns(2)
    camp = c1.selectbox("Campagne", sorted(df_nat["campagne"].unique(), reverse=True), key="nat_camp")
    cult = c2.selectbox("Culture",  sorted(df_nat[df_nat["campagne"]==camp]["culture"].unique()), key="nat_cult")

    df_n  = df_nat[df_nat["campagne"]==camp]
    df_nc = df_n[df_n["culture"]==cult].sort_values("production_t", ascending=True)
    color = PALETTE_CULTURES.get(cult, "#3fb950")

    col_a, col_b = st.columns([3, 2])
    with col_a:
        fig = px.bar(df_nc, x="production_t", y="localite", orientation="h",
                     color_discrete_sequence=[color], text="production_t",
                     labels={"production_t":"Production (T)","localite":"Région"})
        fig.update_traces(texttemplate="%{text:,.0f} T", textposition="outside")
        lay(fig, f"{cult} — Par région ({camp})", 500)
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        st.plotly_chart(make_pie(
            df_nc["localite"], df_nc["production_t"],
            SEQ[:len(df_nc)], f"Part par région — {cult}", 500),
            use_container_width=True)

    st.divider()
    st.markdown("#### Part de Kolda dans la production nationale")
    agg_k = df_nat[df_nat["localite"].str.upper().str.contains("KOLDA")].groupby(["campagne","culture"])["production_t"].sum()
    agg_t = df_nat.groupby(["campagne","culture"])["production_t"].sum()
    part  = (agg_k / agg_t * 100).dropna().reset_index()
    part.columns = ["Campagne","Culture","Part Kolda (%)"]

    col_c, col_d = st.columns([2, 3])
    with col_c:
        pk = part[part["Campagne"]==camp].sort_values("Part Kolda (%)", ascending=False)
        st.plotly_chart(make_pie(
            pk["Culture"], pk["Part Kolda (%)"],
            [PALETTE_CULTURES.get(c,"#abb2bf") for c in pk["Culture"]],
            f"Part Kolda par culture — {camp}", 360), use_container_width=True)
    with col_d:
        st.dataframe(part.sort_values("Part Kolda (%)", ascending=False),
                     hide_index=True, use_container_width=True,
                     column_config={"Part Kolda (%)":st.column_config.ProgressColumn(
                         min_value=0, max_value=100, format="%.1f%%")})


# ══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(page_title="Dashboard — Kolda Agri", page_icon="📊", layout="wide")

    if not DB_PATH.exists():
        st.error("❌ Base introuvable. Lancez `python db/bootstrap.py` d'abord.")
        return

    theme  = apply_theme()
    df     = load_productions()
    df_mag = load_magasins()
    df_loc = load_localites()

    # ---- Construction de la hiérarchie Kolda ----
    kolda_id = 'R07'
    children_map = {}
    for _, row in df_loc.iterrows():
        parent = row['parent_id']
        if parent is not None:
            children_map.setdefault(parent, []).append(row['geo_id'])

    def get_descendants(root):
        descendants = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node in children_map:
                for child in children_map[node]:
                    if child not in descendants:
                        descendants.add(child)
                        stack.append(child)
        return descendants

    all_kolda_ids = get_descendants(kolda_id)

    # ---- Filtrage des données de la région de Kolda ----
    df_kol = df[df["niveau"].isin(["localite", "departement"])].copy()
    df_kol = df_kol[df_kol["localite_id"].isin(all_kolda_ids)]

    # Utiliser les données filtrées pour les métriques du bandeau
    last = sorted(df_kol["campagne"].unique(), reverse=True)[0] if not df_kol.empty else ""
    df_last = df_kol[df_kol["campagne"] == last] if last else pd.DataFrame()

    render_header(theme,
        nb_campagnes  = df["campagne"].nunique(),
        nb_cultures   = df["culture"].nunique(),
        prod_total    = df_last["production_t"].sum() if not df_last.empty else 0,
        sup_total     = df_last["superficie_ha"].sum() if not df_last.empty else 0)

    tabs = st.tabs([
        "🏠 Vue d'ensemble",
        "📈 Comparaison campagnes",
        "🌱 Par culture",
        "🏷️ Par type",
        "🏪 Magasins",
        "🌍 Données nationales",
    ])

    with tabs[0]: onglet_vue_ensemble(df, df_mag, df_kol)
    with tabs[1]: onglet_comparaison(df, df_kol)
    with tabs[2]: onglet_par_culture(df, df_kol)
    with tabs[3]: onglet_par_type(df, df_kol)
    with tabs[4]: onglet_magasins(df_mag)
    with tabs[5]: onglet_national(df)


if __name__ == "__main__":
    main()