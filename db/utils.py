"""
db/utils.py — Utilitaires partagés pour la base SQLite
"""

import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "kolda_agri.db"

# ── Connexion ─────────────────────────────────────────────────

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Retourne une connexion SQLite brute (à fermer manuellement)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_connection(db_path: Path = DB_PATH):
    """
    Context manager qui ouvre, yield, commit et FERME la connexion.
    À utiliser partout avec `with db_connection() as conn:`.

    sqlite3.Connection ne ferme PAS la connexion dans son __exit__
    (il fait seulement commit/rollback) → utiliser ce wrapper à la place.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Nettoyage des valeurs ─────────────────────────────────────

def clean_numeric(val) -> float | None:
    """
    Convertit une valeur en float en gérant les cas ambigus.
    '50 T', '50T', '50 t', '1 200,5', '1200.5' → float
    """
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', 'nan', 'NaN', 'None', '-', '—'):
        return None
    # Supprimer unités (T, t, Ha, ha, kg, Kg...)
    s = re.sub(r'(?i)\s*(T|Ha|kg|Kg|tonnes?|hectares?)\s*$', '', s)
    # Normaliser séparateurs : '1 200,5' ou '1.200,5' → '1200.5'
    s = s.replace(' ', '').replace('\u00a0', '')
    # Si virgule décimale ET point milliers : '1.200,5' → '1200.5'
    if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', s):
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def clean_text(val, lower: bool = True, remove_accents: bool = True) -> str | None:
    """Normalise un texte : strip, minuscule, sans accents."""
    if val is None or str(val).strip() in ('', 'nan', 'NaN', 'None'):
        return None
    s = str(val).strip()
    if lower:
        s = s.lower()
    if remove_accents:
        s = ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )
    return s


def classify_culture(nom: str) -> str:
    """Retourne le type de culture depuis son nom."""
    if not nom:
        return 'autres'
    n = nom.lower()
    mapping = {
        'cereales':      ['mil', 'sorgho', 'riz', 'mais', 'maïs', 'ble', 'orge', 'fonio'],
        'oleagineux':    ['arachide', 'soja', 'tournesol', 'sesame', 'coton'],
        'tubercules':    ['manioc', 'patate', 'igname', 'taro'],
        'legumineuses':  ['niebe', 'niébé', 'haricot', 'pois', 'lentille'],
        'maraîchers':    ['tomate', 'oignon', 'chou', 'carotte', 'laitue', 'pasteque', 'pastèque'],
        'fruitiers':     ['mangue', 'banane', 'orange', 'citron', 'papaye'],
    }
    for type_cult, mots in mapping.items():
        if any(m in n for m in mots):
            return type_cult
    return 'autres'


# ── Auto-incrémentation geo_id ────────────────────────────────

_GEO_PREFIX = {
    'region':      ('R', 2),
    'departement': ('D', 3),
    'commune':     ('C', 3),
    'village':     ('V', 3),
}

def next_geo_id(conn: sqlite3.Connection, type_loc: str) -> str:
    """
    Génère le prochain geo_id pour un type donné.
    Ex : type='commune' → 'C035' si le dernier est 'C034'
    """
    prefix, width = _GEO_PREFIX[type_loc]
    row = conn.execute(
        "SELECT geo_id FROM localites WHERE type = ? ORDER BY geo_id DESC LIMIT 1",
        (type_loc,)
    ).fetchone()
    if row:
        num = int(row['geo_id'][len(prefix):]) + 1
    else:
        num = 1
    return f"{prefix}{str(num).zfill(width)}"


# ── Configuration ─────────────────────────────────────────────

def get_config(conn: sqlite3.Connection) -> dict:
    """Retourne toute la config active sous forme de dict {cle: valeur}."""
    rows = conn.execute("SELECT cle, valeur FROM configuration").fetchall()
    return {r['cle']: r['valeur'] for r in rows}


def set_config(conn: sqlite3.Connection, cle: str, valeur: str) -> None:
    """Met à jour une valeur de config (ne touche jamais valeur_defaut)."""
    conn.execute(
        "UPDATE configuration SET valeur = ? WHERE cle = ?",
        (valeur, cle)
    )
    conn.commit()


def reset_config(conn: sqlite3.Connection, cle: str = None) -> None:
    """
    Remet valeur = valeur_defaut.
    Si cle est None, remet TOUTE la config aux valeurs par défaut.
    """
    if cle:
        conn.execute(
            "UPDATE configuration SET valeur = valeur_defaut WHERE cle = ?",
            (cle,)
        )
    else:
        conn.execute("UPDATE configuration SET valeur = valeur_defaut")
    conn.commit()
