"""
PAGE 6 — CHATBOT IA
Agent conversationnel avec accès aux données agricoles de Kolda.
Architecture : HuggingFace Inference API (Mistral-7B) + tools Python natifs.

Tools disponibles :
  - sql_tool      : exécute une requête SQL sur la base et retourne les résultats
  - summary_tool  : statistiques descriptives sur les productions
  - chart_tool    : génère un graphe Plotly depuis les données
  - meteo_tool    : récupère la météo actuelle de Kolda
"""

import sys
import re
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

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

    def _hex_rgba(h, a=0.07):
        h = h.lstrip("#")
        if len(h) == 6:
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"
        return f"rgba(63,185,80,{a})"

    tab_bg = _hex_rgba(tab_active) if tab_active.startswith("#") else "rgba(63,185,80,0.07)"

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: '{font}', sans-serif !important; }}
    .main .block-container {{ padding-top: 0 !important; margin-top: 0 !important; }}
    header[data-testid="stHeader"] {{ height: 0 !important; }}
    .stButton > button[kind="primary"] {{
        background-color: {primary} !important; border-color: {primary} !important;
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
    /* Bulles de chat */
    .chat-user {{
        background: rgba(63,185,80,0.12);
        border: 1px solid rgba(63,185,80,0.25);
        border-radius: 12px 12px 2px 12px;
        padding: 10px 16px; margin: 8px 0 8px 60px;
        font-size: .9rem; color: #e6edf3;
    }}
    .chat-bot {{
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px 12px 12px 2px;
        padding: 10px 16px; margin: 8px 60px 8px 0;
        font-size: .9rem; color: #e6edf3;
    }}
    .chat-tool {{
        background: rgba(88,166,255,0.08);
        border-left: 3px solid #58a6ff;
        border-radius: 0 6px 6px 0;
        padding: 6px 12px; margin: 4px 0;
        font-size: .8rem; color: #8b949e; font-family: monospace;
    }}
    </style>
    """, unsafe_allow_html=True)
    return {"primary": primary, "hdr_bg": hdr_bg,
            "hdr_border": hdr_border, "hdr_text": hdr_text}


def render_header(theme):
    model = cfg("hf_model_id", "Mistral-7B").split("/")[-1]
    st.markdown(f"""
<div style='background:{theme["hdr_bg"]};border:1px solid rgba(255,255,255,0.06);
            border-left:4px solid {theme["hdr_border"]};
            border-radius:0 0 12px 12px;padding:18px 32px 16px;margin:-1px 0 20px 0;'>
  <div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>
    <span style='font-size:1.45rem;line-height:1;'>🤖</span>
    <h1 style='margin:0;font-size:1.45rem;font-weight:700;color:{theme["hdr_text"]};letter-spacing:-.01em;'>
      Assistant Agricole IA
    </h1>
  </div>
  <p style='margin:0;color:#8b949e;font-size:.83rem;text-align:center;'>
    Posez vos questions sur les données de Kolda — Modèle : <code>{model}</code>
  </p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TOOLS — FONCTIONS APPELÉES PAR L'AGENT
# ══════════════════════════════════════════════════════════════

def tool_sql(query: str) -> str:
    """
    Exécute une requête SQL SELECT sur la base agricole.
    Retourne les résultats sous forme de tableau texte.
    """
    query = query.strip()
    # Sécurité : uniquement SELECT
    if not re.match(r'^\s*SELECT\b', query, re.IGNORECASE):
        return "❌ Seules les requêtes SELECT sont autorisées."

    try:
        with get_connection() as conn:
            df = pd.read_sql_query(query, conn)
        if df.empty:
            return "Aucun résultat."
        return df.to_markdown(index=False)
    except Exception as e:
        return f"❌ Erreur SQL : {e}"


def tool_summary(filtre: str = "") -> str:
    """
    Statistiques descriptives sur les productions agricoles.
    filtre peut être 'campagne=2023/2024', 'culture=MIL', etc.
    """
    try:
        with get_connection() as conn:
            df = pd.read_sql_query("""
                SELECT c.libelle AS campagne, l.nom AS localite,
                       p.culture, p.type_culture,
                       p.superficie_ha, p.rendement_kgha, p.production_t, p.niveau
                FROM productions p
                JOIN campagnes c ON p.campagne_id = c.id
                JOIN localites l ON p.localite_id = l.geo_id
            """, conn)

        # Appliquer filtre simple
        if "campagne=" in filtre:
            camp = filtre.split("campagne=")[-1].split(",")[0].strip()
            df = df[df["campagne"] == camp]
        if "culture=" in filtre:
            cult = filtre.split("culture=")[-1].split(",")[0].strip().upper()
            df = df[df["culture"] == cult]
        if "localite=" in filtre:
            loc = filtre.split("localite=")[-1].split(",")[0].strip()
            df = df[df["localite"].str.contains(loc, case=False, na=False)]
        if "niveau=" in filtre:
            niv = filtre.split("niveau=")[-1].split(",")[0].strip()
            df = df[df["niveau"] == niv]

        if df.empty:
            return "Aucune donnée pour ce filtre."

        lines = [f"**{len(df)} enregistrements** ({df['campagne'].nunique()} campagne(s))"]

        prod_total = df["production_t"].sum()
        sup_total  = df["superficie_ha"].sum()
        rdt_moy    = df["rendement_kgha"].mean()
        lines.append(f"- Production totale : **{prod_total:,.1f} T**")
        lines.append(f"- Superficie totale : **{sup_total:,.1f} Ha**")
        lines.append(f"- Rendement moyen   : **{rdt_moy:,.1f} Kg/Ha**")

        top = (df.groupby("culture")["production_t"].sum()
               .sort_values(ascending=False).head(5))
        lines.append(f"\n**Top 5 cultures :**")
        for cult, prod in top.items():
            lines.append(f"  - {cult} : {prod:,.1f} T")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Erreur : {e}"


def tool_meteo(localite: str = "Kolda") -> str:
    """
    Récupère la météo actuelle d'une localité de Kolda via Open-Meteo.
    """
    COORDS = {
        "kolda":             (12.9033, -14.946),
        "medina yoro foula": (13.2928, -14.7147),
        "velingara":         (13.1472, -14.1076),
    }
    loc_key = localite.lower().strip()
    lat, lon = COORDS.get(loc_key, COORDS["kolda"])

    try:
        params = {
            "latitude":  lat, "longitude": lon,
            "timezone":  "Africa/Dakar",
            "current":   "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
            "daily":     "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
            "forecast_days": 3,
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "KoldaAgri/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())

        cur   = data.get("current", {})
        daily = data.get("daily", {})
        lines = [
            f"**Météo actuelle à {localite.title()}**",
            f"- Température : {cur.get('temperature_2m','?')} °C",
            f"- Humidité : {cur.get('relative_humidity_2m','?')} %",
            f"- Précipitations : {cur.get('precipitation','?')} mm",
            f"- Vent : {cur.get('wind_speed_10m','?')} km/h",
        ]
        if daily.get("time"):
            pluie_3j = sum(x or 0 for x in daily.get("precipitation_sum", []))
            etp_3j   = sum(x or 0 for x in daily.get("et0_fao_evapotranspiration", []))
            lines.append(f"\n**Prévisions 3 jours :**")
            lines.append(f"- Pluie cumulée : {pluie_3j:.1f} mm")
            lines.append(f"- ETP cumulée : {etp_3j:.1f} mm")
            lines.append(f"- Bilan hydrique : {pluie_3j - etp_3j:+.1f} mm")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Météo indisponible ({e}). Vérifiez votre connexion."


def tool_chart(query: str, chart_type: str = "bar",
               x: str = "", y: str = "", titre: str = "") -> tuple[str, object | None]:
    """
    Génère un graphe Plotly depuis une requête SQL.
    Retourne (texte_résumé, figure_plotly | None).
    """
    if not PLOTLY_OK:
        return "❌ Plotly non installé.", None

    try:
        with get_connection() as conn:
            df = pd.read_sql_query(query.strip(), conn)

        if df.empty:
            return "Aucune donnée pour ce graphe.", None

        cols = df.columns.tolist()
        x_col = x if x in cols else cols[0]
        y_col = y if y in cols else (cols[1] if len(cols) > 1 else cols[0])

        LAYOUT = dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9", size=12),
            margin=dict(l=10, r=10, t=40, b=10),
        )

        if chart_type == "bar":
            fig = px.bar(df, x=x_col, y=y_col, title=titre or f"{y_col} par {x_col}",
                         color_discrete_sequence=["#3fb950"])
        elif chart_type == "line":
            fig = px.line(df, x=x_col, y=y_col, title=titre or f"Évolution {y_col}",
                          markers=True, color_discrete_sequence=["#58a6ff"])
        elif chart_type == "pie":
            fig = px.pie(df, names=x_col, values=y_col, title=titre or f"Répartition {y_col}",
                         hole=0.4)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_col, y=y_col, title=titre or f"{y_col} vs {x_col}",
                             color_discrete_sequence=["#d29922"])
        else:
            fig = px.bar(df, x=x_col, y=y_col, title=titre)

        fig.update_layout(**LAYOUT, height=380)
        return f"Graphe généré ({len(df)} lignes, {len(cols)} colonnes).", fig

    except Exception as e:
        return f"❌ Erreur graphe : {e}", None


# ══════════════════════════════════════════════════════════════
# AGENT — APPEL HUGGINGFACE + DÉTECTION DES TOOLS
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Tu es un assistant spécialisé dans l'agriculture de la région de Kolda au Sénégal.
Tu as accès à une base de données SQLite avec les tables suivantes :

TABLES DISPONIBLES :
- productions (campagne_id, localite_id, culture, type_culture, superficie_ha, rendement_kgha, production_t, niveau)
- campagnes (id, annee_debut, annee_fin, libelle)  — libelle ex: '2023/2024'
- localites (geo_id, nom, type, parent_id, latitude, longitude)
- magasins (id, localite_id, departement, commune, village, capacite_t, etat)

LOCALITÉS PRINCIPALES : Kolda (R07), Medina Yoro Foulah (D023), Velingara (D022)
CULTURES : MIL, SORGHO, MAIS, RIZ, FONIO, ARACHIDE HUILERIE, NIEBE, MANIOC, PASTEQUE, SESAME
NIVEAUX : 'localite' (données départementales Kolda), 'region' (données nationales)

Pour accéder aux données, utilise ces commandes spéciales dans ta réponse :
[SQL: SELECT ...] — pour exécuter une requête SQL
[SUMMARY: filtre] — pour un résumé statistique (filtre optionnel: campagne=2023/2024, culture=MIL, etc.)
[METEO: localite] — pour la météo actuelle (Kolda, Velingara, Medina Yoro Foula)
[CHART: type|query|x_col|y_col|titre] — pour générer un graphe (type: bar/line/pie/scatter)

RÈGLES :
- Réponds toujours en français
- Si tu n'as pas l'information, utilise les commandes pour interroger la base
- Sois précis avec les chiffres agricoles
- Pour les graphes, propose-les quand c'est pertinent
- Signale si une donnée est absente ou incohérente"""

def call_hf_api(messages: list, max_tokens: int = 1024,
                temperature: float = 0.3) -> str:
    """Appel à l'API HuggingFace Inference."""
    token    = cfg("hf_api_token", "")
    model_id = cfg("hf_model_id", "mistralai/Mistral-7B-Instruct-v0.2")

    if not token:
        return "❌ Token HuggingFace non configuré. Allez dans **Configuration → API & Chatbot**."

    # Formater les messages en prompt Mistral
    prompt = "<s>"
    for msg in messages:
        if msg["role"] == "system":
            prompt += f"[INST] {msg['content']} [/INST]\n"
        elif msg["role"] == "user":
            prompt += f"[INST] {msg['content']} [/INST]"
        elif msg["role"] == "assistant":
            prompt += f" {msg['content']}</s><s>"

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature":    max(temperature, 0.01),
            "return_full_text": False,
            "stop": ["</s>", "[INST]"],
        }
    }

    url = f"https://api-inference.huggingface.co/models/{model_id}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        if isinstance(result, list) and result:
            return result[0].get("generated_text", "").strip()
        elif isinstance(result, dict):
            if "error" in result:
                return f"❌ API Error: {result['error']}"
            return result.get("generated_text", "").strip()
        return "❌ Réponse API inattendue."
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if e.code == 503:
            return "⏳ Le modèle est en cours de chargement, veuillez patienter 20-30 secondes et réessayer."
        return f"❌ Erreur HTTP {e.code}: {body[:200]}"
    except Exception as e:
        return f"❌ Erreur réseau: {e}"


