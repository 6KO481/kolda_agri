"""
db/import_excel.py — Import des fichiers Excel DAPSA → SQLite

Gère DEUX formats DAPSA :

  Format A — "Ancien" (2020/2021, 2021/2022)
  ─────────────────────────────────────────────────────────────
  Ligne N-1 : noms de culture (MIL, SORGHO, MAIS…)
  Ligne N   : LOCALITES | SUP | RDT | PROD | SUP | RDT | PROD | …
  Ligne N+1 : (vide/métrique)
  Ligne N+2 : (Ha) | (Kg/Ha) | (T) | (Ha) | (Kg/Ha) | (T) | …
  Données   : à partir de N+3

  Format B — "Nouveau" (2022/2023, 2024/2025)
  ─────────────────────────────────────────────────────────────
  Ligne N-1 : (vide) | MIL | (vide) | (vide) | SORGHO | …
  Ligne N   : Departements | Sup(ha) | Rdt(kg/ha) | Product(T) | Sup(ha) | …
  Données   : à partir de N+1
  Note      : la colonne Product(T) contient des formules Excel
              → on recalcule prod = sup * rdt / 1000
"""

import re
import sqlite3
import pandas as pd
from pathlib import Path
from typing import Optional

from utils import (
    get_connection, DB_PATH,
    clean_numeric, clean_text, classify_culture,
)


# ── Constantes ────────────────────────────────────────────────

LIGNES_A_IGNORER = [
    'resultats', 'ecart', 'moyenne', 'source',
    'sodagri', 'contre-saison', 'amenage', 'nan',
]

CULTURES_CEREALES      = ['MIL', 'SORGHO', 'MAIS', 'RIZ', 'FONIO']
CULTURES_INDUSTRIELLES = ['ARACHIDE', 'ARACHIDE HUILERIE', 'COTON',
                           'NIEBE', 'MANIOC', 'PASTEQUE', 'SESAME']


# ── Extraction des années ─────────────────────────────────────

def extraire_annees(df_raw: pd.DataFrame) -> tuple[int, int]:
    """Cherche '2020/2021' ou '2020-2021' dans les premières lignes."""
    for _, row in df_raw.head(10).iterrows():
        for cell in row:
            if isinstance(cell, str):
                m = re.search(r'(\d{4})[/\-](\d{4})', cell)
                if m:
                    return int(m.group(1)), int(m.group(2))
    raise ValueError("Impossible de détecter les années dans le fichier")


def extraire_annees_depuis_nom(nom_fichier: str) -> tuple[int, int] | None:
    """
    Fallback : extrait les années depuis le nom du fichier.
    Ex. : 'RESULTATS_2022-2023_VF.xlsx' → (2022, 2023)
    """
    m = re.search(r'(\d{4})[_\-](\d{4})', Path(nom_fichier).stem)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


# ── Détection de structure — NOUVEAU et ANCIEN format ────────

