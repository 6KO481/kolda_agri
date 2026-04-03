"""
db/init_db.py — Crée la base SQLite et applique le schéma
Usage : python db/init_db.py
"""

import sqlite3
from pathlib import Path
from utils import get_connection, DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: Path = DB_PATH, force: bool = False) -> bool:
    """
    Crée la base de données et applique schema.sql.

    Args:
        db_path : chemin du fichier .db
        force   : si True, supprime et recrée la base

    Returns:
        True si succès
    """
    if force and db_path.exists():
        db_path.unlink()
        print(f"Base existante supprimée : {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_PATH.read_text(encoding='utf-8')

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        print(f"✓ Base créée : {db_path}")

        # Vérification rapide des tables
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print(f"  Tables : {[t[0] for t in tables]}")

        # Vérification des configs insérées
        nb_config = conn.execute("SELECT COUNT(*) FROM configuration").fetchone()[0]
        print(f"  Configuration : {nb_config} paramètres chargés")

        return True
    except Exception as e:
        print(f"✗ Erreur init_db : {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialiser la base Kolda Agri")
    parser.add_argument("--force", action="store_true",
                        help="Supprimer et recréer la base")
    parser.add_argument("--db", default=str(DB_PATH),
                        help="Chemin du fichier .db")
    args = parser.parse_args()
    init_db(Path(args.db), force=args.force)
