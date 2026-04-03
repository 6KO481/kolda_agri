"""
PAGE 5 — CONFIGURATION
Gestion centralisée de tous les paramètres du dashboard.
Toutes les valeurs sont lues et écrites dans la table SQLite `configuration`.
"""

import sys
import json
import re
from pathlib import Path

import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))

from utils import get_connection, get_config, set_config, reset_config, DB_PATH


# ══════════════════════════════════════════════════════════════
# THEME (minimal — la page config ELLE-MÊME se styler)
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_config_full() -> pd.DataFrame:
    """Charge toutes les lignes de la table configuration."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM configuration ORDER BY categorie, cle", conn)


def cfg(key, default=""):
    return st.session_state.get("_config", {}).get(key, default)


def apply_theme():
    if "_config" not in st.session_state:
        with get_connection() as conn:
            st.session_state["_config"] = get_config(conn)

    primary       = cfg("color_primary",      "#3fb950")
    font          = cfg("font_family",         "IBM Plex Mono, sans-serif").split(",")[0].strip()
    hdr_bg        = cfg("header_bg_color",     "#1c2a1e")
    hdr_border    = cfg("header_border_color", "#3fb950")
    hdr_text      = cfg("header_text_color",   "#e6edf3")
    tab_active    = cfg("tab_active_color",    "#3fb950")
    subtab_active = cfg("subtab_active_color", "#58a6ff")

    def _hex_rgba(h, a=0.07):
        h = h.lstrip("#")
        if len(h) == 6:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
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
    /* Aperçu couleur inline */
    .color-swatch {{
        display:inline-block; width:14px; height:14px;
        border-radius:3px; border:1px solid rgba(255,255,255,0.2);
        vertical-align:middle; margin-right:6px;
    }}
    </style>
    """, unsafe_allow_html=True)
    return {"primary": primary, "hdr_bg": hdr_bg,
            "hdr_border": hdr_border, "hdr_text": hdr_text}


