"""
PAGE 1 — DONNÉES & ADMINISTRATION
4 onglets : Production | Magasins | Géographie | Qualité des données
Toutes les données viennent de SQLite via db/utils.py
"""

import sys
import json
import time
import tempfile
from pathlib import Path
import streamlit as st
import pandas as pd

# ── Helper persistance onglets ────────────────────────────────
def _get_tab(key: str, default: int = 0) -> int:
    return st.session_state.get(f"_tab_{key}", default)

def _set_tab(key: str, idx: int):
    st.session_state[f"_tab_{key}"] = idx

def _tabs(label_list: list, key: str) -> list:
    """Wrapper st.tabs qui restaure l'onglet actif après rerun."""
    # Streamlit ne supporte pas default_index nativement,
    # mais on peut injecter du JS minimal pour cliquer sur le bon onglet
    # au rendu suivant via session_state + st.markdown
    return st.tabs(label_list)

# ── Chemins ───────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))

from utils import get_connection, db_connection, next_geo_id, get_config, clean_numeric, DB_PATH
from import_excel import (
    importer_fichier_production,
    importer_fichier_magasins,
    importer_fichier_geo,
)

# ══════════════════════════════════════════════════════════════
# CONFIGURATION UI (depuis la table configuration)
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def load_config() -> dict:
    with db_connection() as conn:
        return get_config(conn)

def cfg(key: str, default="") -> str:
    return st.session_state.get("_config", {}).get(key, default)

# ══════════════════════════════════════════════════════════════
# REQUÊTES SQL RÉUTILISABLES
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def query_productions(campagne_id=None, culture=None, type_culture=None,
                      niveau=None, localite_id=None) -> pd.DataFrame:
    sql = """
        SELECT p.id, c.libelle AS campagne, c.id AS campagne_id,
               l.nom AS localite, l.geo_id AS localite_id, l.type AS type_geo,
               p.culture, p.type_culture,
               ROUND(p.superficie_ha, 2)  AS superficie_ha,
               ROUND(p.rendement_kgha, 1) AS rendement_kgha,
               ROUND(p.production_t, 2)   AS production_t,
               p.niveau, p.notes
        FROM productions p
        JOIN campagnes c ON p.campagne_id = c.id
        JOIN localites l ON p.localite_id = l.geo_id
        WHERE 1=1
    """
    params = []
    if campagne_id:
        sql += " AND p.campagne_id = ?"; params.append(campagne_id)
    if culture:
        sql += " AND p.culture = ?";     params.append(culture)
    if type_culture:
        sql += " AND p.type_culture = ?"; params.append(type_culture)
    if niveau:
        sql += " AND p.niveau = ?";      params.append(niveau)
    if localite_id:
        sql += " AND p.localite_id = ?"; params.append(localite_id)
    sql += " ORDER BY c.annee_debut DESC, l.nom, p.culture"

    with db_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


@st.cache_data(ttl=30)
def query_campagnes() -> pd.DataFrame:
    with db_connection() as conn:
        return pd.read_sql_query(
            "SELECT id, libelle, annee_debut, annee_fin, source_fichier, date_import "
            "FROM campagnes ORDER BY annee_debut DESC", conn)


@st.cache_data(ttl=30)
def query_magasins(dept=None, etat=None) -> pd.DataFrame:
    sql = """
        SELECT m.id, m.departement, m.commune, m.village,
               m.capacite_t, m.etat, m.contact,
               m.latitude, m.longitude, m.notes,
               l.nom AS localite_nom
        FROM magasins m
        LEFT JOIN localites l ON m.localite_id = l.geo_id
        WHERE 1=1
    """
    params = []
    if dept:
        sql += " AND m.departement = ?"; params.append(dept)
    if etat:
        sql += " AND m.etat = ?";        params.append(etat)
    sql += " ORDER BY m.departement, m.commune, m.village"
    with db_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


@st.cache_data(ttl=30)
def query_localites(type_loc=None, parent_id=None) -> pd.DataFrame:
    sql = "SELECT * FROM localites WHERE 1=1"
    params = []
    if type_loc:
        sql += " AND type = ?";      params.append(type_loc)
    if parent_id:
        sql += " AND parent_id = ?"; params.append(parent_id)
    sql += " ORDER BY type, nom"
    with db_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


@st.cache_data(ttl=30)
def query_qualite() -> dict:
    with db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM productions").fetchone()[0]
        null_sup  = conn.execute("SELECT COUNT(*) FROM productions WHERE superficie_ha IS NULL").fetchone()[0]
        null_rdt  = conn.execute("SELECT COUNT(*) FROM productions WHERE rendement_kgha IS NULL").fetchone()[0]
        null_prod = conn.execute("SELECT COUNT(*) FROM productions WHERE production_t IS NULL").fetchone()[0]
        incoherents = conn.execute("""
            SELECT COUNT(*) FROM productions
            WHERE superficie_ha IS NOT NULL AND rendement_kgha IS NOT NULL
              AND production_t IS NOT NULL AND production_t > 0
              AND ABS((superficie_ha * rendement_kgha / 1000.0) - production_t)
                  / production_t > 0.05
        """).fetchone()[0]
        par_campagne = pd.read_sql_query("""
            SELECT c.libelle AS campagne,
                   COUNT(p.id) AS total,
                   SUM(CASE WHEN p.superficie_ha IS NULL THEN 1 ELSE 0 END) AS null_sup,
                   SUM(CASE WHEN p.rendement_kgha IS NULL THEN 1 ELSE 0 END) AS null_rdt,
                   SUM(CASE WHEN p.production_t IS NULL THEN 1 ELSE 0 END) AS null_prod
            FROM productions p JOIN campagnes c ON p.campagne_id = c.id
            GROUP BY c.id ORDER BY c.annee_debut DESC
        """, conn)
        # Localités non résolues dans magasins
        mag_sans_geo = conn.execute(
            "SELECT COUNT(*) FROM magasins WHERE localite_id IS NULL").fetchone()[0]
        # Score synthétique /100
        champs_total = total * 3
        champs_null  = null_sup + null_rdt + null_prod
        completude   = round((1 - champs_null / max(champs_total, 1)) * 100, 1)
        coherence    = round((1 - incoherents / max(total, 1)) * 100, 1)
        score        = round((completude + coherence) / 2, 1)
        return dict(total=total, null_sup=null_sup, null_rdt=null_rdt,
                    null_prod=null_prod, incoherents=incoherents,
                    mag_sans_geo=mag_sans_geo, completude=completude,
                    coherence=coherence, score=score,
                    par_campagne=par_campagne)