def parse_and_execute_tools(response: str) -> tuple[str, list]:
    """
    Parse la réponse du LLM, exécute les tools trouvés,
    et retourne (réponse_enrichie, figures_plotly).
    """
    figures = []
    result  = response

    # [SQL: ...]
    for match in re.finditer(r'\[SQL:\s*(.*?)\]', response, re.DOTALL):
        raw_query = match.group(1).strip()
        tool_out  = tool_sql(raw_query)
        result    = result.replace(match.group(0),
                                   f"\n\n**📊 Résultat SQL :**\n{tool_out}\n")

    # [SUMMARY: ...]
    for match in re.finditer(r'\[SUMMARY:\s*(.*?)\]', response, re.DOTALL):
        filtre   = match.group(1).strip()
        tool_out = tool_summary(filtre)
        result   = result.replace(match.group(0),
                                  f"\n\n**📈 Résumé statistique :**\n{tool_out}\n")

    # [METEO: ...]
    for match in re.finditer(r'\[METEO:\s*(.*?)\]', response, re.DOTALL):
        localite = match.group(1).strip()
        tool_out = tool_meteo(localite)
        result   = result.replace(match.group(0),
                                  f"\n\n**☁️ Météo :**\n{tool_out}\n")

    # [CHART: type|query|x|y|titre]
    for match in re.finditer(r'\[CHART:\s*(.*?)\]', response, re.DOTALL):
        parts  = match.group(1).split("|")
        ctype  = parts[0].strip() if len(parts) > 0 else "bar"
        cquery = parts[1].strip() if len(parts) > 1 else ""
        cx     = parts[2].strip() if len(parts) > 2 else ""
        cy     = parts[3].strip() if len(parts) > 3 else ""
        ctitle = parts[4].strip() if len(parts) > 4 else ""
        text_out, fig = tool_chart(cquery, ctype, cx, cy, ctitle)
        result = result.replace(match.group(0),
                                f"\n\n**📊 Graphe :** {text_out}\n")
        if fig:
            figures.append(fig)

    return result, figures