def _trouver_groupes_nouveaux(header_line: list, cultures_line: list) -> dict:
    """
    Format B : header_line ressemble à
      [Departements, Sup(ha), Rdt(kg/ha), Product(T), Sup(ha), …]
    Cultures sont dans cultures_line à la même position que le premier Sup.

    Retourne col_map {col_idx: {'culture': ..., 'metrique': 'SUP'|'RDT'|'PROD'}}.
    """
    col_map = {}
    i = 1                           # col 0 = Departements
    while i < len(header_line):
        v = str(header_line[i]).strip() if pd.notna(header_line[i]) else ''
        v_low = v.lower().replace(' ', '')

        if 'sup' in v_low and ('ha' in v_low or v_low == 'sup'):
            sup_col = i

            # Les 2 colonnes suivantes : rdt puis prod
            rdt_col  = i + 1 if i + 1 < len(header_line) else None
            prod_col = i + 2 if i + 2 < len(header_line) else None

            # Vérification optionnelle (peut être Product(T) ou vide)
            if rdt_col is not None:
                vr = str(header_line[rdt_col]).strip().lower() if pd.notna(header_line[rdt_col]) else ''
                if not ('rdt' in vr or 'kg' in vr or 'rend' in vr):
                    rdt_col = None
            if prod_col is not None:
                vp = str(header_line[prod_col]).strip().lower() if pd.notna(header_line[prod_col]) else ''
                if not ('prod' in vp or 'product' in vp):
                    prod_col = None

            # Nom de culture dans la ligne au-dessus, sur l'une des 3 colonnes
            nom = None
            for c in filter(None, [sup_col, rdt_col, prod_col]):
                if c < len(cultures_line) and pd.notna(cultures_line[c]):
                    v2 = str(cultures_line[c]).strip()
                    if v2 not in ('', 'nan', ' ', 'None') and 'TOTAL' not in v2.upper():
                        nom = v2.upper().strip()
                        break

            if nom:
                col_map[sup_col] = {'culture': nom, 'metrique': 'SUP'}
                if rdt_col  is not None:
                    col_map[rdt_col]  = {'culture': nom, 'metrique': 'RDT'}
                if prod_col is not None:
                    col_map[prod_col] = {'culture': nom, 'metrique': 'PROD'}

            # Avancer de 3
            i = (prod_col if prod_col else (rdt_col if rdt_col else sup_col)) + 1
        else:
            i += 1

    return col_map


def _trouver_groupes_anciens(cultures_line: list, unites_line: list) -> dict:
    """
    Format A : unites_line ressemble à
      [None, (Ha), (Kg/Ha), (T), (Ha), (Kg/Ha), (T), …]
    Retourne le même col_map.
    """
    col_map = {}
    i = 1
    while i < len(unites_line):
        u = str(unites_line[i]).strip().upper() if pd.notna(unites_line[i]) else ''
        if u == '(HA)':
            sup_col  = i
            rdt_col  = None
            prod_col = None

            if i + 1 < len(unites_line) and str(unites_line[i+1]).strip().upper() == '(KG/HA)':
                rdt_col = i + 1
            if i + 2 < len(unites_line) and str(unites_line[i+2]).strip().upper() == '(T)':
                prod_col = i + 2

            nom = None
            for c in filter(None, [sup_col, rdt_col, prod_col]):
                if c < len(cultures_line) and pd.notna(cultures_line[c]):
                    v = str(cultures_line[c]).strip()
                    if v not in ('', 'nan', ' ') and 'TOTAL' not in v.upper():
                        nom = v.upper().strip()
                        break

            if nom:
                col_map[sup_col] = {'culture': nom, 'metrique': 'SUP'}
                if rdt_col  is not None:
                    col_map[rdt_col]  = {'culture': nom, 'metrique': 'RDT'}
                if prod_col is not None:
                    col_map[prod_col] = {'culture': nom, 'metrique': 'PROD'}

            i += 3
        else:
            i += 1

    return col_map