def render_header(theme):
    st.markdown(f"""
<div style='background:{theme["hdr_bg"]};border:1px solid rgba(255,255,255,0.06);
            border-left:4px solid {theme["hdr_border"]};
            border-radius:0 0 12px 12px;padding:18px 32px 16px;margin:-1px 0 20px 0;'>
  <div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>
    <span style='font-size:1.45rem;line-height:1;'>⚙️</span>
    <h1 style='margin:0;font-size:1.45rem;font-weight:700;color:{theme["hdr_text"]};letter-spacing:-.01em;'>
      Configuration
    </h1>
  </div>
  <p style='margin:0;color:#8b949e;font-size:.83rem;text-align:center;'>
    Paramètres du dashboard — stockés dans SQLite, appliqués à toutes les pages
  </p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# HELPERS — WIDGETS PAR TYPE
# ══════════════════════════════════════════════════════════════

def _to_hex(color_str: str) -> str:
    """Convertit une chaîne de couleur (hex, rgb, rgba) en hexadécimal #RRGGBB."""
    color_str = color_str.strip()
    if re.match(r"^#[0-9A-Fa-f]{6}$", color_str):
        return color_str
    if re.match(r"^#[0-9A-Fa-f]{3}$", color_str):
        return f"#{color_str[1]*2}{color_str[2]*2}{color_str[3]*2}"
    m = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", color_str)
    if m:
        r, g, b = map(int, m.groups())
        return f"#{r:02x}{g:02x}{b:02x}"
    return "#3fb950"


def _render_widget(row: pd.Series, key_prefix: str) -> tuple[str, bool]:
    """
    Affiche le widget approprié selon type_valeur.
    Retourne (nouvelle_valeur, modifiée).
    """
    cle        = row["cle"]
    valeur_act = row["valeur"]
    defaut     = row["valeur_defaut"]
    label      = row["label"]
    desc       = row.get("description") or ""
    type_val   = row["type_valeur"]
    options_raw= row.get("options")
    widget_key = f"{key_prefix}_{cle}"

    help_txt = f"{desc} (défaut : {defaut})" if desc else f"Défaut : {defaut}"

    new_val = valeur_act

    # Cas spécial : police de caractères -> afficher un selectbox
    if cle == "font_family":
        # Liste des polices courantes
        font_options = [
            "IBM Plex Mono", "Sora", "Times New Roman", "Georgia", 
            "Arial", "Verdana", "Courier New", "Trebuchet MS", "Tahoma"
        ]
        # Trouver l'index de la valeur actuelle (peut être "IBM Plex Mono, sans-serif" ou autre)
        current_font = valeur_act.split(",")[0].strip()
        if current_font not in font_options:
            font_options.insert(0, current_font)
        idx = font_options.index(current_font) if current_font in font_options else 0
        selected = st.selectbox(label, options=font_options, index=idx,
                                key=widget_key, help=help_txt)
        new_val = selected
        # On conserve le suffixe ", sans-serif" pour la compatibilité CSS
        if not new_val.endswith(", sans-serif"):
            new_val = f"{new_val}, sans-serif"

    elif type_val == "color":
        current_hex = _to_hex(valeur_act)
        picked = st.color_picker(label, value=current_hex, key=widget_key, help=help_txt)
        new_val = picked
        if not new_val.startswith("#"):
            new_val = "#" + new_val

    elif type_val == "select":
        try:
            opts = json.loads(options_raw) if options_raw else [valeur_act]
        except (json.JSONDecodeError, TypeError):
            opts = [valeur_act]
        idx = opts.index(valeur_act) if valeur_act in opts else 0
        new_val = st.selectbox(label, options=opts, index=idx,
                               key=widget_key, help=help_txt)

    elif type_val == "boolean":
        new_val = "true" if st.checkbox(
            label, value=(valeur_act == "true"),
            key=widget_key, help=help_txt) else "false"

    elif type_val == "range":
        try:
            meta = json.loads(options_raw) if options_raw else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        mn   = meta.get("min", 0)
        mx   = meta.get("max", 100)
        step = meta.get("step", 1)
        try:
            cur_f = float(valeur_act)
        except (ValueError, TypeError):
            cur_f = float(mn)
        if isinstance(step, float):
            new_raw = st.slider(label, min_value=float(mn), max_value=float(mx),
                                value=cur_f, step=float(step),
                                key=widget_key, help=help_txt)
        else:
            new_raw = st.slider(label, min_value=int(mn), max_value=int(mx),
                                value=int(cur_f), step=int(step),
                                key=widget_key, help=help_txt)
        new_val = str(new_raw)

    elif type_val == "number":
        try:
            cur_f = float(valeur_act)
        except (ValueError, TypeError):
            cur_f = 0.0
        new_raw = st.number_input(label, value=cur_f, format="%.4f",
                                  key=widget_key, help=help_txt)
        new_val = str(new_raw)

    elif type_val == "text":
        is_secret = any(w in cle.lower()
                        for w in ("token","password","secret","api_key","key"))
        new_val = st.text_input(
            label, value=valeur_act or "",
            type="password" if is_secret else "default",
            key=widget_key, help=help_txt,
            placeholder="(vide)")

    else:
        new_val = st.text_input(label, value=valeur_act or "",
                                key=widget_key, help=help_txt)

    modifiee = str(new_val) != str(valeur_act)
    return str(new_val), modifiee


def _save_changes(changes: dict[str, str]):
    """Enregistre les modifications en base et invalide le cache."""
    if not changes:
        return
    with get_connection() as conn:
        for cle, valeur in changes.items():
            set_config(conn, cle, valeur)
    load_config_full.clear()
    if "_config" in st.session_state:
        del st.session_state["_config"]
    st.success(f"✅ {len(changes)} paramètre(s) sauvegardé(s).")
    st.rerun()


def _reset_category(categorie: str, df_cfg: pd.DataFrame):
    """Remet les valeurs par défaut d'une catégorie."""
    with get_connection() as conn:
        subset = df_cfg[df_cfg["categorie"] == categorie]
        for _, row in subset.iterrows():
            set_config(conn, row["cle"], row["valeur_defaut"])
    load_config_full.clear()
    if "_config" in st.session_state:
        del st.session_state["_config"]
    st.success(f"✅ Catégorie '{categorie}' remise aux valeurs par défaut.")
    st.rerun()


# ══════════════════════════════════════════════════════════════
# SECTION PAR CATÉGORIE (avec gestion du nombre de colonnes)
# ══════════════════════════════════════════════════════════════

def _section(df_cfg: pd.DataFrame, categorie: str,
             titre: str, icon: str, key_prefix: str,
             columns: int = 1):
    """
    Affiche une section de paramètres.
    - columns : nombre de colonnes pour répartir les widgets (par défaut 1)
    """
    subset = df_cfg[df_cfg["categorie"] == categorie].reset_index(drop=True)
    if subset.empty:
        return

    st.markdown(f"#### {icon} {titre}")

    # Préparer les widgets dans des colonnes
    if columns > 1:
        cols = st.columns(columns)
        changes = {}
        # On répartit les widgets sur les colonnes
        for idx, (_, row) in enumerate(subset.iterrows()):
            col = cols[idx % columns]
            with col:
                new_val, modifiee = _render_widget(row, key_prefix)
                if modifiee:
                    changes[row["cle"]] = new_val
                # Pas de message d'avertissement
    else:
        changes = {}
        for _, row in subset.iterrows():
            new_val, modifiee = _render_widget(row, key_prefix)
            if modifiee:
                changes[row["cle"]] = new_val
            # Pas de message d'avertissement

    # Boutons sauvegarder / réinitialiser
    col_save, col_reset, _ = st.columns([2, 2, 4])
    with col_save:
        if st.button(f"💾 Sauvegarder {titre}", key=f"save_{key_prefix}",
                     type="primary", use_container_width=True):
            # Collecter toutes les valeurs depuis session_state
            all_vals = {}
            for _, row in subset.iterrows():
                wk = f"{key_prefix}_{row['cle']}"
                val = st.session_state.get(wk)
                if val is not None:
                    if row["type_valeur"] == "boolean":
                        val = "true" if val else "false"
                    elif row["type_valeur"] == "range":
                        val = str(val)
                    all_vals[row["cle"]] = str(val)
            _save_changes(all_vals)

    with col_reset:
        if st.button(f"↺ Défauts {titre}", key=f"reset_{key_prefix}",
                     use_container_width=True):
            st.session_state[f"_confirm_reset_{key_prefix}"] = True

    if st.session_state.get(f"_confirm_reset_{key_prefix}"):
        st.warning(f"Remettre **{titre}** aux valeurs d'origine ?")
        c1, c2 = st.columns(2)
        if c1.button("✅ Confirmer", key=f"yes_reset_{key_prefix}", type="primary"):
            _reset_category(categorie, df_cfg)
        if c2.button("❌ Annuler", key=f"no_reset_{key_prefix}"):
            st.session_state[f"_confirm_reset_{key_prefix}"] = False
            st.rerun()


# ══════════════════════════════════════════════════════════════
# ONGLET 1 — THÈME & APPARENCE (avec disposition en lignes)
# ══════════════════════════════════════════════════════════════

def onglet_theme(df_cfg: pd.DataFrame):
    st.info("💡 Les modifications de thème s'appliquent à toutes les pages après sauvegarde.")

    # Aperçu en temps réel
    primary = cfg("color_primary", "#3fb950")
    hdr_bg  = cfg("header_bg_color", "#1c2a1e")
    st.markdown(f"""
    <div style='background:{hdr_bg};border-left:4px solid {primary};
                border-radius:8px;padding:12px 20px;margin-bottom:20px;'>
        <span style='color:#e6edf3;font-weight:600;'>🎨 Aperçu du bandeau actuel</span>
        <span style='color:#8b949e;font-size:.82rem;margin-left:12px;'>
            Couleur primaire :
            <span class='color-swatch' style='background:{primary};'></span>{primary}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Section Bandeau & onglets (2 colonnes)
    _section(df_cfg, "theme", "Bandeau & onglets", "🎨", "theme", columns=4)
    st.divider()
    # Section Couleurs graphes (2 colonnes)
    _section(df_cfg, "couleurs", "Couleurs graphes", "🖌️", "couleurs", columns=4)
    st.divider()
    # Section Typographie (1 colonne, mais on peut aussi mettre 2)
    _section(df_cfg, "typographie", "Typographie", "🔤", "typo", columns=1)


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — AFFICHAGE
# ══════════════════════════════════════════════════════════════

def onglet_affichage(df_cfg: pd.DataFrame):
    st.info("💡 Ces paramètres contrôlent la présentation des données dans les tableaux.")
    _section(df_cfg, "affichage", "Affichage des données", "📋", "aff", columns=1)


# ══════════════════════════════════════════════════════════════
# ONGLET 3 — CARTE
# ══════════════════════════════════════════════════════════════

def onglet_carte(df_cfg: pd.DataFrame):
    st.info("💡 Centre et zoom par défaut de la carte Folium.")

    lat = cfg("carte_lat_defaut", "12.9033")
    lon = cfg("carte_lon_defaut", "-14.946")
    zoom = cfg("carte_zoom_defaut", "9")
    st.markdown(f"""
    <div style='background:rgba(88,166,255,0.08);border-left:3px solid #58a6ff;
                border-radius:6px;padding:10px 16px;margin-bottom:16px;font-family:monospace;font-size:.85rem;'>
        Centre actuel : <b>{lat}, {lon}</b> &nbsp;|&nbsp; Zoom : <b>{zoom}</b>
    </div>
    """, unsafe_allow_html=True)

    _section(df_cfg, "carte", "Paramètres carte", "🗺️", "carte", columns=1)


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — BASE DE DONNÉES
# ══════════════════════════════════════════════════════════════

def onglet_base():
    st.markdown("#### 🗄️ Informations sur la base de données")

    if not DB_PATH.exists():
        st.error("❌ Base introuvable.")
        return

    size_mb = DB_PATH.stat().st_size / 1024 / 1024
    from datetime import datetime
    mtime   = datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime("%d/%m/%Y %H:%M")

    col1, col2, col3 = st.columns(3)
    col1.metric("📁 Taille DB",        f"{size_mb:.2f} Mo")
    col2.metric("🕐 Dernière modif.",  mtime)
    col3.metric("📍 Chemin",           str(DB_PATH.name))

    st.code(str(DB_PATH), language=None)

    st.divider()
    st.markdown("#### 📊 Statistiques par table")
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        rows_data = []
        for (t,) in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            rows_data.append({"Table": t, "Lignes": n})
    st.dataframe(pd.DataFrame(rows_data), hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("#### 📋 Tableau de configuration complet")
    st.caption("Vue en lecture seule de toutes les clés — modifications via les onglets ci-dessus.")
    with get_connection() as conn:
        df_all = pd.read_sql_query(
            "SELECT cle, valeur, valeur_defaut, categorie, label FROM configuration ORDER BY categorie, cle",
            conn)
    df_all["Modifiée"] = df_all["valeur"] != df_all["valeur_defaut"]
    st.dataframe(
        df_all.rename(columns={"cle":"Clé","valeur":"Valeur actuelle",
                               "valeur_defaut":"Défaut","categorie":"Catégorie","label":"Label"}),
        hide_index=True, use_container_width=True,
        column_config={
            "Modifiée": st.column_config.CheckboxColumn("Modifiée", disabled=True)
        })

    st.divider()
    st.markdown("#### ⚠️ Réinitialisation globale")
    st.warning("Remet **TOUTE** la configuration aux valeurs par défaut d'origine.")
    if st.button("↺ Tout réinitialiser", key="reset_all"):
        st.session_state["_confirm_reset_all"] = True

    if st.session_state.get("_confirm_reset_all"):
        st.error("Confirmer la réinitialisation complète de la configuration ?")
        c1, c2 = st.columns(2)
        if c1.button("✅ Confirmer", type="primary", key="yes_reset_all"):
            with get_connection() as conn:
                reset_config(conn)
            load_config_full.clear()
            if "_config" in st.session_state:
                del st.session_state["_config"]
            st.session_state["_confirm_reset_all"] = False
            st.success("✅ Configuration réinitialisée.")
            st.rerun()
        if c2.button("❌ Annuler", key="no_reset_all"):
            st.session_state["_confirm_reset_all"] = False
            st.rerun()

    st.divider()
    st.markdown("#### 💾 Export / Import configuration")
    col_exp, col_imp = st.columns(2)
    with col_exp:
        with get_connection() as conn:
            df_exp = pd.read_sql_query(
                "SELECT cle, valeur FROM configuration ORDER BY cle", conn)
        export_json = df_exp.set_index("cle")["valeur"].to_dict()
        st.download_button(
            "⬇ Exporter la config (JSON)",
            data=json.dumps(export_json, ensure_ascii=False, indent=2),
            file_name="kolda_agri_config.json",
            mime="application/json",
            use_container_width=True)

    with col_imp:
        uploaded = st.file_uploader("⬆ Importer une config (JSON)",
                                    type=["json"], key="import_cfg")
        if uploaded:
            try:
                imported = json.loads(uploaded.read())
                with get_connection() as conn:
                    n = 0
                    for cle, valeur in imported.items():
                        exists = conn.execute(
                            "SELECT 1 FROM configuration WHERE cle=?", (cle,)).fetchone()
                        if exists:
                            set_config(conn, cle, str(valeur))
                            n += 1
                load_config_full.clear()
                if "_config" in st.session_state:
                    del st.session_state["_config"]
                st.success(f"✅ {n} paramètre(s) importé(s).")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur import : {e}")


# ══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Configuration — Kolda Agri",
        page_icon="⚙️",
        layout="wide",
    )

    if not DB_PATH.exists():
        st.error("❌ Base introuvable. Lancez `python db/bootstrap.py` d'abord.")
        return

    theme  = apply_theme()
    df_cfg = load_config_full()

    render_header(theme)

    tabs = st.tabs([
        "🎨 Thème & apparence",
        "📋 Affichage",
        "🗺️ Carte",
        "🗄️ Base de données",
    ])

    with tabs[0]: onglet_theme(df_cfg)
    with tabs[1]: onglet_affichage(df_cfg)
    with tabs[2]: onglet_carte(df_cfg)
    with tabs[3]: onglet_base()


if __name__ == "__main__":
    main()