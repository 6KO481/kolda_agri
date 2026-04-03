"""
PAGE 4 — MÉTÉO
Données météorologiques via l'API Open-Meteo (gratuite, sans clé).
Fonctionnalités :
  - Météo actuelle + prévisions 7 jours
  - Historique personnalisable (jusqu'à 2 ans avec découpage automatique)
  - Indicateurs agro-météo (ETP, stress hydrique, jours de pluie)
  - Comparaison des 3 départements de Kolda
  - Calendrier agricole / alertes
"""

import sys
import json
import urllib.request
import urllib.parse
from datetime import date, timedelta, datetime
from pathlib import Path

import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))

from utils import get_connection, get_config, DB_PATH

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False


# ══════════════════════════════════════════════════════════════
# THEME
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
    body_bg       = cfg("body_bg_color",       "#0d1117")   # Nouvelle couleur de fond générale

    def _hex_rgba(h, a=0.07):
        h = h.lstrip("#")
        if len(h) == 6:
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
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
    .stButton > button[kind="primary"] {{ background-color: {primary} !important; border-color: {primary} !important; }}
    
    /* Fond général de l'application */
    .stApp {{
        background-color: {body_bg} !important;
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


def render_header(theme, localite_nom):
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f"""
<div style='background:{theme["hdr_bg"]};border:1px solid rgba(255,255,255,0.06);
            border-left:4px solid {theme["hdr_border"]};
            border-radius:0 0 12px 12px;padding:18px 32px 16px;margin:-1px 0 20px 0;'>
  <div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>
    <span style='font-size:1.45rem;line-height:1;'>☁️</span>
    <h1 style='margin:0;font-size:1.45rem;font-weight:700;color:{theme["hdr_text"]};letter-spacing:-.01em;'>
      Météo — {localite_nom}
    </h1>
  </div>
  <p style='margin:0 0 12px;color:#8b949e;font-size:.83rem;text-align:center;'>
    Données Open-Meteo (gratuit, sans clé API) &nbsp;·&nbsp;
    Mis à jour : {now_str}
  </p>
  <div style='display:flex;justify-content:center;gap:8px;flex-wrap:wrap;'>
    <span style='background:rgba(88,166,255,.1);color:#58a6ff;border:1px solid rgba(88,166,255,.25);border-radius:20px;padding:3px 12px;font-size:.78rem;'>
      🌍 Open-Meteo API
    </span>
    <span style='background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3);border-radius:20px;padding:3px 12px;font-size:.78rem;'>
      Fuseau : Africa/Dakar
    </span>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# LOCALITÉS DISPONIBLES
# ══════════════════════════════════════════════════════════════

LIEUX_KOLDA = {
    "Région de Kolda":    (12.9033,  -14.9460),
    "Kolda (dept)":       (12.8921,  -14.9401),
    "Médina Yoro Foulah": (13.2928,  -14.7147),
    "Vélingara":          (13.1472,  -14.1076),
}

# Codes WMO → description + emoji
WMO_CODES = {
    0:  ("Ciel dégagé",                "☀️"),
    1:  ("Principalement dégagé",      "🌤️"),
    2:  ("Partiellement nuageux",      "⛅"),
    3:  ("Couvert",                    "☁️"),
    45: ("Brouillard",                 "🌫️"),
    48: ("Brouillard givrant",         "🌫️"),
    51: ("Bruine légère",              "🌦️"),
    53: ("Bruine modérée",             "🌦️"),
    55: ("Bruine dense",               "🌧️"),
    61: ("Pluie légère",               "🌧️"),
    63: ("Pluie modérée",              "🌧️"),
    65: ("Pluie forte",                "🌧️"),
    71: ("Neige légère",               "🌨️"),
    73: ("Neige modérée",              "🌨️"),
    75: ("Neige forte",                "❄️"),
    80: ("Averses légères",            "🌦️"),
    81: ("Averses modérées",           "🌧️"),
    82: ("Averses violentes",          "⛈️"),
    95: ("Orage",                      "⛈️"),
    96: ("Orage avec grêle",           "⛈️"),
    99: ("Orage violent avec grêle",   "⛈️"),
}

def wmo_label(code):
    if code is None:
        return ("Inconnu", "❓")
    return WMO_CODES.get(int(code), (f"Code {code}", "🌡️"))


# ══════════════════════════════════════════════════════════════
# APPELS API OPEN-METEO
# ══════════════════════════════════════════════════════════════

OPENMETEO_BASE = "https://api.open-meteo.com/v1"
ARCHIVE_BASE   = "https://archive-api.open-meteo.com/v1/archive"

def _get(url: str) -> dict:
    """Requête HTTP simple avec gestion d'erreur."""
    req = urllib.request.Request(url, headers={"User-Agent": "KoldaAgriDashboard/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_current_and_forecast(lat: float, lon: float) -> dict:
    """Météo actuelle + prévisions 7 jours + indicateurs agricoles."""
    params = {
        "latitude":  lat,
        "longitude": lon,
        "timezone":  "Africa/Dakar",
        "forecast_days": 7,
        "current": ",".join([
            "temperature_2m", "apparent_temperature",
            "relative_humidity_2m", "precipitation",
            "wind_speed_10m", "wind_direction_10m",
            "weather_code", "surface_pressure",
            "cloud_cover", "is_day",
        ]),
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "precipitation_probability_max",
            "wind_speed_10m_max", "weather_code",
            "et0_fao_evapotranspiration",
            "sunshine_duration",
            "uv_index_max",
        ]),
        "hourly": ",".join([
            "temperature_2m", "precipitation_probability",
            "precipitation", "relative_humidity_2m", "wind_speed_10m",
        ]),
    }
    url = f"{OPENMETEO_BASE}/forecast?" + urllib.parse.urlencode(params)
    return _get(url)


def _fetch_historical_single(lat: float, lon: float, start_date: date, end_date: date) -> dict:
    """Appel unique à l'API archive (max 365 jours)."""
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "timezone":   "Africa/Dakar",
        "start_date": start_date.isoformat(),
        "end_date":   end_date.isoformat(),
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
            "precipitation_sum",
            "et0_fao_evapotranspiration",
            "wind_speed_10m_max",
            "sunshine_duration",
            "weather_code",
        ]),
    }
    url = f"{ARCHIVE_BASE}?" + urllib.parse.urlencode(params)
    return _get(url)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_historical_range(lat: float, lon: float, start_date: date, end_date: date) -> dict:
    """
    Récupère l'historique sur une période pouvant dépasser 365 jours
    en découpant automatiquement en tranches.
    """
    delta = (end_date - start_date).days
    if delta <= 365:
        return _fetch_historical_single(lat, lon, start_date, end_date)

    # Découpage
    all_daily = {
        "time": [], "temperature_2m_max": [], "temperature_2m_min": [],
        "temperature_2m_mean": [], "precipitation_sum": [],
        "et0_fao_evapotranspiration": [], "wind_speed_10m_max": [],
        "sunshine_duration": [], "weather_code": []
    }
    current_start = start_date
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=364), end_date)
        part = _fetch_historical_single(lat, lon, current_start, current_end)
        if "daily" in part:
            for k in all_daily.keys():
                all_daily[k].extend(part["daily"].get(k, []))
        current_start = current_end + timedelta(days=1)
    return {"daily": all_daily}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_multi_locations(lieux: dict) -> dict[str, dict]:
    """Météo actuelle pour plusieurs localités."""
    results = {}
    for nom, (lat, lon) in lieux.items():
        try:
            results[nom] = fetch_current_and_forecast(lat, lon)
        except Exception as e:
            results[nom] = {"error": str(e)}
    return results