def trouver_structure(df_raw: pd.DataFrame) -> tuple[int, dict, str]:
    """
    Détecte le format (A ou B) et retourne (data_start, col_map, niveau).
    niveau : 'region' ou 'localite'
    """
    for i, row in df_raw.iterrows():
        vals_up = [str(v).strip().upper() for v in row if pd.notna(v) and str(v).strip()]

        # ── FORMAT A ─────────────────────────────────────────
        if any(v in ('LOCALITES', 'REGIONS', 'LOCALITE') for v in vals_up
               if v != 'REGION DE KOLDA'):
            header_row = i
            type_b     = 'REGIONS' in vals_up and 'LOCALITES' not in vals_up
            unite_row  = header_row + 2 if type_b else header_row + 1
            data_start = header_row + 3 if type_b else header_row + 2

            cultures_line = df_raw.iloc[header_row - 1].tolist() if header_row > 0 else []
            unites_line   = df_raw.iloc[unite_row].tolist() if unite_row < len(df_raw) else []

            col_map = _trouver_groupes_anciens(cultures_line, unites_line)
            if col_map:
                # Niveau : region si en-tête "REGIONS", sinon localite
                niveau = 'region' if type_b else 'localite'
                return data_start, col_map, niveau
            # Fallback : essayer format B depuis cette position

        # ── FORMAT B ─────────────────────────────────────────
        v0 = str(row.iloc[0]).strip().lower() if pd.notna(row.iloc[0]) else ''
        row_vals = [str(v).strip().lower() for v in row]
        # Accepte aussi les en-têtes "Regions" / "Region" en plus de Departements/Localites
        has_dept  = 'depart' in v0 or 'localit' in v0 or 'region' in v0
        has_sup   = any('sup' in v and 'ha' in v for v in row_vals[1:])
        has_rdt   = any(('rdt' in v or 'kg' in v) for v in row_vals[1:])
        if has_dept and has_sup and has_rdt:
            header_row    = i
            cultures_line = df_raw.iloc[header_row - 1].tolist() if header_row > 0 else []
            header_line   = df_raw.iloc[header_row].tolist()
            col_map       = _trouver_groupes_nouveaux(header_line, cultures_line)
            data_start    = header_row + 1
            if col_map:
                # Niveau déterminé par l'en-tête de la colonne 0 :
                # 'region' seulement si explicitement "REGION" ou "REGIONS",
                # sinon 'localite' (couvre DEPARTEMENTS, LOCALITES, etc.)
                niveau = 'region' if v0.rstrip('s') == 'region' else 'localite'
                return data_start, col_map, niveau

    raise ValueError("Structure non reconnue (ni format A ni format B)")


# ── Validation d'une ligne localité ──────────────────────────

def est_localite_valide(nom) -> bool:
    """Retourne True si la cellule correspond à une localité réelle."""
    if nom is None or str(nom).strip() in ('', 'nan', 'NaN', 'None'):
        return False
    s = str(nom).strip()
    # Formules Excel héritées
    if s.startswith('='):
        return False
    # Numéros seuls
    try:
        float(s)
        return False
    except ValueError:
        pass

    n = s.upper()
    # Mots à ignorer (sans 'region' ni 'total' qui peuvent être dans des noms légitimes)
    for mot in [m.upper() for m in LIGNES_A_IGNORER]:
        if mot in n:
            return False

    # Exclure les sous-totaux et lignes de récapitulatif
    if re.match(r'^TOTAL[\s\(]', n) or re.match(r'^ENSEMBLE', n):
        return False
    # Exclure "REGION (1)", "REGION  (1)" etc.
    if re.match(r'^REGION\s*\(', n):
        return False

    return True


# ── Parser d'une feuille ──────────────────────────────────────

