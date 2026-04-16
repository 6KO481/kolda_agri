"""
DASHBOARD DE DEVELOPPEMENT RURAL - REGION DE KOLDA
Application principale
"""

import streamlit as st
import sys
import os

# DOIT ÊTRE LA PREMIÈRE LIGNE
st.set_page_config(
    page_title="Dashboard Direction Régionale du Développement Rural de Kolda",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration du chemin pour les imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))

# Import du style
try:
    from utils.style import CSS
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    STYLE_AVAILABLE = True
except ImportError:
    STYLE_AVAILABLE = False

# Initialisation de l'état de session
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Données"

# ============================================================================
# SIDEBAR - NAVIGATION
# ============================================================================

with st.sidebar:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <h1 style="color: #4CAF50; font-size: 1.8rem;">🌱 KOLDA</h1>
        <p style="color: #D1D5DB; font-size: 0.9rem;">Dashboard Direction Régionale du Développement Rural</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Navigation par boutons
    st.markdown("**NAVIGATION**")
    
    views = {
        "Données": "📊 Gestion des Données", 
        "Dashboard": "📈 Dashboard Avancées",
        "Meteo": "🌤️ Météo & Climat",
        "Carte": " Cartes",
        "Configuration": "❓ Configuration",
        "Chatbot": "🤖 Chatbot"
    }
    
    for page_key, page_label in views.items():
        if st.button(
            page_label,
            key=f"nav_{page_key}",
            use_container_width=True,
            type="primary" if st.session_state.current_page == page_key else "secondary"
        ):
            st.session_state.current_page = page_key
            st.rerun()
    
    st.divider()
    
    # Informations système
    st.markdown("""
    <div style="margin-top: 2rem; padding: 1rem; background-color: #1E293B; border-radius: 10px;">
        <p style="color: #9CA3AF; font-size: 0.8rem; margin: 0;">
        <strong>📊 Version:</strong> 2.0.0<br>
        <strong>🌍 Région:</strong> Kolda<br>
        <strong>📅 Dernière MAJ:</strong> 2025
        </p>
    </div>
    """, unsafe_allow_html=True)

# ============================================================================
# CHARGEMENT DES views
# ============================================================================

page = st.session_state.current_page

if page == "Meteo":
    try:
        import views.Meteo
        views.Meteo.main()
    except ImportError as e:
        st.error(f"Erreur: {e}")
        st.title("🌤️ Météo & Climat")
        st.info("Page de gestion du Climat")

elif page == "Données":
    try:
        import views.Données_Admin
        views.Données_Admin.main()
    except ImportError as e:
        st.error(f"Erreur: {e}")
        st.title("📊 Gestion des Données")
        st.info("Page de gestion des données")
 #stats_avancees       
elif page == "Dashboard":
    try:
        import views.Dashboard
        views.Dashboard.main()
    except ImportError as e:
        st.error(f"Erreur: {e}")
        st.title("📊 Statistiques Avancées")
        st.info("Page des Statistiques Avancées")
    
elif page == "Carte":
    try:
        import views.Carte
        views.Carte.main()
    except ImportError as e:
        st.error(f"Erreur: {e}")
        st.title("📊 Statistiques Avancées")
        st.info("Page des Statistiques Avancées")

elif page == "Chatbot":
    try:
        import views.Chatbot
        views.Chatbot.main()
    except ImportError as e:
        st.error(f"Erreur: {e}")
        st.title("erreur de chargement")
        st.info("Page de l'asistant IA")

    
elif page == "Configuration":
    try:
        import views.Configuration
        views.Configuration.main()
    except ImportError as e:
        st.error(f"Erreur: {e}")
        st.title("IA - Chat")
        st.info("Page en développement")

# ============================================================================
# FOOTER
# ============================================================================
#######################

#####################""