# ══════════════════════════════════════════════════════════════
# HELPERS GRAPHES
# ══════════════════════════════════════════════════════════════

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="IBM Plex Mono, sans-serif", color="#c9d1d9", size=12),
    margin=dict(l=10, r=10, t=36, b=10),
    legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor="#30363d",
                borderwidth=1, font=dict(size=11)),
)

def lay(fig, title="", height=320, **kwargs):
    layout = {**PLOTLY_LAYOUT, "title": title, "height": height}
    layout.update(kwargs)
    fig.update_layout(**layout)
    return fig


# ══════════════════════════════════════════════════════════════
# CARTE MÉTÉO ACTUELLE (widget HTML)
# ══════════════════════════════════════════════════════════════

def _card_meteo(label, value, unit, icon, color="#3fb950", sub=""):
    return f"""
    <div style='background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
                border-left:3px solid {color};border-radius:10px;
                padding:12px 16px;text-align:center;'>
      <div style='font-size:1.6rem;margin-bottom:4px;'>{icon}</div>
      <div style='font-size:.75rem;color:#8b949e;text-transform:uppercase;
                  letter-spacing:.06em;margin-bottom:4px;'>{label}</div>
      <div style='font-size:1.6rem;font-weight:700;color:{color};line-height:1;'>
        {value}<span style='font-size:.85rem;font-weight:400;color:#8b949e;'> {unit}</span>
      </div>
      {f"<div style='font-size:.75rem;color:#8b949e;margin-top:4px;'>{sub}</div>" if sub else ""}
    </div>"""