def parser_feuille(
    df_raw: pd.DataFrame,
    annee_debut: int,
    annee_fin: int,
    feuille: str,
) -> list[dict]:
    """
    Parse une feuille DAPSA (format A ou B) et retourne une liste de dicts
    prêts pour SQLite.
    """
    data_start, col_map, niveau = trouver_structure(df_raw)

    # Regrouper par culture
    cultures_cols: dict[str, dict] = {}
    for col_idx, info in col_map.items():
        culture = info['culture']
        if not culture or 'TOTAL' in culture:
            continue
        if culture not in cultures_cols:
            cultures_cols[culture] = {}
        cultures_cols[culture][info['metrique']] = col_idx

    rows = []
    for idx in range(data_start, len(df_raw)):
        row        = df_raw.iloc[idx]
        raw_nom    = row.iloc[0] if len(row) > 0 else None
        nom_loc    = str(raw_nom).strip() if pd.notna(raw_nom) else ''

        if not est_localite_valide(nom_loc):
            continue

        for culture, cols in cultures_cols.items():
            sup  = clean_numeric(row.iloc[cols['SUP']])  if 'SUP'  in cols else None
            rdt  = clean_numeric(row.iloc[cols['RDT']])  if 'RDT'  in cols else None

            # Production : si cellule contient formule ou est vide, on calcule sup * rdt / 1000
            prod_raw  = row.iloc[cols['PROD']] if 'PROD' in cols else None
            prod_val  = clean_numeric(prod_raw)

            is_formula = (
                prod_val is None
                and prod_raw is not None
                and str(prod_raw).strip().startswith('=')
            )

            if is_formula or (prod_val is None and sup is not None and rdt is not None):
                prod = round(sup * rdt / 1000, 4) if (sup and rdt) else None
            else:
                prod = prod_val

            if sup is None and rdt is None and prod is None:
                continue

            rows.append({
                'localite_nom':   nom_loc,
                'annee_debut':    annee_debut,
                'annee_fin':      annee_fin,
                'culture':        culture,
                'type_culture':   classify_culture(culture),
                'superficie_ha':  sup,
                'rendement_kgha': rdt,
                'production_t':   prod,
                'niveau':         niveau,
                'source_feuille': feuille,
            })

    return rows


# ── Résolution localite_id (CORRIGÉE) ────────────────────────

def resoudre_localite_id(
    conn: sqlite3.Connection,
    nom_localite: str,
    type_attendu: str = None,
) -> Optional[str]:
    """
    Trouve le geo_id d'une localité en donnant la priorité aux types non-région.
    Si type_attendu est fourni, on filtre sur ce type.
    """
    nom_clean = clean_text(nom_localite, lower=True, remove_accents=True)
    if not nom_clean:
        return None

    # 1. Exact sur nom_standardise
    if type_attendu:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE nom_standardise = ? AND type = ? LIMIT 1",
            (nom_clean, type_attendu),
        ).fetchone()
        if row:
            return row['geo_id']
    else:
        # Priorité aux types non-région
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE nom_standardise = ? AND type != 'region' LIMIT 1",
            (nom_clean,),
        ).fetchone()
        if row:
            return row['geo_id']
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE nom_standardise = ? LIMIT 1",
            (nom_clean,),
        ).fetchone()
        if row:
            return row['geo_id']

    # 2. LIKE sur nom_standardise
    if type_attendu:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE nom_standardise LIKE ? AND type = ? LIMIT 1",
            (f"%{nom_clean}%", type_attendu),
        ).fetchone()
        if row:
            return row['geo_id']
    else:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE nom_standardise LIKE ? AND type != 'region' LIMIT 1",
            (f"%{nom_clean}%",),
        ).fetchone()
        if row:
            return row['geo_id']
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE nom_standardise LIKE ? LIMIT 1",
            (f"%{nom_clean}%",),
        ).fetchone()
        if row:
            return row['geo_id']

    # 3. Exact sur nom (non standardisé)
    if type_attendu:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE LOWER(nom) = ? AND type = ? LIMIT 1",
            (nom_clean, type_attendu),
        ).fetchone()
        if row:
            return row['geo_id']
    else:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE LOWER(nom) = ? AND type != 'region' LIMIT 1",
            (nom_clean,),
        ).fetchone()
        if row:
            return row['geo_id']
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE LOWER(nom) = ? LIMIT 1",
            (nom_clean,),
        ).fetchone()
        if row:
            return row['geo_id']

    # 4. LIKE sur nom
    if type_attendu:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE LOWER(nom) LIKE ? AND type = ? LIMIT 1",
            (f"%{nom_clean}%", type_attendu),
        ).fetchone()
        if row:
            return row['geo_id']
    else:
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE LOWER(nom) LIKE ? AND type != 'region' LIMIT 1",
            (f"%{nom_clean}%",),
        ).fetchone()
        if row:
            return row['geo_id']
        row = conn.execute(
            "SELECT geo_id FROM localites WHERE LOWER(nom) LIKE ? LIMIT 1",
            (f"%{nom_clean}%",),
        ).fetchone()
        if row:
            return row['geo_id']

    return None


