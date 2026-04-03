"""
PAGE 3 — CARTE & GÉOGRAPHIE
Visualisation cartographique : productions, magasins, localités
Dépendances : folium, streamlit-folium, streamlit
"""

import sys
import json
import io
from pathlib import Path
import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))

from utils import get_connection, get_config, DB_PATH

try:
    import folium
    from folium.plugins import MarkerCluster, HeatMap, Fullscreen, MiniMap
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False


# ══════════════════════════════════════════════════════════════
# THEME & CONFIG
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
    primary       = cfg("color_primary",      "#3fb950")
    font          = cfg("font_family",         "IBM Plex Mono, sans-serif").split(",")[0].strip()
    hdr_bg        = cfg("header_bg_color",     "#1c2a1e")
    hdr_border    = cfg("header_border_color", "#3fb950")
    hdr_text      = cfg("header_text_color",   "#e6edf3")
    tab_active    = cfg("tab_active_color",    "#3fb950")
    subtab_active = cfg("subtab_active_color", "#58a6ff")
    body_bg       = cfg("body_bg_color",       "#0d1117")   # Nouveau

    def _hex_rgba(h, a=0.07):
        h = h.lstrip("#")
        if len(h) == 6:
            r,g,b = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
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
    .stButton > button[kind="primary"] {{
        background-color: {primary} !important;
        border-color: {primary} !important;
    }}
    [data-baseweb="tab-list"] {{ gap: 0 !important; width: 100% !important; }}
    [data-baseweb="tab"] {{
        flex: 1 1 0 !important; justify-content: center !important;
        padding: 10px 4px !important; font-size: 0.85rem !important;
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


def render_header(theme, nb_localites, nb_magasins):
    st.markdown(f"""
<div style='background:{theme["hdr_bg"]};border:1px solid rgba(255,255,255,0.06);
            border-left:4px solid {theme["hdr_border"]};
            border-radius:0 0 12px 12px;padding:18px 32px 16px;margin:-1px 0 20px 0;'>
  <div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>
    <span style='font-size:1.45rem;line-height:1;'>🗺️</span>
    <h1 style='margin:0;font-size:1.45rem;font-weight:700;color:{theme["hdr_text"]};letter-spacing:-.01em;'>
      Carte &amp; Géographie
    </h1>
  </div>
  <p style='margin:0 0 12px;color:#8b949e;font-size:.83rem;text-align:center;'>
    Région de Kolda — Visualisation cartographique
  </p>
  <div style='display:flex;justify-content:center;gap:8px;flex-wrap:wrap;'>
    <span style='background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3);border-radius:20px;padding:3px 12px;font-size:.78rem;'>
      📍 {nb_localites} localités géolocalisées
    </span>
    <span style='background:rgba(88,166,255,.1);color:#58a6ff;border:1px solid rgba(88,166,255,.25);border-radius:20px;padding:3px 12px;font-size:.78rem;'>
      🏪 {nb_magasins} magasins
    </span>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# DONNÉES
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def load_localites() -> pd.DataFrame:
    """Charge la table localites pour l'analyse hiérarchique."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT geo_id, nom, type, parent_id, latitude, longitude FROM localites", conn
        )


@st.cache_data(ttl=60)
def load_geo() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT l.geo_id, l.nom, l.type, l.parent_id,
                   l.latitude, l.longitude, l.abreviation,
                   p.nom AS parent_nom
            FROM localites l
            LEFT JOIN localites p ON l.parent_id = p.geo_id
            WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
            ORDER BY l.type, l.nom
        """, conn)


@st.cache_data(ttl=60)
def load_magasins_geo() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT m.id, m.departement, m.commune, m.village,
                   m.capacite_t, m.etat, m.contact,
                   COALESCE(m.latitude,  l.latitude)  AS lat,
                   COALESCE(m.longitude, l.longitude) AS lon,
                   l.nom AS localite_nom,
                   l.geo_id AS localite_id
            FROM magasins m
            LEFT JOIN localites l ON m.localite_id = l.geo_id
        """, conn)


@st.cache_data(ttl=60)
def load_productions_geo() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT p.culture, p.type_culture,
                   p.superficie_ha, p.rendement_kgha, p.production_t,
                   c.libelle AS campagne, c.annee_debut,
                   l.nom AS localite, l.geo_id AS localite_id,
                   l.latitude, l.longitude
            FROM productions p
            JOIN campagnes c ON p.campagne_id = c.id
            JOIN localites l ON p.localite_id = l.geo_id
            WHERE p.niveau = 'localite'
              AND l.latitude IS NOT NULL
            ORDER BY c.annee_debut DESC, l.nom, p.culture
        """, conn)


@st.cache_data(ttl=60)
def load_national_data() -> pd.DataFrame:
    """Charge les données au niveau région pour la comparaison régionale."""
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT p.culture, p.type_culture,
                   p.superficie_ha, p.rendement_kgha, p.production_t,
                   c.libelle AS campagne, c.annee_debut,
                   l.nom AS region, l.geo_id AS region_id,
                   l.latitude, l.longitude
            FROM productions p
            JOIN campagnes c ON p.campagne_id = c.id
            JOIN localites l ON p.localite_id = l.geo_id
            WHERE p.niveau = 'region'
              AND l.latitude IS NOT NULL
            ORDER BY c.annee_debut DESC, l.nom, p.culture
        """, conn)