# ══════════════════════════════════════════════════════════════
# ONGLET 1 — MÉTÉO ACTUELLE
# ══════════════════════════════════════════════════════════════

def onglet_actuelle(data: dict):
    if "error" in data:
        st.error(f"❌ Erreur API : {data['error']}")
        return

    cur   = data.get("current", {})
    daily = data.get("daily",   {})

    code  = cur.get("weather_code")
    desc, emoji = wmo_label(code)
    is_day = cur.get("is_day", 1)

    st.markdown(f"""
    <div style='text-align:center;padding:20px 0 10px;'>
      <div style='font-size:4rem;'>{emoji}</div>
      <div style='font-size:2.2rem;font-weight:700;color:#e6edf3;margin:4px 0;'>
        {cur.get("temperature_2m", "--")} °C
      </div>
      <div style='color:#8b949e;font-size:1rem;'>{desc}</div>
      <div style='font-size:.8rem;color:#6e7681;margin-top:4px;'>
        {"☀️ Jour" if is_day else "🌙 Nuit"}
      </div>
    </div>
    """, unsafe_allow_html=True)

    cards = [
        ("Ressenti",   f"{cur.get('apparent_temperature','--')}",    "°C",   "🌡️",  "#58a6ff"),
        ("Humidité",   f"{cur.get('relative_humidity_2m','--')}",    "%",    "💧",  "#56b6c2"),
        ("Pluie",      f"{cur.get('precipitation','--')}",           "mm",   "🌧️",  "#3fb950"),
        ("Vent",       f"{cur.get('wind_speed_10m','--')}",          "km/h", "💨",  "#d29922",
         f"Direction {cur.get('wind_direction_10m','--')}°"),
        ("Pression",   f"{cur.get('surface_pressure','--')}",        "hPa",  "📊",  "#c678dd"),
        ("Nuages",     f"{cur.get('cloud_cover','--')}",             "%",    "☁️",  "#abb2bf"),
    ]
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards):
        col.markdown(_card_meteo(*c[:5], sub=c[5] if len(c)>5 else ""),
                     unsafe_allow_html=True)

    st.divider()
    st.markdown("#### 📅 Prévisions 7 jours")
    if not daily or not daily.get("time"):
        st.info("Données de prévision non disponibles.")
        return

    n = len(daily["time"])
    cols7 = st.columns(min(n, 7))
    for i, col in enumerate(cols7):
        if i >= n:
            break
        d_str   = daily["time"][i]
        d_obj   = date.fromisoformat(d_str)
        jour    = d_obj.strftime("%a %d")
        t_max   = daily["temperature_2m_max"][i]
        t_min   = daily["temperature_2m_min"][i]
        pluie   = daily["precipitation_sum"][i] or 0
        prob    = daily.get("precipitation_probability_max", [None]*n)[i]
        wcode   = daily["weather_code"][i]
        _, em   = wmo_label(wcode)
        etp     = daily.get("et0_fao_evapotranspiration", [None]*n)[i]
        sun_s   = daily.get("sunshine_duration", [None]*n)[i]
        sun_h   = round(sun_s / 3600, 1) if sun_s else "--"

        prob_str = f"{prob}%" if prob is not None else "--"
        etp_str  = f"{etp:.1f}" if etp is not None else "--"

        col.markdown(f"""
        <div style='background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:10px 8px;text-align:center;'>
          <div style='font-size:.75rem;color:#8b949e;margin-bottom:4px;'>{jour}</div>
          <div style='font-size:1.6rem;'>{em}</div>
          <div style='font-size:.95rem;font-weight:600;color:#e06c75;'>{t_max}°</div>
          <div style='font-size:.85rem;color:#8b949e;'>{t_min}°</div>
          <div style='font-size:.72rem;color:#56b6c2;margin-top:4px;'>💧 {pluie} mm</div>
          <div style='font-size:.72rem;color:#58a6ff;'>🌧 {prob_str}</div>
          <div style='font-size:.7rem;color:#d29922;margin-top:2px;'>ETP {etp_str} mm</div>
          <div style='font-size:.7rem;color:#e5c07b;'>☀ {sun_h} h</div>
        </div>
        """, unsafe_allow_html=True)

    if not PLOTLY_OK:
        return
    st.divider()
    df_d = pd.DataFrame({
        "Jour":    daily["time"],
        "Max °C":  daily["temperature_2m_max"],
        "Min °C":  daily["temperature_2m_min"],
        "Pluie mm":daily["precipitation_sum"],
    })
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_d["Jour"], y=df_d["Max °C"],
                             name="Max °C", line=dict(color="#e06c75", width=2),
                             mode="lines+markers"))
    fig.add_trace(go.Scatter(x=df_d["Jour"], y=df_d["Min °C"],
                             name="Min °C", line=dict(color="#58a6ff", width=2),
                             mode="lines+markers",
                             fill="tonexty", fillcolor="rgba(88,166,255,0.08)"))
    fig.add_trace(go.Bar(x=df_d["Jour"], y=df_d["Pluie mm"],
                         name="Pluie (mm)", marker_color="#3fb950",
                         opacity=0.5, yaxis="y2"))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title="Températures et précipitations — 7 jours",
        height=320,
        yaxis=dict(title="°C", gridcolor="#21262d"),
        yaxis2=dict(title="mm", overlaying="y", side="right",
                    gridcolor="rgba(0,0,0,0)")
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — HISTORIQUE & BILAN MENSUEL (avec intervalle personnalisé)
# ══════════════════════════════════════════════════════════════