# ── Import principal (production) ────────────────────────────

def importer_fichier_production(
    fichier_excel: str | Path,
    db_path: Path = DB_PATH,
    mode: str = 'insert_or_ignore',
) -> dict:
    """
    Importe un fichier Excel DAPSA dans la base SQLite.

    Args:
        fichier_excel : chemin du fichier .xlsx
        db_path       : chemin de la base .db
        mode          : 'insert_or_ignore' | 'replace' | 'preview'

    Returns:
        dict : insertions, doublons, erreurs, aperçu, campagne
    """
    fichier_excel = Path(fichier_excel)
    stats: dict = {
        'fichier':     fichier_excel.name,
        'insertions':  0,
        'doublons':    0,
        'erreurs':     [],
        'apercu':      [],
        'campagne':    None,
    }

    # 1. Charger toutes les feuilles sans en-tête
    feuilles = pd.read_excel(fichier_excel, sheet_name=None, header=None)

    # 2. Détecter les années
    annee_debut = annee_fin = None
    for nom_f, df_raw in feuilles.items():
        try:
            annee_debut, annee_fin = extraire_annees(df_raw)
            break
        except ValueError:
            continue
    if annee_debut is None:
        fallback = extraire_annees_depuis_nom(str(fichier_excel))
        if fallback:
            annee_debut, annee_fin = fallback
    if annee_debut is None:
        stats['erreurs'].append("Années non détectées dans le fichier")
        return stats

    libelle          = f"{annee_debut}/{annee_fin}"
    stats['campagne'] = libelle

    # 3. Mode aperçu (sans DB)
    if mode == 'preview':
        all_rows = []
        for nom_f, df_raw in feuilles.items():
            try:
                rows = parser_feuille(df_raw, annee_debut, annee_fin, nom_f)
                all_rows.extend(rows)
            except Exception as e:
                stats['erreurs'].append(f"Feuille '{nom_f}': {e}")
        stats['apercu']      = all_rows[:20]
        stats['insertions']  = len(all_rows)
        return stats

    # 4. Import réel
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO campagnes
               (annee_debut, annee_fin, libelle, source_fichier)
               VALUES (?, ?, ?, ?)""",
            (annee_debut, annee_fin, libelle, fichier_excel.name),
        )
        campagne_id = conn.execute(
            "SELECT id FROM campagnes WHERE annee_debut = ? AND annee_fin = ?",
            (annee_debut, annee_fin),
        ).fetchone()['id']

        for nom_feuille, df_raw in feuilles.items():
            try:
                rows = parser_feuille(df_raw, annee_debut, annee_fin, nom_feuille)
            except Exception as e:
                stats['erreurs'].append(f"Feuille '{nom_feuille}': {e}")
                continue

            for row in rows:
                # On transmet type_attendu='region' si le niveau détecté est 'region'
                type_att = 'region' if row['niveau'] == 'region' else None
                localite_id = resoudre_localite_id(conn, row['localite_nom'], type_attendu=type_att)
                if localite_id is None:
                    stats['erreurs'].append(
                        f"Localité non résolue : '{row['localite_nom']}' (niveau={row['niveau']})"
                    )
                    continue

                try:
                    if mode == 'replace':
                        sql = """INSERT OR REPLACE INTO productions
                                 (campagne_id, localite_id, culture, type_culture,
                                  superficie_ha, rendement_kgha, production_t, niveau)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
                    else:
                        sql = """INSERT OR IGNORE INTO productions
                                 (campagne_id, localite_id, culture, type_culture,
                                  superficie_ha, rendement_kgha, production_t, niveau)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""

                    cur = conn.execute(sql, (
                        campagne_id,
                        localite_id,
                        row['culture'],
                        row['type_culture'],
                        row['superficie_ha'],
                        row['rendement_kgha'],
                        row['production_t'],
                        row['niveau'],
                    ))
                    if cur.rowcount > 0:
                        stats['insertions'] += 1
                    else:
                        stats['doublons'] += 1

                except sqlite3.Error as e:
                    stats['erreurs'].append(
                        f"Insert {row['culture']} / {row['localite_nom']}: {e}"
                    )

        conn.commit()

    except Exception as e:
        conn.rollback()
        stats['erreurs'].append(f"Erreur globale: {e}")
        raise
    finally:
        conn.close()

    return stats


# ── Import magasins (CORRIGÉ) ─────────────────────────────────

def importer_fichier_magasins(
    fichier_excel: str | Path,
    db_path: Path = DB_PATH,
) -> dict:
    """
    Importe le fichier BASE_DE_DONNE_MAGASINS.
    Structure : DEPT | COMMUNE | VILLAGE | CAPACITE(T) | ETAT | CONTACTS
    """
    fichier_excel = Path(fichier_excel)
    stats = {'fichier': fichier_excel.name, 'insertions': 0, 'erreurs': []}

    df_raw = pd.read_excel(fichier_excel, sheet_name=0, header=None)

    header_idx = None
    for i, row in df_raw.iterrows():
        vals = [str(v).upper().strip() for v in row if pd.notna(v)]
        if any(v in ('DEPT', 'COMMUNE', 'DEPARTEMENT') for v in vals):
            header_idx = i
            break

    if header_idx is None:
        stats['erreurs'].append("En-tête non trouvé dans le fichier magasins")
        return stats

    df = pd.read_excel(fichier_excel, sheet_name=0, header=header_idx)
    df.columns = [str(c).strip().upper() for c in df.columns]

    col_map = {}
    for col in df.columns:
        cl = col.upper()
        if 'DEPT' in cl or 'DEPART' in cl: col_map['dept']     = col
        elif 'COMMUNE' in cl:              col_map['commune']  = col
        elif 'VILLAGE' in cl:              col_map['village']  = col
        elif 'CAPAC'   in cl:              col_map['capacite'] = col
        elif 'ETAT'    in cl:              col_map['etat']     = col
        elif 'CONTACT' in cl:              col_map['contact']  = col

    conn = get_connection(db_path)
    if 'dept' in col_map:
        df[col_map['dept']] = df[col_map['dept']].ffill()

    try:
        for _, row in df.iterrows():
            dept    = str(row.get(col_map.get('dept',    ''), '')).strip()
            commune = str(row.get(col_map.get('commune', ''), '')).strip()
            village = str(row.get(col_map.get('village', ''), '')).strip()

            if not village or village.upper() in ('NAN', '', 'VILLAGE'):
                continue

            capacite_raw = row.get(col_map.get('capacite', ''), None)
            etat_raw     = str(row.get(col_map.get('etat', ''), '')).strip()
            contact      = str(row.get(col_map.get('contact', ''), '')).strip()

            capacite   = clean_numeric(capacite_raw)
            etat_clean = etat_raw.capitalize() if etat_raw else 'Inconnu'
            if etat_clean not in ('Bon', 'Mauvais', 'En construction'):
                etat_clean = 'Inconnu'

            # Résolution du localite_id en cascade
            localite_id = None
            if village and village.strip():
                localite_id = resoudre_localite_id(conn, village)
            if not localite_id and commune and commune.strip():
                localite_id = resoudre_localite_id(conn, commune)
            if not localite_id and dept and dept.strip():
                # Recherche par nom ou abréviation dans les départements
                dept_clean = clean_text(dept, lower=True, remove_accents=True)
                if dept_clean:
                    row_dept = conn.execute(
                        "SELECT geo_id FROM localites WHERE type='departement' AND (LOWER(nom) = ? OR LOWER(abreviation) = ?) LIMIT 1",
                        (dept_clean, dept_clean)
                    ).fetchone()
                    if row_dept:
                        localite_id = row_dept['geo_id']
                # Fallback : recherche par LIKE
                if not localite_id and dept_clean:
                    row_dept = conn.execute(
                        "SELECT geo_id FROM localites WHERE type='departement' AND LOWER(nom) LIKE ? LIMIT 1",
                        (f"%{dept_clean}%",)
                    ).fetchone()
                    if row_dept:
                        localite_id = row_dept['geo_id']

            if not localite_id:
                stats['erreurs'].append(f"Localité non résolue pour magasin : village={village}, commune={commune}, dept={dept}")
                continue

            conn.execute(
                """INSERT OR IGNORE INTO magasins
                   (localite_id, departement, commune, village, capacite_t, etat, contact)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (localite_id, dept, commune, village, capacite, etat_clean, contact),
            )
            stats['insertions'] += 1

        conn.commit()

    except Exception as e:
        conn.rollback()
        stats['erreurs'].append(str(e))
        raise
    finally:
        conn.close()

    return stats