# ══════════════════════════════════════════════════════════════
# FILTRAGE HIÉRARCHIQUE KOLDA
# ══════════════════════════════════════════════════════════════

def get_kolda_ids(df_loc: pd.DataFrame) -> set:
    """Retourne l'ensemble des geo_id descendants de la région Kolda (R07)."""
    kolda_id = 'R07'
    children_map = {}
    for _, row in df_loc.iterrows():
        parent = row['parent_id']
        if parent is not None:
            children_map.setdefault(parent, []).append(row['geo_id'])
    descendants = set()
    stack = [kolda_id]
    while stack:
        node = stack.pop()
        if node in children_map:
            for child in children_map[node]:
                if child not in descendants:
                    descendants.add(child)
                    stack.append(child)
    return descendants


# ══════════════════════════════════════════════════════════════
# CARTE DE BASE
# ══════════════════════════════════════════════════════════════

def base_map(zoom: int = None, style: str = None) -> folium.Map:
    """Crée une carte centrée sur Kolda."""
    zoom_start  = int(cfg("carte_zoom_defaut",  "9"))   if zoom  is None else zoom
    lat_center  = float(cfg("carte_lat_defaut",  "12.9033"))
    lon_center  = float(cfg("carte_lon_defaut",  "-14.946"))
    map_style   = cfg("carte_style", "CartoDB dark_matter") if style is None else style

    tiles_map = {
        "OpenStreetMap":       "OpenStreetMap",
        "CartoDB positron":    "CartoDB positron",
        "CartoDB dark_matter": "CartoDB dark_matter",
        "Stamen Terrain":      "Stamen Terrain",
    }

    m = folium.Map(
        location    = [lat_center, lon_center],
        zoom_start  = zoom_start,
        tiles       = tiles_map.get(map_style, "CartoDB dark_matter"),
        prefer_canvas = True,
    )
    Fullscreen(position="topright").add_to(m)
    MiniMap(position="bottomright", toggle_display=True).add_to(m)
    return m


# ══════════════════════════════════════════════════════════════
# COULEURS
# ══════════════════════════════════════════════════════════════

COULEURS_ETAT = {
    "Bon":            "#3fb950",
    "Mauvais":        "#f85149",
    "En construction":"#d29922",
    "Inconnu":        "#6e7681",
}

COULEURS_TYPE = {
    "region":       "#e06c75",
    "departement":  "#d29922",
    "commune":      "#58a6ff",
    "village":      "#3fb950",
}

COULEURS_CULTURES = {
    "MIL":               "#3fb950",
    "MAIS":              "#58a6ff",
    "RIZ":               "#d29922",
    "SORGHO":            "#e06c75",
    "FONIO":             "#c678dd",
    "ARACHIDE HUILERIE": "#e5c07b",
    "NIEBE":             "#56b6c2",
    "MANIOC":            "#be5046",
    "COTON":             "#abb2bf",
    "PASTEQUE":          "#98c379",
    "SESAME":            "#61afef",
}

def _circle_marker(lat, lon, color, radius, tooltip, popup_html=None):
    """Cercle coloré avec tooltip et popup optionnel."""
    m = folium.CircleMarker(
        location=[lat, lon],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.75,
        weight=1.5,
        tooltip=folium.Tooltip(tooltip, sticky=True),
    )
    if popup_html:
        m.add_child(folium.Popup(popup_html, max_width=280))
    return m