def onglet_historique(lat: float, lon: float):
    st.markdown("#### 📅 Période d'analyse")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Date de début",
            value=date.today() - timedelta(days=30),
            max_value=date.today() - timedelta(days=1),
            key="hist_start"
        )
    with col2:
        end_date = st.date_input(
            "Date de fin",
            value=date.today() - timedelta(days=1),
            max_value=date.today() - timedelta(days=1),
            key="hist_end"
        )
    if start_date > end_date:
        st.error("La date de début doit être antérieure à la date de fin.")
        return

    try:
        with st.spinner(f"Chargement de l'historique du {start_date} au {end_date}..."):
            data = fetch_historical_range(lat, lon, start_date, end_date)
    except Exception as e:
        st.error(f"❌ Erreur API historique : {e}")
        return

    daily = data.get("daily", {})
    if not daily or not daily.get("time"):
        st.info("Aucune donnée historique pour cette période.")
        return

    df = pd.DataFrame({
        "date":     pd.to_datetime(daily["time"]),
        "t_max":    daily.get("temperature_2m_max", []),
        "t_min":    daily.get("temperature_2m_min", []),
        "t_mean":   daily.get("temperature_2m_mean", []),
        "pluie":    daily.get("precipitation_sum", []),
        "etp":      daily.get("et0_fao_evapotranspiration", []),
        "vent_max": daily.get("wind_speed_10m_max", []),
        "soleil_h": [s/3600 if s else 0 for s in daily.get("sunshine_duration", [])],
        "wcode":    daily.get("weather_code", []),
    })

    # Bilan KPIs
    pluie_tot   = df["pluie"].sum()
    etp_tot     = df["etp"].sum()
    bilan_hydro = pluie_tot - etp_tot
    jours_pluie = int((df["pluie"] > 1).sum())
    t_moy       = df["t_mean"].mean()
    soleil_moy  = df["soleil_h"].mean()

    col1,col2,col3,col4,col5 = st.columns(5)
    col1.metric("💧 Précip. totales", f"{pluie_tot:.1f} mm")
    col2.metric("🌱 ETP totale",       f"{etp_tot:.1f} mm",
                help="Évapotranspiration potentielle Penman-Monteith")
    col3.metric("⚖️ Bilan hydrique",  f"{bilan_hydro:+.1f} mm",
                delta=("Excédent" if bilan_hydro >= 0 else "Déficit"),
                delta_color="normal" if bilan_hydro >= 0 else "inverse")
    col4.metric("🌧️ Jours de pluie", f"{jours_pluie} j",
                help="Jours avec pluie > 1 mm")
    col5.metric("☀️ Ensoleillement moy.", f"{soleil_moy:.1f} h/j")

    st.divider()

    if not PLOTLY_OK:
        st.dataframe(df, hide_index=True, use_container_width=True)
        return

    # Graphiques
    col_a, col_b = st.columns(2)
    with col_a:
        fig_p = go.Figure()
        fig_p.add_trace(go.Bar(x=df["date"], y=df["pluie"],
                               name="Pluie (mm)", marker_color="#3fb950", opacity=0.8))
        fig_p.add_trace(go.Scatter(x=df["date"], y=df["etp"],
                                   name="ETP (mm)", line=dict(color="#d29922", width=2),
                                   mode="lines"))
        lay(fig_p, "Précipitations vs ETP (mm/jour)", 300)
        st.plotly_chart(fig_p, use_container_width=True)

    with col_b:
        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(x=df["date"], y=df["t_max"],
                                   name="T max", line=dict(color="#e06c75", width=2)))
        fig_t.add_trace(go.Scatter(x=df["date"], y=df["t_min"],
                                   name="T min", line=dict(color="#58a6ff", width=2),
                                   fill="tonexty", fillcolor="rgba(88,166,255,0.06)"))
        fig_t.add_trace(go.Scatter(x=df["date"], y=df["t_mean"],
                                   name="T moy", line=dict(color="#d29922", width=1.5,
                                   dash="dot")))
        lay(fig_t, "Températures (°C)", 300)
        st.plotly_chart(fig_t, use_container_width=True)

    col_c, col_d = st.columns(2)
    with col_c:
        df["bilan_cum"] = (df["pluie"] - df["etp"]).cumsum()
        fig_b = go.Figure()
        fig_b.add_trace(go.Scatter(
            x=df["date"], y=df["bilan_cum"],
            name="Bilan hydrique cumulé (mm)",
            fill="tozeroy",
            line=dict(color="#56b6c2", width=2),
            fillcolor="rgba(86,182,194,0.15)",
        ))
        fig_b.add_hline(y=0, line_color="#6e7681", line_dash="dash")
        lay(fig_b, "Bilan hydrique cumulé (mm)", 280)
        st.plotly_chart(fig_b, use_container_width=True)

    with col_d:
        fig_s = go.Figure(go.Bar(
            x=df["date"], y=df["soleil_h"],
            name="Ensoleillement (h/j)",
            marker_color="#e5c07b", opacity=0.8))
        lay(fig_s, "Ensoleillement quotidien (h/j)", 280)
        st.plotly_chart(fig_s, use_container_width=True)

    # Tableau détaillé
    st.divider()
    with st.expander("📋 Données journalières complètes"):
        df_show = df.copy()
        df_show["date"] = df_show["date"].dt.strftime("%d/%m/%Y")
        rename_map = {
            "date": "Date", "t_max": "T max °C", "t_min": "T min °C",
            "t_mean": "T moy °C", "pluie": "Pluie mm", "etp": "ETP mm",
            "vent_max": "Vent max km/h", "soleil_h": "Soleil h",
            "wcode": "Code météo"
        }
        df_show = df_show.rename(columns=rename_map)
        if "bilan_cum" in df_show.columns:
            df_show = df_show.drop(columns=["bilan_cum"])
        st.dataframe(df_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 3 — INDICATEURS AGRO-MÉTÉO
# ══════════════════════════════════════════════════════════════

def onglet_agro(data: dict, lat: float, lon: float):
    if "error" in data:
        st.error(f"❌ {data['error']}")
        return

    daily = data.get("daily", {})
    if not daily or not daily.get("time"):
        st.info("Données non disponibles.")
        return

    df_7j = pd.DataFrame({
        "jour":    daily["time"],
        "t_max":   daily.get("temperature_2m_max", []),
        "t_min":   daily.get("temperature_2m_min", []),
        "pluie":   daily.get("precipitation_sum", []),
        "prob":    daily.get("precipitation_probability_max", []),
        "etp":     daily.get("et0_fao_evapotranspiration", []),
        "uv":      daily.get("uv_index_max", []),
        "sun_h":   [s/3600 if s else 0 for s in daily.get("sunshine_duration", [])],
    })

    pluie_7j  = df_7j["pluie"].sum()
    etp_7j    = df_7j["etp"].sum()
    bilan_7j  = pluie_7j - etp_7j
    t_max_max = df_7j["t_max"].max()

    st.markdown("#### 🚨 Alertes agro-météo")
    alertes = []
    if bilan_7j < -30:
        alertes.append(("🔴 Déficit hydrique sévère",
                         f"Bilan hydrique 7j : {bilan_7j:.1f} mm — risque de stress pour les cultures."))
    elif bilan_7j < -10:
        alertes.append(("🟡 Déficit hydrique modéré",
                         f"Bilan hydrique 7j : {bilan_7j:.1f} mm — surveiller l'irrigation."))
    if t_max_max > 38:
        alertes.append(("🔴 Chaleur extrême",
                         f"T max prévue : {t_max_max}°C — risque de brûlures foliaires."))
    elif t_max_max > 34:
        alertes.append(("🟡 Fortes chaleurs",
                         f"T max prévue : {t_max_max}°C — stress thermique possible."))
    if pluie_7j > 80:
        alertes.append(("🟡 Excès pluviométrique",
                         f"Précip. 7j : {pluie_7j:.1f} mm — risque d'engorgement des sols."))
    uv_max = df_7j["uv"].max() if "uv" in df_7j.columns else 0
    if uv_max and uv_max > 10:
        alertes.append(("🟡 Indice UV très élevé",
                         f"UV max : {uv_max:.0f} — protection des travailleurs agricoles recommandée."))

    if not alertes:
        st.success("✅ Aucune alerte agro-météo pour les 7 prochains jours.")
    for titre, detail in alertes:
        niveau = "error" if "🔴" in titre else "warning"
        getattr(st, niveau)(f"**{titre}** — {detail}")

    st.divider()
    st.markdown("#### 🌱 Indicateurs agricoles — 7 prochains jours")
    col1,col2,col3,col4 = st.columns(4)
    col1.metric("💧 Précipitations", f"{pluie_7j:.1f} mm")
    col2.metric("🌱 ETP cumulée",    f"{etp_7j:.1f} mm",
                help="Évapotranspiration potentielle — eau nécessaire aux cultures")
    bilan_delta = f"{'Excédent' if bilan_7j>=0 else 'Déficit'}"
    col3.metric("⚖️ Bilan hydrique", f"{bilan_7j:+.1f} mm",
                delta=bilan_delta, delta_color="normal" if bilan_7j>=0 else "inverse")
    col4.metric("🌡️ T max prévue",   f"{t_max_max:.1f} °C")

    if not PLOTLY_OK:
        return

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_7j["jour"], y=df_7j["pluie"],
                             name="Pluie (mm)", marker_color="#3fb950", opacity=0.8))
        fig.add_trace(go.Scatter(x=df_7j["jour"], y=df_7j["etp"],
                                 name="ETP (mm)", line=dict(color="#d29922", width=2.5),
                                 mode="lines+markers"))
        lay(fig, "Pluie vs ETP — 7 jours (mm)", 300)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        colors_bilan = ["#3fb950" if v >= 0 else "#f85149"
                        for v in (df_7j["pluie"] - df_7j["etp"])]
        fig2 = go.Figure(go.Bar(
            x=df_7j["jour"],
            y=df_7j["pluie"] - df_7j["etp"],
            name="Bilan (mm/j)",
            marker_color=colors_bilan,
        ))
        fig2.add_hline(y=0, line_color="#6e7681", line_dash="dash")
        lay(fig2, "Bilan hydrique journalier (mm)", 300)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("#### 🌾 Calendrier cultural — Contexte Kolda")
    mois_actuel = date.today().month

    CALENDRIER = {
        "Mil / Sorgho":          {"semis": [6,7], "croissance": [7,8,9], "recolte": [10,11]},
        "Maïs":                  {"semis": [6,7], "croissance": [7,8,9], "recolte": [10,11]},
        "Riz":                   {"semis": [7,8], "croissance": [8,9,10],"recolte": [11,12]},
        "Arachide":              {"semis": [6,7], "croissance": [7,8,9], "recolte": [9,10]},
        "Niébé":                 {"semis": [7],   "croissance": [8,9],   "recolte": [9,10]},
    }

    PHASES = {
        "semis":     ("🌱", "#3fb950"),
        "croissance":("🌿", "#58a6ff"),
        "recolte":   ("🌾", "#d29922"),
    }

    rows = []
    for culture, phases in CALENDRIER.items():
        phase_actuelle = None
        for phase, mois_list in phases.items():
            if mois_actuel in mois_list:
                em, col = PHASES[phase]
                phase_actuelle = f"{em} {phase.capitalize()}"
                break
        rows.append({
            "Culture":        culture,
            "Phase actuelle": phase_actuelle or "Hors saison",
            "Semis":          "Juin–Juil" if 6 in phases.get("semis",[]) else "Juil–Août",
            "Récolte":        "Oct–Nov" if 10 in phases.get("recolte",[]) else "Nov–Déc",
        })

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — COMPARAISON DES 3 DÉPARTEMENTS
# ══════════════════════════════════════════════════════════════