def invalidate_cache():
    """Vide les caches Streamlit après toute modification."""
    query_productions.clear()
    query_campagnes.clear()
    query_magasins.clear()
    query_localites.clear()
    query_qualite.clear()


# ══════════════════════════════════════════════════════════════
# COMPOSANTS UI RÉUTILISABLES
# ══════════════════════════════════════════════════════════════

def metric_row(items: list[tuple]):
    """items = [(label, value, delta?), ...]"""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value = item[0], item[1]
        delta = item[2] if len(item) > 2 else None
        col.metric(label, value, delta)


def confirm_delete(key: str, label: str = "Confirmer la suppression") -> bool:
    """Retourne True si l'utilisateur confirme. Gère l'état via session_state."""
    if st.session_state.get(f"_confirm_{key}"):
        st.warning(f"⚠️ {label} — cette action est irréversible.")
        c1, c2 = st.columns(2)
        if c1.button("✅ Confirmer", key=f"_yes_{key}", type="primary"):
            st.session_state[f"_confirm_{key}"] = False
            return True
        if c2.button("❌ Annuler", key=f"_no_{key}"):
            st.session_state[f"_confirm_{key}"] = False
            st.rerun()
    return False


def export_buttons(df: pd.DataFrame, prefix: str):
    """Boutons export CSV + Excel."""
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇ CSV", df.to_csv(index=False).encode(),
            f"{prefix}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
            "text/csv", use_container_width=True, key=f"csv_{prefix}")
    with c2:
        from io import BytesIO
        buf = BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "⬇ Excel", buf.getvalue(),
            f"{prefix}_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, key=f"xlsx_{prefix}")


# ══════════════════════════════════════════════════════════════
# ONGLET 1 — PRODUCTION
# ══════════════════════════════════════════════════════════════