def _house_icon(color: str, size: int) -> folium.DivIcon:
    """
    Crée une icône maison SVG colorée dont la taille est proportionnelle
    à la capacité du magasin.
    """
    s = max(18, min(size, 52))
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='{s}' height='{s}' viewBox='0 0 24 24'>
      <polygon points='12,3 22,11 19,11 19,21 5,21 5,11 2,11'
               fill='{color}' stroke='#ffffff' stroke-width='1.2' opacity='0.9'/>
      <rect x='9' y='14' width='6' height='7' fill='rgba(0,0,0,0.35)'/>
    </svg>"""
    return folium.DivIcon(
        html=f"<div style='margin-left:-{s//2}px;margin-top:-{s//2}px;'>{svg}</div>",
        icon_size=(s, s),
        icon_anchor=(s // 2, s // 2),
    )


def _add_legend_to_map(m: folium.Map, legend_html: str):
    """Injecte un bloc HTML de légende en bas à gauche de la carte Folium."""
    m.get_root().html.add_child(folium.Element(legend_html))


# ══════════════════════════════════════════════════════════════
# ONGLET 1 — STOCKAGE (KOLDA uniquement)
# Icônes maison : couleur = état, taille ∝ capacité
# Cluster de marqueurs pour zoom progressif
# ══════════════════════════════════════════════════════════════

def onglet_stockage(df_geo: pd.DataFrame, df_mag: pd.DataFrame, kolda_ids: set):
    """Carte centrée sur Kolda, focalisée sur les magasins avec filtres."""
    df_geo_kol = df_geo[df_geo["geo_id"].isin(kolda_ids)].copy()
    df_mag_kol = df_mag[
        df_mag["localite_id"].isin(kolda_ids) |
        df_mag["departement"].str.contains("KOLDA", case=False, na=False)
    ].copy()

    if df_mag_kol.empty:
        st.warning("Aucun magasin géolocalisé dans la région de Kolda.")
        return

    # ── Filtres ──────────────────────────────────────────────
    col1, col2 = st.columns(2)
    dept_opts = ["Tous"] + sorted(df_mag_kol["departement"].dropna().unique().tolist())
    etat_opts = ["Tous"] + sorted(df_mag_kol["etat"].dropna().unique().tolist())
    dept_sel  = col1.selectbox("Département", dept_opts, key="stock_dept")
    etat_sel  = col2.selectbox("État des magasins", etat_opts, key="stock_etat")

    dff = df_mag_kol.copy()
    if dept_sel != "Tous":
        dff = dff[dff["departement"] == dept_sel]
    if etat_sel != "Tous":
        dff = dff[dff["etat"] == etat_sel]

    # ── KPIs ─────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Magasins affichés", len(dff))
    col2.metric("Capacité totale (T)", f"{dff['capacite_t'].sum():,.0f}")
    col3.metric("Capacité moyenne (T)", f"{dff['capacite_t'].mean():,.0f}")
    st.divider()

    # ── Carte ────────────────────────────────────────────────
    m = base_map()
    max_cap = dff["capacite_t"].max()
    max_cap = max_cap if pd.notna(max_cap) and max_cap > 0 else 1

    # Cluster qui se décluster au zoom → on voit les détails
    cluster = MarkerCluster(
        name="🏠 Magasins",
        options={
            "showCoverageOnHover": True,
            "zoomToBoundsOnClick": True,
            "maxClusterRadius": 50,
        }
    )

    for _, row in dff.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            continue
        color  = COULEURS_ETAT.get(row["etat"], "#6e7681")
        # Taille icône : 18px (petite cap) → 48px (grande cap)
        cap = row["capacite_t"] if pd.notna(row["capacite_t"]) else 0
        icon_size = int(18 + (cap / max_cap) * 30)
        popup_html = f"""
        <div style='font-family:monospace;font-size:12px;min-width:200px;'>
            <b>🏠 {row['village']}</b><br>
            Commune    : {row['commune']}<br>
            Département: {row['departement']}<br>
            Capacité   : <b>{row['capacite_t']:.0f} T</b><br>
            État       : <span style='color:{color};font-weight:bold;'>{row['etat']}</span><br>
            Contact    : {row['contact'] or '—'}
        </div>"""
        marker = folium.Marker(
            location=[row["lat"], row["lon"]],
            icon=_house_icon(color, icon_size),
            tooltip=folium.Tooltip(
                f"🏠 {row['village']} — {row['capacite_t']:.0f} T ({row['etat']})",
                sticky=True
            ),
            popup=folium.Popup(popup_html, max_width=280),
        )
        marker.add_to(cluster)
    cluster.add_to(m)

    # Couche localités (fond contextuel, masquée par défaut)
    loc_layer = folium.FeatureGroup(name="📍 Localités", show=False)
    for _, row in df_geo_kol.iterrows():
        radius = 3 if row["type"] == "village" else 5 if row["type"] == "commune" else 8
        color  = COULEURS_TYPE.get(row["type"], "#ffffff")
        _circle_marker(
            row["latitude"], row["longitude"], color, radius,
            f"{row['nom']} ({row['type']})",
            f"<b>{row['nom']}</b><br>Type : {row['type']}"
        ).add_to(loc_layer)
    loc_layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Légende dynamique avec valeurs réelles
    max_cap_val = int(dff["capacite_t"].max()) if pd.notna(dff["capacite_t"].max()) else 0
    mid_cap_val = int(max_cap_val / 2)

    legend_html = f"""
    <div style='position:fixed;bottom:30px;left:30px;z-index:9999;
                background:rgba(13,17,23,0.88);border:1px solid rgba(255,255,255,0.15);
                border-radius:10px;padding:14px 18px;font-family:monospace;font-size:12px;
                color:#e6edf3;min-width:210px;'>
      <b style='font-size:13px;'>🏠 Légende — Magasins</b>
      <hr style='border-color:rgba(255,255,255,0.1);margin:7px 0;'/>
      <div style='font-weight:600;color:#8b949e;margin-bottom:6px;'>Couleur = État du magasin</div>
      <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
        <span style='display:inline-block;width:14px;height:14px;background:#3fb950;border-radius:3px;'></span>Bon
      </div>
      <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
        <span style='display:inline-block;width:14px;height:14px;background:#f85149;border-radius:3px;'></span>Mauvais
      </div>
      <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
        <span style='display:inline-block;width:14px;height:14px;background:#d29922;border-radius:3px;'></span>En construction
      </div>
      <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
        <span style='display:inline-block;width:14px;height:14px;background:#6e7681;border-radius:3px;'></span>Inconnu
      </div>
      <hr style='border-color:rgba(255,255,255,0.1);margin:7px 0;'/>
      <div style='font-weight:600;color:#8b949e;margin-bottom:6px;'>Taille de l'icône = Capacité (T)</div>
      <div style='position:relative;height:10px;border-radius:5px;
                  background:linear-gradient(to right,rgba(255,255,255,0.15),rgba(255,255,255,0.80));
                  margin-bottom:4px;'></div>
      <div style='display:flex;justify-content:space-between;font-size:10px;color:#8b949e;'>
        <span>0 T</span>
        <span>{mid_cap_val:,} T</span>
        <span>{max_cap_val:,} T</span>
      </div>
    </div>
    """
    _add_legend_to_map(m, legend_html)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    # Tableau des magasins
    st.divider()
    st.subheader("Liste des magasins")
    st.dataframe(
        dff[["departement","commune","village","capacite_t","etat","contact"]].rename(
            columns={"departement":"Département","commune":"Commune",
                     "village":"Village","capacite_t":"Capacité (T)","etat":"État","contact":"Contact"}),
        hide_index=True, use_container_width=True,
        column_config={"Capacité (T)": st.column_config.NumberColumn(format="%.0f")}
    )


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — PRODUCTION (KOLDA uniquement)
# Légende : couleur = superficie, taille = production
# ══════════════════════════════════════════════════════════════

def onglet_production(df_prod: pd.DataFrame, kolda_ids: set):
    """Carte de production : bulles taille=prod, couleur=sup."""
    df_prod_kol = df_prod[df_prod["localite_id"].isin(kolda_ids)].copy()
    if df_prod_kol.empty:
        st.warning("Aucune donnée de production pour Kolda.")
        return

    # Filtres
    campagnes      = sorted(df_prod_kol["campagne"].unique(), reverse=True)
    cultures       = sorted(df_prod_kol["culture"].unique())
    type_cultures  = sorted(df_prod_kol["type_culture"].dropna().unique())

    col1, col2, col3 = st.columns(3)
    camp_sel = col1.selectbox("Campagne", campagnes, key="prod_camp")
    cult_sel = col2.selectbox("Culture", ["Toutes"] + cultures, key="prod_cult")
    type_sel = col3.selectbox("Type de culture", ["Tous"] + type_cultures, key="prod_type")

    dff = df_prod_kol[df_prod_kol["campagne"] == camp_sel].copy()
    if cult_sel != "Toutes":
        dff = dff[dff["culture"] == cult_sel]
    if type_sel != "Tous":
        dff = dff[dff["type_culture"] == type_sel]

    # Agrégation par localité
    agg = (dff.groupby(["localite","latitude","longitude"])
             .agg(prod=("production_t","sum"),
                  sup=("superficie_ha","sum"),
                  rdt=("rendement_kgha","mean"))
             .reset_index())

    if agg.empty:
        st.warning("Aucune donnée pour cette sélection.")
        return

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Production totale (T)",    f"{agg['prod'].sum():,.0f}")
    col2.metric("Superficie totale (Ha)",   f"{agg['sup'].sum():,.0f}")
    col3.metric("Rendement moyen (Kg/Ha)",  f"{agg['rdt'].mean():,.0f}")
    col4.metric("Localités concernées",     len(agg))
    st.divider()

    # Carte
    m = base_map()
    max_prod = agg["prod"].max() if agg["prod"].max() > 0 else 1
    max_sup  = agg["sup"].max()  if agg["sup"].max()  > 0 else 1

    # Seuils superficie pour couleurs
    def _color_sup(sup_norm):
        if sup_norm > 0.8:  return "#f85149", "Très grande (> 80 %)"
        if sup_norm > 0.5:  return "#d29922", "Grande (50–80 %)"
        if sup_norm > 0.2:  return "#58a6ff", "Moyenne (20–50 %)"
        return "#3fb950",                      "Petite (< 20 %)"

    for _, row in agg.iterrows():
        radius   = 6 + (row["prod"] / max_prod) ** 0.5 * 44
        sup_norm = row["sup"] / max_sup
        color, _ = _color_sup(sup_norm)
        popup = f"""
        <div style='font-family:monospace;font-size:12px;min-width:180px;'>
            <b>{row['localite']}</b><br>
            Production : <b>{row['prod']:,.1f} T</b><br>
            Superficie : {row['sup']:,.1f} Ha<br>
            Rendement  : {row['rdt']:,.0f} Kg/Ha
        </div>"""
        _circle_marker(row["latitude"], row["longitude"],
                       color, radius,
                       f"📍 {row['localite']} — {row['prod']:,.0f} T",
                       popup).add_to(m)

    # Légende dynamique avec valeurs réelles
    max_sup_val  = int(agg["sup"].max())
    mid_sup_val  = int(max_sup_val / 2)
    qtr_sup_val  = int(max_sup_val / 4)
    tqtr_sup_val = int(max_sup_val * 3 / 4)
    max_prod_val = int(agg["prod"].max())

    legend_html = f"""
    <div style='position:fixed;bottom:30px;left:30px;z-index:9999;
                background:rgba(13,17,23,0.88);border:1px solid rgba(255,255,255,0.15);
                border-radius:10px;padding:14px 18px;font-family:monospace;font-size:12px;
                color:#e6edf3;min-width:230px;'>
      <b style='font-size:13px;'>🌾 Légende — Production</b>
      <hr style='border-color:rgba(255,255,255,0.1);margin:7px 0;'/>

      <div style='font-weight:600;color:#8b949e;margin-bottom:6px;'>Couleur du cercle = Superficie (Ha)</div>
      <div style='position:relative;height:14px;border-radius:7px;
                  background:linear-gradient(to right,#3fb950,#58a6ff,#d29922,#f85149);
                  margin-bottom:4px;'></div>
      <div style='display:flex;justify-content:space-between;font-size:10px;color:#8b949e;margin-bottom:2px;'>
        <span>0</span>
        <span>{qtr_sup_val:,}</span>
        <span>{mid_sup_val:,}</span>
        <span>{tqtr_sup_val:,}</span>
        <span>{max_sup_val:,}</span>
      </div>
      <div style='font-size:10px;color:#6e7681;margin-bottom:8px;'>Ha</div>

      <hr style='border-color:rgba(255,255,255,0.1);margin:7px 0;'/>
      <div style='font-weight:600;color:#8b949e;margin-bottom:4px;'>Taille du cercle = Production (T)</div>
      <div style='font-size:11px;color:#adb5bd;'>
        Proportionnelle à la production — max {max_prod_val:,} T
      </div>
    </div>
    """
    _add_legend_to_map(m, legend_html)
    st_folium(m, height=520, use_container_width=True, returned_objects=[])

    # Tableau récapitulatif
    st.divider()
    st.subheader("Données détaillées")
    df_show = agg[["localite","prod","sup","rdt"]].copy()
    df_show.columns = ["Localité","Production (T)","Superficie (Ha)","Rendement (Kg/Ha)"]
    st.dataframe(
        df_show.sort_values("Production (T)", ascending=False),
        hide_index=True, use_container_width=True,
        column_config={
            "Production (T)":    st.column_config.NumberColumn(format="%.1f"),
            "Superficie (Ha)":   st.column_config.NumberColumn(format="%.1f"),
            "Rendement (Kg/Ha)": st.column_config.NumberColumn(format="%.0f"),
        }
    )


# ══════════════════════════════════════════════════════════════
# ONGLET 3 — COMPARAISON RÉGIONALE
# Légende + bulles proportionnelles
# ══════════════════════════════════════════════════════════════

def onglet_comparaison_regionale(df_nat: pd.DataFrame):
    """Affiche une carte choroplèthe et des graphiques comparatifs entre régions."""

    if df_nat.empty:
        st.warning("Aucune donnée nationale (niveau région) disponible.")
        return

    campagnes = sorted(df_nat["campagne"].unique(), reverse=True)
    camp_sel  = st.selectbox("Campagne", campagnes, key="cr_camp")

    df_camp = df_nat[df_nat["campagne"] == camp_sel].copy()
    if df_camp.empty:
        st.warning("Aucune donnée pour cette campagne.")
        return

    # Agrégation par région
    agg_reg = (df_camp.groupby(["region","region_id","latitude","longitude"])
                     .agg(prod=("production_t","sum"),
                          sup=("superficie_ha","sum"),
                          rdt=("rendement_kgha","mean"))
                     .reset_index())
    agg_reg = agg_reg.dropna(subset=["latitude","longitude"])

    if agg_reg.empty:
        st.warning("Aucune région géolocalisée.")
        return

    # KPIs nationaux
    col1, col2, col3 = st.columns(3)
    col1.metric("Production nationale (T)",       f"{agg_reg['prod'].sum():,.0f}")
    col2.metric("Superficie nationale (Ha)",      f"{agg_reg['sup'].sum():,.0f}")
    col3.metric("Rendement national moyen (Kg/Ha)", f"{agg_reg['rdt'].mean():,.0f}")
    st.divider()

    # Carte (bulles proportionnelles)
    m = base_map(zoom=6)
    max_prod = agg_reg["prod"].max() if agg_reg["prod"].max() > 0 else 1

    for _, row in agg_reg.iterrows():
        radius = 10 + (row["prod"] / max_prod) ** 0.5 * 40
        is_kolda = row["region"].upper() == "KOLDA"
        color    = "#d29922" if is_kolda else "#3fb950"
        popup = f"""
        <div style='font-family:monospace;font-size:12px;'>
            <b>{row['region']}</b>{'&nbsp;⭐' if is_kolda else ''}<br>
            Production : {row['prod']:,.0f} T<br>
            Superficie : {row['sup']:,.0f} Ha<br>
            Rendement  : {row['rdt']:.0f} Kg/Ha
        </div>"""
        _circle_marker(
            row["latitude"], row["longitude"],
            color, radius,
            f"{row['region']} — {row['prod']:,.0f} T",
            popup
        ).add_to(m)

    # Légende intégrée dans la carte
    legend_html = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:9999;
                background:rgba(13,17,23,0.88);border:1px solid rgba(255,255,255,0.15);
                border-radius:10px;padding:12px 16px;font-family:monospace;font-size:12px;
                color:#e6edf3;min-width:210px;'>
      <b style='font-size:13px;'>📊 Légende — Régions</b>
      <hr style='border-color:rgba(255,255,255,0.1);margin:6px 0;'/>
      <div style='font-weight:600;color:#8b949e;margin-bottom:4px;'>Couleur</div>
      <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
        <span style='display:inline-block;width:14px;height:14px;background:#d29922;border-radius:50%;'></span>Région de Kolda ⭐
      </div>
      <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
        <span style='display:inline-block;width:14px;height:14px;background:#3fb950;border-radius:50%;'></span>Autres régions
      </div>
      <hr style='border-color:rgba(255,255,255,0.1);margin:6px 0;'/>
      <div style='font-weight:600;color:#8b949e;margin-bottom:4px;'>Taille du cercle</div>
      <div style='font-size:11px;color:#adb5bd;'>Proportionnelle à la production totale (T)</div>
    </div>
    """
    _add_legend_to_map(m, legend_html)
    st_folium(m, height=500, use_container_width=True, returned_objects=[])

    # Graphique à barres
    st.divider()
    st.subheader("Comparaison des productions par région")
    try:
        import plotly.express as px
        fig = px.bar(
            agg_reg.sort_values("prod", ascending=False),
            x="region", y="prod", color="region",
            labels={"region": "Région", "prod": "Production (T)"},
            title=f"Production par région – {camp_sel}",
            color_discrete_map={r: "#d29922" if r.upper() == "KOLDA" else "#3fb950"
                                 for r in agg_reg["region"]},
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.warning("Plotly non installé, impossible d'afficher le graphique.")

    # Tableau détaillé
    st.divider()
    st.subheader("Données détaillées")
    df_show = agg_reg[["region","prod","sup","rdt"]].copy()
    df_show.columns = ["Région","Production (T)","Superficie (Ha)","Rendement (Kg/Ha)"]
    st.dataframe(
        df_show.sort_values("Production (T)", ascending=False),
        hide_index=True, use_container_width=True,
        column_config={
            "Production (T)":    st.column_config.NumberColumn(format="%.0f"),
            "Superficie (Ha)":   st.column_config.NumberColumn(format="%.0f"),
            "Rendement (Kg/Ha)": st.column_config.NumberColumn(format="%.0f"),
        }
    )


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — DIVISIONS ADMINISTRATIVES
# Polygones GeoJSON, compteurs géocodé/non-géocodé, export
# ══════════════════════════════════════════════════════════════

def _render_geocoding_stats(df_all: pd.DataFrame, df_geo: pd.DataFrame):
    """Affiche les compteurs et le bouton d'export des zones non-géocodées."""
    nb_total    = len(df_all)
    nb_geocoded = len(df_geo)
    nb_missing  = nb_total - nb_geocoded
    pct         = round(nb_geocoded / nb_total * 100) if nb_total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total zones", nb_total)
    col2.metric("✅ Géocodées", nb_geocoded,
                delta=f"{pct} %", delta_color="normal")
    col3.metric("❌ Non-géocodées", nb_missing,
                delta=f"{100-pct} %", delta_color="inverse")
    col4.metric("Taux de couverture", f"{pct} %")

    # Zones non-géocodées
    df_missing = df_all[~df_all["geo_id"].isin(df_geo["geo_id"])].copy()
    if df_missing.empty:
        st.success("🎉 Toutes les zones sont géocodées !")
        return

    with st.expander(f"📋 Voir les {nb_missing} zones non-géocodées", expanded=False):
        cols_show = [c for c in ["geo_id","nom","type","parent_id"] if c in df_missing.columns]
        df_view = df_missing[cols_show].copy()
        df_view.columns = [c.replace("_"," ").capitalize() for c in cols_show]
        st.dataframe(df_view, hide_index=True, use_container_width=True)

    # Boutons export
    st.markdown("**Exporter les zones non-géocodées :**")
    ecol1, ecol2 = st.columns(2)

    # Export CSV
    csv_data = df_missing[cols_show].to_csv(index=False).encode("utf-8")
    ecol1.download_button(
        label="⬇️ Télécharger CSV",
        data=csv_data,
        file_name="zones_non_geocodees.csv",
        mime="text/csv",
        key="dl_csv_admin",
    )

    # Export Excel
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_missing[cols_show].to_excel(writer, index=False, sheet_name="Non-géocodées")
        excel_data = output.getvalue()
        ecol2.download_button(
            label="⬇️ Télécharger Excel",
            data=excel_data,
            file_name="zones_non_geocodees.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_xlsx_admin",
        )
    except ImportError:
        ecol2.warning("openpyxl non installé — export Excel indisponible.")


def onglet_divisions_administratives(df_all: pd.DataFrame, df_geo: pd.DataFrame,
                                     kolda_ids: set):
    """
    Carte des divisions administratives.
    - Polygones GeoJSON si disponible (data/senegal.geojson ou data/kolda.geojson)
    - Sinon : marqueurs type-colorés (sans cercles superflus)
    - Compteurs géocodé/non-géocodé + export
    """
    # ── Filtres ──────────────────────────────────────────────
    type_opts  = ["Tous"] + sorted(df_geo["type"].dropna().unique().tolist())
    scope_opts = ["Kolda uniquement", "Toute la base"]
    col1, col2 = st.columns(2)
    type_sel  = col1.selectbox("Type de zone", type_opts, key="adm_type")
    scope_sel = col2.selectbox("Périmètre", scope_opts, key="adm_scope")

    dff = df_geo.copy()
    if scope_sel == "Kolda uniquement":
        dff = dff[dff["geo_id"].isin(kolda_ids)]
    if type_sel != "Tous":
        dff = dff[dff["type"] == type_sel]

    # Correspondance df_all pour stats (même filtre scope)
    df_all_filt = df_all.copy()
    if scope_sel == "Kolda uniquement":
        df_all_filt = df_all_filt[df_all_filt["geo_id"].isin(kolda_ids)]
    if type_sel != "Tous":
        df_all_filt = df_all_filt[df_all_filt["type"] == type_sel]

    # ── Stats géocodage ──────────────────────────────────────
    _render_geocoding_stats(df_all_filt, dff)
    st.divider()

    if dff.empty:
        st.warning("Aucune donnée géolocalisée pour cette sélection.")
        return

    # ── Carte ────────────────────────────────────────────────
    m = base_map()

    # Chercher fichier(s) GeoJSON
    geojson_candidates = [
        ROOT / "data" / "kolda.geojson",
        ROOT / "data" / "senegal.geojson",
        ROOT / "data" / "senegal_regions.geojson",
        ROOT / "data" / "senegal_departements.geojson",
        ROOT / "data" / "kolda_communes.geojson",
    ]
    geojson_loaded = False
    for gj_path in geojson_candidates:
        if gj_path.exists():
            try:
                with open(gj_path, encoding="utf-8") as f:
                    gj_data = json.load(f)
                folium.GeoJson(
                    gj_data,
                    name=f"🗺️ Polygones ({gj_path.stem})",
                    style_function=lambda feat: {
                        "fillColor":   "#58a6ff",
                        "color":       "#e6edf3",
                        "weight":      1.5,
                        "fillOpacity": 0.08,
                        "dashArray":   "4 3",
                    },
                    highlight_function=lambda feat: {
                        "fillColor":   "#3fb950",
                        "color":       "#3fb950",
                        "weight":      2.5,
                        "fillOpacity": 0.20,
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=["nom"] if "nom" in (
                            gj_data["features"][0]["properties"] if gj_data.get("features") else {}
                        ) else [],
                        aliases=["Zone :"],
                        sticky=True,
                    ) if gj_data.get("features") else None,
                ).add_to(m)
                geojson_loaded = True
            except Exception:
                pass  # fichier invalide, on continue

    if not geojson_loaded:
        st.info(
            "💡 Aucun fichier GeoJSON trouvé dans `data/`. "
            "Pour afficher les délimitations polygonales, ajoutez par exemple "
            "`kolda.geojson` ou `senegal.geojson` dans ce dossier."
        )

    # Marqueurs par type (icônes colorées, sans cercle)
    # On regroupe par type pour avoir des couches séparées
    type_groups = {}
    for t in dff["type"].dropna().unique():
        fg = folium.FeatureGroup(name=f"{'🟥' if t=='region' else '🟧' if t=='departement' else '🔵' if t=='commune' else '🟢'} {t.capitalize()}s", show=True)
        type_groups[t] = fg

    for _, row in dff.iterrows():
        t      = row["type"]
        color  = COULEURS_TYPE.get(t, "#ffffff")
        parent = row.get("parent_nom") or row.get("parent_id") or "—"
        # Icône pin colorée (pas de cercle)
        icon = folium.Icon(color="white", icon_color=color, icon="map-marker", prefix="fa")
        popup_html = f"""
        <div style='font-family:monospace;font-size:12px;min-width:160px;'>
            <b>{row['nom']}</b><br>
            Type   : {t}<br>
            Parent : {parent}
        </div>"""
        marker = folium.Marker(
            location=[row["latitude"], row["longitude"]],
            icon=icon,
            tooltip=folium.Tooltip(f"{row['nom']} ({t})", sticky=True),
            popup=folium.Popup(popup_html, max_width=220),
        )
        if t in type_groups:
            marker.add_to(type_groups[t])

    for fg in type_groups.values():
        fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Légende
    legend_items = ""
    for t, color in COULEURS_TYPE.items():
        label = t.capitalize() + "s"
        legend_items += f"""
        <div style='display:flex;align-items:center;gap:7px;margin:3px 0;'>
          <span style='display:inline-block;width:14px;height:14px;background:{color};border-radius:3px;'></span>{label}
        </div>"""

    legend_html = f"""
    <div style='position:fixed;bottom:30px;left:30px;z-index:9999;
                background:rgba(13,17,23,0.88);border:1px solid rgba(255,255,255,0.15);
                border-radius:10px;padding:12px 16px;font-family:monospace;font-size:12px;
                color:#e6edf3;min-width:185px;'>
      <b style='font-size:13px;'>🗺️ Légende — Zones</b>
      <hr style='border-color:rgba(255,255,255,0.1);margin:6px 0;'/>
      {legend_items}
      {'<hr style="border-color:rgba(255,255,255,0.1);margin:6px 0;"/><div style="font-size:11px;color:#adb5bd;">Contours polygonaux si GeoJSON disponible</div>' if geojson_loaded else ''}
    </div>
    """
    _add_legend_to_map(m, legend_html)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    # Tableau
    st.divider()
    st.subheader(f"Zones affichées ({len(dff)})")
    cols_show = [c for c in ["nom","type","parent_nom","latitude","longitude"] if c in dff.columns]
    st.dataframe(
        dff[cols_show].rename(columns={
            "nom":"Nom","type":"Type","parent_nom":"Parent",
            "latitude":"Latitude","longitude":"Longitude"
        }),
        hide_index=True, use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Carte — Kolda Agri",
        page_icon="🗺️",
        layout="wide",
    )

    if not DB_PATH.exists():
        st.error("❌ Base introuvable. Lancez `python db/bootstrap.py` d'abord.")
        return

    if not FOLIUM_OK:
        st.error("📦 Folium non installé. Lancez :")
        st.code("pip install folium streamlit-folium")
        return

    theme    = apply_theme()
    df_loc   = load_localites()          # contient latitude/longitude aussi
    df_geo   = load_geo()
    df_mag   = load_magasins_geo()
    df_prod  = load_productions_geo()
    df_nat   = load_national_data()

    kolda_ids = get_kolda_ids(df_loc)

    df_geo_kol = df_geo[df_geo["geo_id"].isin(kolda_ids)]
    df_mag_kol = df_mag[df_mag["localite_id"].isin(kolda_ids) |
                        df_mag["departement"].str.contains("KOLDA", case=False, na=False)]

    render_header(theme, len(df_geo_kol), len(df_mag_kol))

    tabs = st.tabs([
        "🏠 Stockage",
        "🌾 Production",
        "📊 Comparaison régionale",
        "🗺️ Divisions administratives",
    ])

    with tabs[0]: onglet_stockage(df_geo, df_mag, kolda_ids)
    with tabs[1]: onglet_production(df_prod, kolda_ids)
    with tabs[2]: onglet_comparaison_regionale(df_nat)
    with tabs[3]: onglet_divisions_administratives(df_loc, df_geo, kolda_ids)


if __name__ == "__main__":
    main()