def onglet_comparaison():
    st.info("💡 Comparaison météo simultanée des 3 départements de Kolda.")
    try:
        with st.spinner("Chargement des données pour les 3 localités…"):
            all_data = fetch_multi_locations(LIEUX_KOLDA)
    except Exception as e:
        st.error(f"❌ Erreur : {e}")
        return

    if not PLOTLY_OK:
        st.warning("Plotly requis pour les graphes.")
        return

    rows = []
    for nom, data in all_data.items():
        if "error" in data:
            rows.append({"Localité": nom, "Erreur": data["error"]})
            continue
        cur   = data.get("current", {})
        daily = data.get("daily",   {})
        pluie_7j = sum(x or 0 for x in daily.get("precipitation_sum", []))
        etp_7j   = sum(x or 0 for x in daily.get("et0_fao_evapotranspiration", []))
        _, em = wmo_label(cur.get("weather_code"))
        rows.append({
            "Localité":        nom,
            "Météo":           em,
            "T actuelle °C":   cur.get("temperature_2m"),
            "Humidité %":      cur.get("relative_humidity_2m"),
            "Vent km/h":       cur.get("wind_speed_10m"),
            "Pluie 7j mm":     round(pluie_7j, 1),
            "ETP 7j mm":       round(etp_7j, 1),
            "Bilan 7j mm":     round(pluie_7j - etp_7j, 1),
        })

    df_cmp = pd.DataFrame([r for r in rows if "Erreur" not in r])

    if df_cmp.empty:
        st.error("Données non disponibles pour toutes les localités.")
        return

    st.markdown("#### 📊 Comparatif météo actuel")
    st.dataframe(df_cmp, hide_index=True, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        fig_t = px.bar(df_cmp, x="Localité", y="T actuelle °C",
                       color="Localité", color_discrete_sequence=["#e06c75","#d29922","#3fb950","#58a6ff"],
                       text="T actuelle °C")
        fig_t.update_traces(texttemplate="%{text}°C", textposition="outside")
        lay(fig_t, "Température actuelle (°C)", 320)
        st.plotly_chart(fig_t, use_container_width=True)

    with col2:
        fig_p = go.Figure()
        fig_p.add_trace(go.Bar(name="Pluie 7j (mm)", x=df_cmp["Localité"],
                               y=df_cmp["Pluie 7j mm"], marker_color="#3fb950", opacity=0.8))
        fig_p.add_trace(go.Bar(name="ETP 7j (mm)", x=df_cmp["Localité"],
                               y=df_cmp["ETP 7j mm"], marker_color="#d29922", opacity=0.8))
        fig_p.update_layout(**PLOTLY_LAYOUT, barmode="group",
                             title="Bilan hydrique 7j — comparaison", height=320)
        st.plotly_chart(fig_p, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        colors_b = ["#3fb950" if v >= 0 else "#f85149" for v in df_cmp["Bilan 7j mm"]]
        fig_b = go.Figure(go.Bar(x=df_cmp["Localité"], y=df_cmp["Bilan 7j mm"],
                                 marker_color=colors_b, text=df_cmp["Bilan 7j mm"],
                                 texttemplate="%{text:+.1f} mm", textposition="outside"))
        fig_b.add_hline(y=0, line_dash="dash", line_color="#6e7681")
        lay(fig_b, "Bilan hydrique 7j (mm)", 300)
        st.plotly_chart(fig_b, use_container_width=True)

    with col4:
        fig_h = px.bar(df_cmp, x="Localité", y="Humidité %",
                       color="Localité",
                       color_discrete_sequence=["#e06c75","#d29922","#3fb950","#58a6ff"],
                       text="Humidité %")
        fig_h.update_traces(texttemplate="%{text}%", textposition="outside")
        lay(fig_h, "Humidité relative actuelle (%)", 300)
        st.plotly_chart(fig_h, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Météo — Kolda Agri",
        page_icon="☁️",
        layout="wide",
    )

    if not DB_PATH.exists():
        st.error("❌ Base introuvable. Lancez `python db/bootstrap.py` d'abord.")
        return

    theme = apply_theme()

    # Sélecteur de localité + bouton rafraîchir alignés
    col_left, col_right = st.columns([10, 1], vertical_alignment="center")
    with col_left:
        lieu_sel = st.selectbox(
            "📍 Choisir une zone",
            list(LIEUX_KOLDA.keys()),
            key="meteo_lieu_page"
        )
    with col_right:
        # Le bouton rafraîchir a été retiré ou commenté selon vos souhaits
        pass

    lat, lon = LIEUX_KOLDA[lieu_sel]
    render_header(theme, lieu_sel)

    try:
        with st.spinner("⏳ Chargement des données météo…"):
            data = fetch_current_and_forecast(lat, lon)
        api_ok = "error" not in data
    except Exception as e:
        data = {"error": str(e)}
        api_ok = False

    if not api_ok:
        st.error(f"❌ Impossible de contacter l'API Open-Meteo : {data.get('error', '?')}")
        st.info("Vérifiez votre connexion Internet. L'API Open-Meteo est gratuite et ne nécessite pas de clé.")
        return

    tabs = st.tabs([
        "🌤️ Météo actuelle",
        "📅 Historique",
        "🌱 Indicateurs agro",
        "🗺️ Comparaison depts",
    ])

    with tabs[0]: onglet_actuelle(data)
    with tabs[1]: onglet_historique(lat, lon)
    with tabs[2]: onglet_agro(data, lat, lon)
    with tabs[3]: onglet_comparaison()


if __name__ == "__main__":
    main()