def onglet_production():
    campagnes_df = query_campagnes()
    camp_options = {r.libelle: r.id for _, r in campagnes_df.iterrows()}
    all_df       = query_productions()

    sub = st.tabs(["📋 Consulter & Modifier", "📤 Importer", "🗑️ Gérer / Supprimer"])

    # ── Consulter & Modifier (fusionnés) ──────────────────────
    with sub[0]:
        st.info("💡 Filtrez les données puis double-cliquez sur une cellule pour l'éditer. Cliquez **Sauvegarder** pour enregistrer en base.")

        # ── Filtres ──
        with st.expander("🔎 Filtres", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            camp_sel = c1.selectbox("Campagne", ["Toutes"] + list(camp_options.keys()), key="f_camp")
            cult_sel = c2.selectbox("Culture",
                ["Toutes"] + sorted(all_df["culture"].unique().tolist()), key="f_cult")
            type_sel = c3.selectbox("Type",
                ["Tous"] + sorted(all_df["type_culture"].dropna().unique().tolist()), key="f_type")
            niv_sel  = c4.selectbox("Niveau", ["Tous", "localite", "region"], key="f_niv")

            # Recherche textuelle dans une colonne
            c5, c6 = st.columns([2, 3])
            search_col = c5.selectbox("Rechercher dans", 
                ["localite", "culture", "type_culture", "campagne", "notes"], key="f_search_col")
            search_val = c6.text_input("Mot-clé", placeholder="Ex: Kolda, MIL, riz…", key="f_search_val")

        # ── Appliquer les filtres ──
        df = query_productions(
            campagne_id  = camp_options.get(camp_sel) if camp_sel != "Toutes" else None,
            culture      = cult_sel if cult_sel != "Toutes" else None,
            type_culture = type_sel if type_sel != "Tous"   else None,
            niveau       = niv_sel  if niv_sel  != "Tous"   else None,
        )
        # Filtre texte libre (côté Python, sur le DataFrame déjà filtré)
        if search_val.strip():
            mask = df[search_col].astype(str).str.contains(
                search_val.strip(), case=False, na=False)
            df = df[mask]

        metric_row([
            ("Enregistrements", f"{len(df):,}"),
            ("Cultures", df["culture"].nunique()),
            ("Localités", df["localite"].nunique()),
            ("Campagnes", df["campagne"].nunique()),
        ])
        st.divider()

        show_ids = cfg("show_ids") == "true"
        cols_edit = (["id"] if show_ids else ["id"]) + [
            "campagne", "localite", "culture", "type_culture",
            "superficie_ha", "rendement_kgha", "production_t", "notes"
        ]
        # id toujours présent pour la sauvegarde mais caché si show_ids=false
        edited = st.data_editor(
            df[cols_edit],
            hide_index=True,
            use_container_width=True,
            disabled=["id", "campagne", "localite", "culture", "type_culture"],
            column_config={
                "id":             st.column_config.NumberColumn("ID", disabled=True),
                "superficie_ha":  st.column_config.NumberColumn("Sup. (Ha)",   format="%.2f"),
                "rendement_kgha": st.column_config.NumberColumn("Rdt (Kg/Ha)", format="%.1f"),
                "production_t":   st.column_config.NumberColumn("Prod. (T)",   format="%.2f"),
                "notes":          st.column_config.TextColumn("Notes"),
            },
            key="editor_prod"
        )
        st.caption(f"{len(df):,} lignes affichées")

        c_save, c_exp1, c_exp2 = st.columns([2, 1, 1])
        with c_save:
            if st.button("💾 Sauvegarder les modifications", type="primary", key="save_prod",
                         use_container_width=True):
                with db_connection() as conn:
                    n = 0
                    for _, row in edited.iterrows():
                        orig_rows = df[df["id"] == row["id"]]
                        if orig_rows.empty:
                            continue
                        orig = orig_rows.iloc[0]
                        if (row["superficie_ha"]  != orig["superficie_ha"] or
                            row["rendement_kgha"] != orig["rendement_kgha"] or
                            row["production_t"]   != orig["production_t"] or
                            str(row.get("notes","")) != str(orig.get("notes",""))):
                            conn.execute("""
                                UPDATE productions
                                SET superficie_ha=?, rendement_kgha=?, production_t=?, notes=?
                                WHERE id=?
                            """, (clean_numeric(row["superficie_ha"]),
                                  clean_numeric(row["rendement_kgha"]),
                                  clean_numeric(row["production_t"]),
                                  row.get("notes") or None,
                                  int(row["id"])))
                            n += 1
                    conn.commit()
                invalidate_cache()
                st.success(f"✅ {n} ligne(s) mise(s) à jour en base.")
        with c_exp1:
            st.download_button("⬇ CSV", df[cols_edit].to_csv(index=False).encode(),
                f"production_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                "text/csv", use_container_width=True, key="csv_prod")
        with c_exp2:
            from io import BytesIO
            _buf = BytesIO(); df[cols_edit].to_excel(_buf, index=False, engine="openpyxl")
            st.download_button("⬇ Excel", _buf.getvalue(),
                f"production_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key="xlsx_prod")

    # ── Importer ──────────────────────────────────────────────
    with sub[1]:
        st.markdown("##### Importer un nouveau fichier de campagne agricole")
        st.caption("Format DAPSA standard — .xlsx avec feuilles CEREALES / CULTURES INDUSTRIELLES / Kolda")

        uploaded = st.file_uploader("Fichier Excel", type=["xlsx", "xls"], key="up_prod")
        c1, c2 = st.columns(2)
        mode = c1.radio("Mode d'import", ["insert_or_ignore", "replace"],
            format_func=lambda x: "Ignorer les doublons" if x == "insert_or_ignore" else "Remplacer les doublons",
            key="import_mode")
        preview_only = c2.checkbox("Aperçu uniquement (ne pas insérer)", key="preview_only")

        if uploaded:
            st.success(f"📁 Fichier : **{uploaded.name}**")
            if st.button("🚀 Lancer l'import", type="primary", key="btn_import_prod"):
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = Path(tmp.name)
                with st.spinner("Traitement en cours…"):
                    stats = importer_fichier_production(
                        tmp_path, mode="preview" if preview_only else mode)
                tmp_path.unlink(missing_ok=True)
                for e in stats["erreurs"][:10]:
                    st.warning(f"⚠ {e}")
                if preview_only:
                    st.info(f"Aperçu : **{stats['insertions']}** enregistrements (campagne {stats['campagne']})")
                    if stats["apercu"]:
                        st.dataframe(pd.DataFrame(stats["apercu"]), use_container_width=True, hide_index=True)
                else:
                    metric_row([
                        ("Campagne", stats["campagne"] or "?"),
                        ("Insertions", stats["insertions"]),
                        ("Doublons ignorés", stats["doublons"]),
                        ("Erreurs", len(stats["erreurs"])),
                    ])
                    if stats["insertions"] > 0:
                        st.success("✅ Import réussi ! Allez dans Consulter & Modifier pour voir les nouvelles données.")
                        invalidate_cache()

    # ── Gérer / Supprimer ─────────────────────────────────────
    with sub[2]:
        st.markdown("##### Supprimer par campagne entière")
        camp_del = st.selectbox("Campagne", list(camp_options.keys()), key="del_camp")
        n_rows   = len(query_productions(campagne_id=camp_options[camp_del]))
        st.info(f"Cette campagne contient **{n_rows}** enregistrements.")

        if st.button("🗑️ Supprimer cette campagne", key="btn_del_camp"):
            st.session_state["_confirm_del_camp"] = True
        if st.session_state.get("_confirm_del_camp"):
            st.error(f"⚠️ Supprimer **{camp_del}** ({n_rows} lignes) ?")
            c1, c2 = st.columns(2)
            if c1.button("✅ Confirmer", type="primary", key="_yes_del_camp"):
                with db_connection() as conn:
                    conn.execute("DELETE FROM productions WHERE campagne_id=?", (camp_options[camp_del],))
                    conn.execute("DELETE FROM campagnes WHERE id=?", (camp_options[camp_del],))
                    conn.commit()
                st.session_state["_confirm_del_camp"] = False
                invalidate_cache(); st.success("✅ Supprimée."); time.sleep(1); st.rerun()
            if c2.button("❌ Annuler", key="_no_del_camp"):
                st.session_state["_confirm_del_camp"] = False; st.rerun()

        st.divider()
        st.markdown("##### Supprimer des lignes individuelles")
        df_sel  = query_productions()
        ids_sel = st.multiselect("Sélectionner des lignes",
            options=df_sel["id"].tolist(),
            format_func=lambda i: (
                f"#{i} — {df_sel[df_sel.id==i].iloc[0]['localite']} / "
                f"{df_sel[df_sel.id==i].iloc[0]['culture']} / "
                f"{df_sel[df_sel.id==i].iloc[0]['campagne']}"),
            key="sel_ids_del")
        if ids_sel:
            if st.button(f"🗑️ Supprimer {len(ids_sel)} ligne(s)", key="btn_del_ids"):
                st.session_state["_confirm_del_ids"] = True
            if st.session_state.get("_confirm_del_ids"):
                st.error(f"Supprimer {len(ids_sel)} ligne(s) ?")
                c1, c2 = st.columns(2)
                if c1.button("✅ Confirmer", type="primary", key="_yes_del_ids"):
                    with db_connection() as conn:
                        conn.executemany("DELETE FROM productions WHERE id=?", [(i,) for i in ids_sel])
                        conn.commit()
                    st.session_state["_confirm_del_ids"] = False
                    invalidate_cache(); st.success(f"✅ {len(ids_sel)} supprimée(s)."); time.sleep(1); st.rerun()
                if c2.button("❌ Annuler", key="_no_del_ids"):
                    st.session_state["_confirm_del_ids"] = False; st.rerun()


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — MAGASINS
# ══════════════════════════════════════════════════════════════

def onglet_magasins():
    sub = st.tabs(["📋 Consulter / Modifier", "➕ Ajouter", "📤 Importer"])

    # ── Consulter / Modifier ──────────────────────────────────
    with sub[0]:
        c1, c2 = st.columns(2)
        dept_opts = ["Tous"] + sorted(query_magasins()["departement"].dropna().unique().tolist())
        dept_sel = c1.selectbox("Département", dept_opts, key="mag_dept")
        etat_sel = c2.selectbox("État", ["Tous", "Bon", "Mauvais", "En construction", "Inconnu"], key="mag_etat")

        df = query_magasins(
            dept = dept_sel if dept_sel != "Tous" else None,
            etat = etat_sel if etat_sel != "Tous" else None,
        )

        metric_row([
            ("Magasins", len(df)),
            ("Capacité totale (T)", f"{df['capacite_t'].sum():,.0f}" if not df.empty else "—"),
            ("État : Bon", int((df["etat"] == "Bon").sum())),
            ("État : Mauvais", int((df["etat"] == "Mauvais").sum())),
        ])
        st.divider()

        edited_mag = st.data_editor(
            df[["id","departement","commune","village","capacite_t","etat","contact","notes"]],
            hide_index=True,
            use_container_width=True,
            disabled=["id"],
            column_config={
                "capacite_t": st.column_config.NumberColumn("Capacité (T)", format="%.0f"),
                "etat": st.column_config.SelectboxColumn("État",
                    options=["Bon","Mauvais","En construction","Inconnu"]),
            },
            key="editor_mag"
        )

        if st.button("💾 Sauvegarder", type="primary", key="save_mag"):
            with db_connection() as conn:
                n = 0
                for _, row in edited_mag.iterrows():
                    orig = df[df["id"] == row["id"]].iloc[0]
                    if any(str(row[c]) != str(orig[c]) for c in
                           ["capacite_t","etat","contact","notes","departement","commune","village"]):
                        conn.execute("""
                            UPDATE magasins SET departement=?, commune=?, village=?,
                            capacite_t=?, etat=?, contact=?, notes=? WHERE id=?
                        """, (row["departement"], row["commune"], row["village"],
                              clean_numeric(row["capacite_t"]), row["etat"],
                              row["contact"], row["notes"], int(row["id"])))
                        n += 1
                conn.commit()
            invalidate_cache()
            st.success(f"✅ {n} magasin(s) mis à jour.")

        st.divider()
        # Suppression
        ids_del = st.multiselect("Sélectionner des magasins à supprimer",
                                 options=df["id"].tolist(),
                                 format_func=lambda i: f"#{i} — {df[df.id==i].iloc[0]['village']} ({df[df.id==i].iloc[0]['commune']})",
                                 key="mag_del_ids")
        if ids_del:
            if st.button(f"🗑️ Supprimer {len(ids_del)} magasin(s)", key="btn_del_mag"):
                st.session_state["_confirm_del_mag"] = True
            if st.session_state.get("_confirm_del_mag"):
                st.error(f"Supprimer {len(ids_del)} magasin(s) ?")
                c1, c2 = st.columns(2)
                if c1.button("✅ Confirmer", type="primary", key="_yes_del_mag"):
                    with db_connection() as conn:
                        conn.executemany("DELETE FROM magasins WHERE id=?",
                                         [(i,) for i in ids_del])
                        conn.commit()
                    st.session_state["_confirm_del_mag"] = False
                    invalidate_cache()
                    st.success("✅ Supprimé.")
                    time.sleep(1); st.rerun()
                if c2.button("❌ Annuler", key="_no_del_mag"):
                    st.session_state["_confirm_del_mag"] = False; st.rerun()

        export_buttons(df, "magasins")

    # ── Ajouter ───────────────────────────────────────────────
    with sub[1]:
        st.markdown("##### Ajouter un nouveau magasin")
        with st.form("form_add_mag"):
            c1, c2, c3 = st.columns(3)
            dept   = c1.text_input("Département *")
            commune = c2.text_input("Commune *")
            village = c3.text_input("Village *")
            c4, c5, c6 = st.columns(3)
            capacite = c4.number_input("Capacité (T)", min_value=0.0, step=10.0)
            etat     = c5.selectbox("État", ["Bon","Mauvais","En construction","Inconnu"])
            contact  = c6.text_input("Contact")
            notes    = st.text_area("Notes", height=80)
            submitted = st.form_submit_button("➕ Ajouter", type="primary")

        if submitted:
            if not (dept and commune and village):
                st.error("⚠️ Département, commune et village sont obligatoires.")
            else:
                with db_connection() as conn:
                    # Tenter de résoudre localite_id
                    row = conn.execute(
                        "SELECT geo_id FROM localites WHERE LOWER(nom) LIKE ? LIMIT 1",
                        (f"%{village.lower()}%",)).fetchone()
                    loc_id = row["geo_id"] if row else None
                    conn.execute("""
                        INSERT INTO magasins
                        (localite_id, departement, commune, village, capacite_t, etat, contact, notes)
                        VALUES (?,?,?,?,?,?,?,?)
                    """, (loc_id, dept, commune, village, capacite or None, etat, contact or None, notes or None))
                    conn.commit()
                invalidate_cache()
                st.success(f"✅ Magasin ajouté : {village} ({commune})")
                st.rerun()

    # ── Importer ──────────────────────────────────────────────
    with sub[2]:
        st.markdown("##### Importer un fichier magasins Excel")
        st.caption("Colonnes attendues : DEPT | COMMUNE | VILLAGE | CAPACITE | ETAT | CONTACTS")
        uploaded_mag = st.file_uploader("Fichier Excel", type=["xlsx","xls"], key="up_mag")
        if uploaded_mag:
            if st.button("🚀 Importer", type="primary", key="btn_imp_mag"):
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    tmp.write(uploaded_mag.getvalue())
                    tmp_path = Path(tmp.name)
                with st.spinner("Import en cours…"):
                    stats = importer_fichier_magasins(tmp_path)
                tmp_path.unlink(missing_ok=True)
                metric_row([("Insertions", stats["insertions"]), ("Erreurs", len(stats["erreurs"]))])
                for e in stats["erreurs"][:5]:
                    st.warning(f"⚠ {e}")
                if stats["insertions"] > 0:
                    st.success(f"✅ {stats['insertions']} magasin(s) importé(s) avec succès.")
                    invalidate_cache()


# ══════════════════════════════════════════════════════════════
# ONGLET 3 — GÉOGRAPHIE
# ══════════════════════════════════════════════════════════════

def onglet_geographie():
    sub = st.tabs(["🌍 Consulter / Modifier", "➕ Ajouter une localité",
                   "📍 Trouver coordonnées", "📤 Importer"])

    # ── Consulter / Modifier ──────────────────────────────────
    with sub[0]:
        type_sel = st.selectbox("Niveau géographique",
                                ["Tous","region","departement","commune","village"],
                                key="geo_type_sel")
        df_geo = query_localites(type_loc=None if type_sel=="Tous" else type_sel)

        metric_row([
            ("Régions",     int((df_geo["type"]=="region").sum())),
            ("Départements",int((df_geo["type"]=="departement").sum())),
            ("Communes",    int((df_geo["type"]=="commune").sum())),
            ("Villages",    int((df_geo["type"]=="village").sum())),
        ])
        st.divider()

        show_ids = cfg("show_ids") == "true"
        cols_geo = (["geo_id"] if show_ids else []) + [
            "nom", "type", "parent_id", "latitude", "longitude",
            "nom_standardise", "abreviation"
        ]
        edited_geo = st.data_editor(
            df_geo[cols_geo],
            hide_index=True,
            use_container_width=True,
            disabled=["geo_id", "type"],
            column_config={
                "latitude":  st.column_config.NumberColumn("Latitude",  format="%.6f"),
                "longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
                "type": st.column_config.TextColumn("Type"),
                "parent_id": st.column_config.TextColumn("Parent ID"),
            },
            key="editor_geo"
        )

        if st.button("💾 Sauvegarder", type="primary", key="save_geo"):
            with db_connection() as conn:
                n = 0
                for _, row in edited_geo.iterrows():
                    orig = df_geo[df_geo["geo_id"]==row["geo_id"]].iloc[0]
                    if any(str(row.get(c, "")) != str(orig.get(c, ""))
                           for c in ["nom","latitude","longitude","nom_standardise","abreviation","parent_id"]):
                        conn.execute("""
                            UPDATE localites SET nom=?, latitude=?, longitude=?,
                            nom_standardise=?, abreviation=? WHERE geo_id=?
                        """, (row["nom"], clean_numeric(row["latitude"]),
                              clean_numeric(row["longitude"]),
                              row.get("nom_standardise"), row.get("abreviation"),
                              row["geo_id"]))
                        n += 1
                conn.commit()
            invalidate_cache()
            st.success(f"✅ {n} localité(s) mise(s) à jour.")

        export_buttons(df_geo, "geographie")

    # ── Ajouter une localité ──────────────────────────────────
    with sub[1]:
        st.markdown("##### Ajouter une nouvelle localité")
        st.caption("Le code géographique est généré automatiquement.")

        with st.form("form_add_geo"):
            c1, c2 = st.columns(2)
            type_loc = c1.selectbox("Type *", ["region","departement","commune","village"])
            nom      = c2.text_input("Nom *")

            # Parent selon le type
            parent_options = {"(aucun)": None}
            parent_type = {"region": None, "departement": "region",
                           "commune": "departement", "village": "commune"}.get(type_loc)
            if parent_type:
                df_parents = query_localites(type_loc=parent_type)
                for _, r in df_parents.iterrows():
                    parent_options[f"{r['nom']} ({r['geo_id']})"] = r["geo_id"]

            parent_label = c1.selectbox("Parent *" if parent_type else "Parent",
                                        list(parent_options.keys()), key="add_geo_parent")
            parent_id    = parent_options[parent_label]
            abrev        = c2.text_input("Abréviation (3 lettres)")

            st.markdown("**Coordonnées** — saisir manuellement ou utiliser l'onglet 📍")
            c3, c4 = st.columns(2)
            lat = c3.number_input("Latitude",  value=12.9033, format="%.6f", key="add_lat")
            lon = c4.number_input("Longitude", value=-14.946, format="%.6f", key="add_lon")

            # Pré-remplir depuis le résultat de géocodage si disponible
            if st.session_state.get("_geo_result"):
                res = st.session_state["_geo_result"]
                st.info(f"📍 Coordonnées du géocodage : {res['lat']:.6f}, {res['lon']:.6f} — {res['label']}")
                if st.form_submit_button("⬆️ Utiliser ces coordonnées"):
                    lat = res["lat"]; lon = res["lon"]

            submitted = st.form_submit_button("➕ Ajouter", type="primary")

        if submitted:
            if not nom:
                st.error("Le nom est obligatoire.")
            elif parent_type and not parent_id:
                st.error(f"Un parent de type '{parent_type}' est obligatoire.")
            else:
                import unicodedata, re
                nom_std = ''.join(c for c in unicodedata.normalize('NFD', nom.lower())
                                  if unicodedata.category(c) != 'Mn')
                nom_std = re.sub(r'[^\w\s]', '', nom_std).strip()

                with db_connection() as conn:
                    new_id = next_geo_id(conn, type_loc)
                    conn.execute("""
                        INSERT INTO localites
                        (geo_id, nom, type, parent_id, latitude, longitude,
                         nom_standardise, abreviation)
                        VALUES (?,?,?,?,?,?,?,?)
                    """, (new_id, nom.strip(), type_loc, parent_id or None,
                          lat or None, lon or None,
                          nom_std, abrev.strip().upper() or None))
                    conn.commit()
                invalidate_cache()
                st.success(f"✅ Localité ajoutée : **{nom}** → ID généré : **{new_id}**")
                if "_geo_result" in st.session_state:
                    del st.session_state["_geo_result"]
                st.rerun()

    # ── Trouver coordonnées ───────────────────────────────────
    with sub[2]:
        st.markdown("##### Trouver des coordonnées géographiques")

        mode_geo = st.radio("Méthode", ["🔎 Recherche Nominatim (OpenStreetMap)",
                                        "📍 Ma position GPS actuelle"],
                            key="geo_mode", horizontal=True)

        if "Nominatim" in mode_geo:
            st.caption("Recherche gratuite via l'API OpenStreetMap — fonctionne sans clé API.")
            query_nom = st.text_input("Nom du lieu", placeholder="Ex: Kolda, Sénégal",
                                     key="nominatim_query")
            if st.button("🔎 Rechercher", key="btn_nominatim") and query_nom:
                import urllib.request, urllib.parse
                url = (f"https://nominatim.openstreetmap.org/search"
                       f"?q={urllib.parse.quote(query_nom)}&format=json&limit=5"
                       f"&countrycodes=sn&accept-language=fr")
                try:
                    req = urllib.request.Request(url,
                        headers={"User-Agent": "KoldaAgriDashboard/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as r:
                        results = json.loads(r.read())
                    if not results:
                        st.warning("Aucun résultat. Essayez avec un nom plus précis.")
                    else:
                        st.session_state["_nominatim_results"] = results
                except Exception as e:
                    st.error(f"Erreur Nominatim : {e}")

            if st.session_state.get("_nominatim_results"):
                results = st.session_state["_nominatim_results"]
                st.markdown("**Résultats :**")
                for i, r in enumerate(results):
                    lat_r = float(r["lat"]); lon_r = float(r["lon"])
                    with st.container():
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"**{r.get('display_name','?')}**  \n"
                                    f"`{lat_r:.6f}, {lon_r:.6f}` — {r.get('type','')}")
                        if c2.button("✅ Utiliser", key=f"use_nom_{i}"):
                            st.session_state["_geo_result"] = {
                                "lat": lat_r, "lon": lon_r,
                                "label": r.get("display_name", "")
                            }
                            del st.session_state["_nominatim_results"]
                            st.success(f"Coordonnées sélectionnées : {lat_r:.6f}, {lon_r:.6f}")
                            st.info("Allez dans l'onglet **➕ Ajouter** pour les utiliser.")

        else:  # GPS
            st.caption("Utilise le GPS de votre appareil — idéal sur mobile lors d'une visite terrain.")
            st.markdown("""
            <div id="gps-container">
              <button onclick="getPosition()" style="
                background:#1a7a2e;color:white;border:none;border-radius:8px;
                padding:10px 20px;cursor:pointer;font-size:14px;">
                📍 Obtenir ma position
              </button>
              <p id="gps-status" style="margin-top:10px;color:#8b949e;font-size:13px;">
                En attente…
              </p>
              <div id="gps-result" style="display:none;background:#1c2330;border:1px solid #2a3441;
                border-radius:8px;padding:12px;margin-top:10px;font-family:monospace;">
              </div>
            </div>
            <script>
            function getPosition() {
              const status = document.getElementById('gps-status');
              status.textContent = '⏳ Localisation en cours…';
              if (!navigator.geolocation) {
                status.textContent = '❌ Géolocalisation non supportée par ce navigateur.';
                return;
              }
              navigator.geolocation.getCurrentPosition(
                function(pos) {
                  const lat = pos.coords.latitude.toFixed(6);
                  const lon = pos.coords.longitude.toFixed(6);
                  const acc = Math.round(pos.coords.accuracy);
                  const res = document.getElementById('gps-result');
                  res.style.display = 'block';
                  res.innerHTML = '<b style="color:#3fb950">✅ Position obtenue</b><br>'
                    + 'Latitude : <b>' + lat + '</b><br>'
                    + 'Longitude : <b>' + lon + '</b><br>'
                    + 'Précision : ±' + acc + ' m<br><br>'
                    + '<small style="color:#8b949e">Copiez ces valeurs dans le formulaire Ajouter.</small>';
                  status.textContent = '';
                },
                function(err) {
                  status.textContent = '❌ ' + err.message;
                },
                {enableHighAccuracy: true, timeout: 10000}
              );
            }
            </script>
            """, unsafe_allow_html=True)

            st.divider()
            st.markdown("**Ou saisir manuellement les coordonnées obtenues :**")
            c1, c2 = st.columns(2)
            lat_m = c1.number_input("Latitude",  format="%.6f", key="manual_lat")
            lon_m = c2.number_input("Longitude", format="%.6f", key="manual_lon")
            if st.button("✅ Utiliser ces coordonnées", key="use_manual_gps"):
                st.session_state["_geo_result"] = {
                    "lat": lat_m, "lon": lon_m, "label": "Saisie manuelle"
                }
                st.success(f"Coordonnées enregistrées : {lat_m:.6f}, {lon_m:.6f}")
                st.info("Allez dans l'onglet **➕ Ajouter** pour les utiliser.")

    # ── Importer ──────────────────────────────────────────────
    with sub[3]:
        st.markdown("##### Importer un fichier géographique Excel")
        st.caption("Colonnes : geo_id | nom | type | parent_id | latitude | longitude | nom_standardise | abreviation")
        uploaded_geo = st.file_uploader("Fichier Excel", type=["xlsx","xls"], key="up_geo")
        if uploaded_geo:
            if st.button("🚀 Importer", type="primary", key="btn_imp_geo"):
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    tmp.write(uploaded_geo.getvalue())
                    tmp_path = Path(tmp.name)
                stats = importer_fichier_geo(tmp_path)
                tmp_path.unlink(missing_ok=True)
                metric_row([("Insertions", stats["insertions"]), ("Erreurs", len(stats["erreurs"]))])
                for e in stats["erreurs"][:5]:
                    st.warning(f"⚠ {e}")
                if stats["insertions"] > 0:
                    st.success(f"✅ {stats['insertions']} localité(s) importée(s) avec succès.")
                    invalidate_cache()


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — QUALITÉ DES DONNÉES
# ══════════════════════════════════════════════════════════════

def onglet_qualite():
    q = query_qualite()

    # Score global
    score_color = "normal" if q["score"] >= 80 else "inverse"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏆 Score qualité", f"{q['score']} / 100")
    c2.metric("Complétude",   f"{q['completude']} %",
              delta=f"{q['completude']-100:.1f}%" if q['completude'] < 100 else "Parfait")
    c3.metric("Cohérence",    f"{q['coherence']} %")
    c4.metric("Total lignes", f"{q['total']:,}")
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Valeurs manquantes — Productions")
        manquants = {
            "Superficie (Ha)":   q["null_sup"],
            "Rendement (Kg/Ha)": q["null_rdt"],
            "Production (T)":    q["null_prod"],
        }
        for label, n in manquants.items():
            pct = round(n / max(q["total"], 1) * 100, 1)
            col_a, col_b = st.columns([3, 1])
            col_a.progress(min(pct / 100, 1.0), text=f"{label}")
            col_b.markdown(f"**{n}** ({pct}%)")

        st.divider()
        st.markdown("#### Magasins sans géolocalisation")
        st.metric("Magasins non résolus", q["mag_sans_geo"])

    with col2:
        st.markdown("#### Anomalies détectées")
        if q["incoherents"] > 0:
            st.error(f"**{q['incoherents']}** ligne(s) — Production ≠ Superficie × Rendement (écart >5%)")
            with db_connection() as conn:
                df_inc = pd.read_sql_query("""
                    SELECT p.id, c.libelle AS campagne, l.nom AS localite,
                           p.culture,
                           ROUND(p.superficie_ha,2) AS superficie_ha,
                           ROUND(p.rendement_kgha,1) AS rendement_kgha,
                           ROUND(p.production_t,2) AS production_t,
                           ROUND(p.superficie_ha * p.rendement_kgha / 1000.0, 2) AS prod_calculee,
                           ROUND(ABS((p.superficie_ha * p.rendement_kgha / 1000.0) - p.production_t)
                                 / p.production_t * 100, 1) AS ecart_pct
                    FROM productions p
                    JOIN campagnes c ON p.campagne_id = c.id
                    JOIN localites l ON p.localite_id = l.geo_id
                    WHERE p.superficie_ha IS NOT NULL AND p.rendement_kgha IS NOT NULL
                      AND p.production_t IS NOT NULL AND p.production_t > 0
                      AND ABS((p.superficie_ha * p.rendement_kgha / 1000.0) - p.production_t)
                          / p.production_t > 0.05
                    ORDER BY ecart_pct DESC
                """, conn)
            st.dataframe(df_inc, hide_index=True, use_container_width=True,
                         column_config={"ecart_pct": st.column_config.NumberColumn("Écart %", format="%.1f")})
        else:
            st.success("✅ Aucune incohérence SUP×RDT vs PROD détectée.")

    st.divider()
    st.markdown("#### Qualité par campagne")
    df_camp = q["par_campagne"].copy()
    df_camp["score"] = (
        (1 - (df_camp["null_sup"] + df_camp["null_rdt"] + df_camp["null_prod"])
         / (df_camp["total"] * 3)) * 100
    ).round(1)
    st.dataframe(
        df_camp.rename(columns={
            "campagne":"Campagne","total":"Lignes",
            "null_sup":"Manq. Sup","null_rdt":"Manq. Rdt",
            "null_prod":"Manq. Prod","score":"Score %"
        }),
        hide_index=True, use_container_width=True,
        column_config={"Score %": st.column_config.ProgressColumn(
            "Score %", min_value=0, max_value=100, format="%.1f%%")}
    )

    st.divider()
    if st.button("🔄 Recalculer les statistiques", key="refresh_qualite"):
        query_qualite.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Données & Admin — Kolda Agri",
        page_icon="🌾",
        layout="wide",
    )

    # Charger la config et l'injecter dans session_state
    if "_config" not in st.session_state:
        st.session_state["_config"] = load_config()

    # ── Lecture config thème ─────────────────────────────────
    primary         = cfg("color_primary",     "#3fb950")
    font            = cfg("font_family",       "IBM Plex Mono, sans-serif").split(",")[0].strip()
    hdr_bg          = cfg("header_bg_color",   "#1c2a1e")
    hdr_border      = cfg("header_border_color","#3fb950")
    hdr_text        = cfg("header_text_color", "#e6edf3")
    tab_active      = cfg("tab_active_color",  "#3fb950")
    tab_hover       = cfg("tab_hover_bg",      "rgba(255,255,255,0.04)")
    subtab_active   = cfg("subtab_active_color","#58a6ff")
    subtab_hover    = cfg("subtab_hover_bg",   "rgba(88,166,255,0.06)")
    body_bg         = cfg("body_bg_color",     "#0d1117")   # <--- NOUVEAU

    # Dériver rgba de tab_active pour le fond léger de l'onglet actif
    def _hex_to_rgba(h, a=0.08):
        h = h.lstrip('#')
        if len(h) == 6:
            r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"
        return f"rgba(63,185,80,{a})"

    tab_active_bg    = _hex_to_rgba(tab_active,    0.07) if tab_active.startswith('#') else "rgba(63,185,80,0.07)"
    subtab_active_bg = _hex_to_rgba(subtab_active, 0.07) if subtab_active.startswith('#') else "rgba(88,166,255,0.07)"

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: '{font}', sans-serif !important; }}

    /* Fond général de l'application */
    .stApp {{
        background-color: {body_bg} !important;
    }}

    /* Supprimer la marge haute de Streamlit */
    .main .block-container {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    header[data-testid="stHeader"] {{ height: 0 !important; }}

    /* Bouton primaire */
    .stButton > button[kind="primary"] {{
        background-color: {primary} !important;
        border-color: {primary} !important;
    }}

    /* ── Onglets principaux — pleine largeur ── */
    [data-baseweb="tab-list"] {{
        gap: 0 !important;
        width: 100% !important;
    }}
    [data-baseweb="tab"] {{
        flex: 1 1 0 !important;
        justify-content: center !important;
        text-align: center !important;
        padding: 12px 4px !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        border-bottom: 2px solid transparent !important;
        transition: background 0.15s, color 0.15s !important;
    }}
    [data-baseweb="tab"]:hover {{
        background: {tab_hover} !important;
    }}
    [data-baseweb="tab"][aria-selected="true"] {{
        border-bottom-color: {tab_active} !important;
        color: {tab_active} !important;
        background: {tab_active_bg} !important;
    }}

    /* ── Sous-onglets (niveau 2) — couleur distincte ── */
    .stTabs .stTabs [data-baseweb="tab-list"] {{
        gap: 0 !important;
    }}
    .stTabs .stTabs [data-baseweb="tab"] {{
        flex: 1 1 0 !important;
        justify-content: center !important;
        font-size: 0.82rem !important;
        padding: 8px 4px !important;
    }}
    .stTabs .stTabs [data-baseweb="tab"]:hover {{
        background: {subtab_hover} !important;
    }}
    .stTabs .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        border-bottom-color: {subtab_active} !important;
        color: {subtab_active} !important;
        background: {subtab_active_bg} !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    # ── En-tête centré ────────────────────────────────────────
    with db_connection() as _conn_hdr:
        _nb_prod   = _conn_hdr.execute("SELECT COUNT(*) FROM productions").fetchone()[0]
        _nb_camp   = _conn_hdr.execute("SELECT COUNT(*) FROM campagnes").fetchone()[0]
        _nb_anomal = _conn_hdr.execute("""
            SELECT COUNT(*) FROM productions
            WHERE superficie_ha IS NOT NULL AND rendement_kgha IS NOT NULL
              AND production_t IS NOT NULL AND production_t > 0
              AND ABS((superficie_ha*rendement_kgha/1000.0)-production_t)/production_t > 0.05
        """).fetchone()[0]

    _chip_rd = "background:rgba(248,81,73,.15);color:#f85149;border:1px solid rgba(248,81,73,.35);border-radius:20px;padding:3px 12px;font-size:.78rem;"
    _chip_cs_a = "background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3);border-radius:20px;padding:3px 12px;font-size:.78rem;"
    _anomal_chip = (
        f"<span style='{_chip_rd}'>⚠ {_nb_anomal} anomalie(s)</span>"
        if _nb_anomal > 0 else
        f"<span style='{_chip_cs_a}'>✓ Aucune anomalie</span>"
    )

    _now     = pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')
    _chip_cs = "background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3);border-radius:20px;padding:3px 12px;font-size:.78rem;"
    _chip_bl = "background:rgba(88,166,255,.1);color:#58a6ff;border:1px solid rgba(88,166,255,.25);border-radius:20px;padding:3px 12px;font-size:.78rem;"
    _chip_gy = "background:rgba(139,148,158,.1);color:#8b949e;border:1px solid rgba(139,148,158,.2);border-radius:20px;padding:3px 12px;font-size:.78rem;"
    _chip_camp  = f"<span style='{_chip_cs}'>● {_nb_camp} campagne(s)</span>"
    _chip_prod  = f"<span style='{_chip_bl}'>📊 {_nb_prod:,} enregistrements</span>"
    _chip_time  = f"<span style='{_chip_gy}'>🕐 {_now}</span>"

    _chips_html = _chip_camp + _chip_prod + _anomal_chip + _chip_time
    st.markdown(f"""
<div style='
    background: {hdr_bg};
    border: 1px solid rgba(255,255,255,0.06);
    border-left: 4px solid {hdr_border};
    border-radius: 0 0 12px 12px;
    padding: 18px 32px 16px;
    margin: -1px 0 20px 0;
'>
  <div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>
    <span style='font-size:1.45rem;line-height:1;'>🌾</span>
    <h1 style='margin:0;font-size:1.45rem;font-weight:700;
               color:{hdr_text};letter-spacing:-.01em;'>
      Données &amp; Administration
    </h1>
  </div>
  <p style='margin:0 0 12px;color:#8b949e;font-size:.83rem;text-align:center;'>
    Région de Kolda — Base SQLite locale &nbsp;·&nbsp;
    <code style='font-size:.74rem;color:#58a6ff;background:rgba(88,166,255,.1);
                 padding:2px 6px;border-radius:4px;'>kolda_agri.db</code>
  </p>
  <div style='display:flex;justify-content:center;gap:8px;flex-wrap:wrap;'>
    {_chips_html}
  </div>
</div>
""", unsafe_allow_html=True)

    # Vérifier que la base existe
    if not DB_PATH.exists():
        st.error("❌ Base de données introuvable. Lancez `python db/bootstrap.py` d'abord.")
        st.code("python db/bootstrap.py --data-dir data")
        return

    # 4 onglets principaux
    tabs = st.tabs(["🌾 Production", "🏪 Magasins", "🗺️ Géographie", "🔍 Qualité des données"])

    with tabs[0]: onglet_production()
    with tabs[1]: onglet_magasins()
    with tabs[2]: onglet_geographie()
    with tabs[3]: onglet_qualite()


if __name__ == "__main__":
    main()