# ── Import géographie ─────────────────────────────────────────

def importer_fichier_geo(
    fichier_excel: str | Path,
    db_path: Path = DB_PATH,
) -> dict:
    """
    Importe geo_mapping.xlsx dans la table localites.
    Colonnes : geo_id | nom | type | parent_id | latitude | longitude |
               nom_standardise | abreviation
    """
    fichier_excel = Path(fichier_excel)
    stats = {'fichier': fichier_excel.name, 'insertions': 0, 'erreurs': []}

    df = pd.read_excel(fichier_excel)
    df.columns = [str(c).strip().lower() for c in df.columns]

    conn = get_connection(db_path)
    try:
        for type_loc in ['region', 'departement', 'commune', 'village']:
            subset = df[df['type'] == type_loc]
            for _, row in subset.iterrows():
                parent_id = row.get('parent_id')
                if pd.isna(parent_id):
                    parent_id = None

                conn.execute(
                    """INSERT OR REPLACE INTO localites
                       (geo_id, nom, type, parent_id, latitude, longitude,
                        nom_standardise, abreviation)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(row['geo_id']).strip(),
                        str(row['nom']).strip(),
                        str(row['type']).strip(),
                        parent_id,
                        clean_numeric(row.get('latitude')),
                        clean_numeric(row.get('longitude')),
                        str(row.get('nom_standardise', '')).strip() or None,
                        str(row.get('abreviation', '')).strip() or None,
                    ),
                )
                stats['insertions'] += 1

        conn.commit()

    except Exception as e:
        conn.rollback()
        stats['erreurs'].append(str(e))
        raise
    finally:
        conn.close()

    return stats


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, json, sys

    parser = argparse.ArgumentParser(
        description="Importer des fichiers Excel dans Kolda Agri DB"
    )
    parser.add_argument(
        "type", choices=['geo', 'production', 'magasins'],
        help="Type de fichier à importer",
    )
    parser.add_argument("fichier", help="Chemin du fichier Excel")
    parser.add_argument("--db",   default=str(DB_PATH), help="Chemin de la base .db")
    parser.add_argument(
        "--mode", default='insert_or_ignore',
        choices=['insert_or_ignore', 'replace', 'preview'],
    )
    args = parser.parse_args()

    db = Path(args.db)
    f  = Path(args.fichier)

    if not f.exists():
        print(f"✗ Fichier introuvable : {f}", file=sys.stderr)
        sys.exit(1)

    if   args.type == 'geo':        stats = importer_fichier_geo(f, db)
    elif args.type == 'production': stats = importer_fichier_production(f, db, mode=args.mode)
    elif args.type == 'magasins':   stats = importer_fichier_magasins(f, db)

    print(json.dumps(stats, ensure_ascii=False, indent=2))