# ══════════════════════════════════════════════════════════════
# QUESTIONS RAPIDES
# ══════════════════════════════════════════════════════════════

QUESTIONS_RAPIDES = [
    ("🌾 Production totale", "Quelle est la production totale de la région de Kolda pour la dernière campagne ?"),
    ("📊 Top cultures", "Quelles sont les 5 cultures les plus produites à Kolda ?"),
    ("💧 Météo actuelle", "Quelle est la météo actuelle à Kolda et quel est son impact potentiel sur les cultures ?"),
    ("📈 Comparaison", "Compare la production entre les campagnes 2020/2021 et 2023/2024."),
    ("🏪 Magasins", "Quel est l'état des magasins de stockage dans la région de Kolda ?"),
    ("🌧️ Bilan hydrique", "Quel est le bilan hydrique actuel à Kolda et que recommandes-tu pour les agriculteurs ?"),
    ("📐 Rendements", "Quels sont les rendements moyens par culture à Kolda ?"),
    ("🗺️ Comparaison depts", "Compare la production agricole entre les 3 départements de Kolda."),
]


# ══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Chatbot IA — Kolda Agri",
        page_icon="🤖",
        layout="wide",
    )

    if not DB_PATH.exists():
        st.error("❌ Base introuvable. Lancez `python db/bootstrap.py` d'abord.")
        return

    theme = apply_theme()
    render_header(theme)

    # Initialiser l'historique de conversation
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_figures" not in st.session_state:
        st.session_state.chat_figures = {}

    # ── Sidebar ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Paramètres")
        max_tokens  = st.slider("Tokens max", 256, 2048,
                                int(cfg("chatbot_max_tokens", "1024")), 64)
        temperature = st.slider("Température", 0.0, 1.0,
                                float(cfg("chatbot_temperature", "0.3")), 0.05)
        langue      = st.selectbox("Langue", ["fr","en","wolof"],
                                   index=["fr","en","wolof"].index(
                                       cfg("chatbot_langue","fr")))
        st.divider()

        # Vérif token
        hf_token = cfg("hf_api_token","")
        if hf_token:
            st.success("✅ Token HuggingFace configuré")
        else:
            st.error("❌ Token manquant")
            st.page_link("pages/5_Configuration.py",
                         label="→ Configurer le token", icon="⚙️")

        st.divider()
        if st.button("🗑️ Vider la conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.chat_figures = {}
            st.rerun()

        # Infos DB
        st.divider()
        st.markdown("### 📊 Base de données")
        with get_connection() as conn:
            nb_prod = conn.execute("SELECT COUNT(*) FROM productions").fetchone()[0]
            nb_camp = conn.execute("SELECT COUNT(*) FROM campagnes").fetchone()[0]
        st.caption(f"{nb_prod} productions · {nb_camp} campagnes")

    # ── Questions rapides ─────────────────────────────────────
    if not st.session_state.chat_history:
        st.markdown("#### 💬 Questions suggérées")
        cols = st.columns(4)
        for i, (label, question) in enumerate(QUESTIONS_RAPIDES):
            if cols[i % 4].button(label, key=f"qq_{i}", use_container_width=True):
                st.session_state.chat_history.append(
                    {"role": "user", "content": question})
                st.rerun()

    # ── Historique ────────────────────────────────────────────
    for i, msg in enumerate(st.session_state.chat_history):
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        elif msg["role"] == "assistant":
            with st.chat_message("assistant", avatar="🌾"):
                st.markdown(msg["content"])
                # Afficher les figures associées à ce message
                figs = st.session_state.chat_figures.get(i, [])
                for fig in figs:
                    st.plotly_chart(fig, use_container_width=True)

    # ── Entrée utilisateur ────────────────────────────────────
    user_input = st.chat_input(
        "Posez votre question sur l'agriculture de Kolda…",
        key="chat_input"
    )

    if user_input and user_input.strip():
        # Ajouter le message utilisateur
        st.session_state.chat_history.append(
            {"role": "user", "content": user_input.strip()})

        # Construire les messages pour l'API
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Garder les N derniers messages pour le contexte
        history_window = st.session_state.chat_history[-12:]
        messages.extend(history_window[:-1])  # sans le dernier (déjà dans history)
        messages.append({"role": "user", "content": user_input.strip()})

        # Appel LLM
        with st.chat_message("assistant", avatar="🌾"):
            with st.spinner("🤔 Réflexion en cours…"):
                raw_response = call_hf_api(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            # Parser et exécuter les tools
            with st.spinner("🔧 Exécution des outils…") if (
                "[SQL:" in raw_response or "[CHART:" in raw_response
                or "[SUMMARY:" in raw_response or "[METEO:" in raw_response
            ) else st.empty():
                enriched, figures = parse_and_execute_tools(raw_response)

            st.markdown(enriched)
            for fig in figures:
                st.plotly_chart(fig, use_container_width=True)

        # Sauvegarder dans l'historique
        msg_idx = len(st.session_state.chat_history)
        st.session_state.chat_history.append(
            {"role": "assistant", "content": enriched})
        if figures:
            st.session_state.chat_figures[msg_idx] = figures

        st.rerun()

    # ── Exemples de commandes SQL ─────────────────────────────
    if len(st.session_state.chat_history) == 0:
        with st.expander("💡 Exemples de questions que vous pouvez poser"):
            st.markdown("""
            **Données agricoles**
            - *Quelle est la production de riz à Médina Yoro Foulah en 2023/2024 ?*
            - *Montre-moi un graphe de la production par culture pour la dernière campagne.*
            - *Compare les rendements du mil entre 2020 et 2023.*
            - *Quels départements ont les meilleures productions d'arachide ?*

            **Météo & agronomie**
            - *Quelle est la météo à Vélingara aujourd'hui ?*
            - *Y a-t-il un déficit hydrique à Kolda en ce moment ?*
            - *Est-ce une bonne période pour semer du mil ?*

            **Magasins & stockage**
            - *Combien de magasins sont en bon état dans la région ?*
            - *Quelle est la capacité de stockage disponible par département ?*

            **Analyse**
            - *Génère un graphe circulaire de la répartition des cultures par type.*
            - *Quel est le bilan de la campagne 2023/2024 pour Kolda ?*
            """)


if __name__ == "__main__":
    main()
