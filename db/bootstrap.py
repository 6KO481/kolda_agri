"""
db/bootstrap.py — Script one-shot pour initialiser la base et importer
                   tous les fichiers Excel existants.

Usage :
    python db/bootstrap.py
    python db/bootstrap.py --data-dir /chemin/vers/excels
    python db/bootstrap.py --force      # recrée la base depuis zéro
"""

import argparse
import sys
from pathlib import Path

# Ajouter le dossier db/ au path
sys.path.insert(0, str(Path(__file__).parent))

from init_db import init_db
from import_excel import (
    importer_fichier_geo,
    importer_fichier_production,
    importer_fichier_magasins,
)
from utils import DB_PATH


def bootstrap(data_dir: Path, force: bool = False):
    print("=" * 60)
    print("  KOLDA AGRI — Initialisation de la base de données")
    print("=" * 60)

    # 1. Créer la base
    print("\n[1/4] Création du schéma SQLite...")
    init_db(DB_PATH, force=force)

    # 2. Importer la géographie
    print("\n[2/4] Import du référentiel géographique...")
    geo_candidates = [
        data_dir / "geo_mapping.xlsx",
        data_dir / "geo_mapping.xls",
    ]
    geo_file = next((f for f in geo_candidates if f.exists()), None)

    if geo_file:
        stats = importer_fichier_geo(geo_file)
        _afficher_stats("Géographie", stats)
    else:
        print(f"  ⚠ Fichier géo non trouvé dans {data_dir}")
        print("    Attendu : geo_mapping.xlsx")

    # 3. Importer les magasins
    print("\n[3/4] Import des magasins...")
    mag_candidates = list(data_dir.glob("*MAGASIN*.xlsx")) + \
                     list(data_dir.glob("*magasin*.xlsx")) + \
                     list(data_dir.glob("*STOCKAGE*.xlsx"))

    if mag_candidates:
        stats = importer_fichier_magasins(mag_candidates[0])
        _afficher_stats(f"Magasins ({mag_candidates[0].name})", stats)
    else:
        print(f"  ⚠ Fichier magasins non trouvé dans {data_dir}")

    # 4. Importer les fichiers de production (toutes les années)
    print("\n[4/4] Import des campagnes agricoles...")

    # Patterns courants des fichiers DAPSA
    prod_files = (
        list(data_dir.glob("RESULTATS*.xlsx")) +
        list(data_dir.glob("Résultats*.xlsx")) +
        list(data_dir.glob("resultats*.xlsx")) +
        list(data_dir.glob("*campagne*.xlsx")) +
        list(data_dir.glob("*CA_20*.xlsx"))
    )
    # Dédoublonner
    prod_files = list(dict.fromkeys(prod_files))

    if not prod_files:
        print(f"  ⚠ Aucun fichier de production trouvé dans {data_dir}")
    else:
        for f in prod_files:
            stats = importer_fichier_production(f, mode='insert_or_ignore')
            _afficher_stats(f"Production ({f.name})", stats)

    print("\n" + "=" * 60)
    print("  Terminé !")
    print(f"  Base : {DB_PATH}")
    print("=" * 60)


def _afficher_stats(label: str, stats: dict):
    print(f"\n  ▶ {label}")
    print(f"    Insertions : {stats.get('insertions', 0)}")
    print(f"    Doublons   : {stats.get('doublons', 0)}")
    if stats.get('erreurs'):
        for e in stats['erreurs'][:5]:   # Limiter à 5 erreurs affichées
            print(f"    ✗ {e}")
        if len(stats['erreurs']) > 5:
            print(f"    ... et {len(stats['erreurs']) - 5} autre(s) erreur(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent.parent / "data"),
        help="Dossier contenant les fichiers Excel (défaut: ./data)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Supprimer et recréer la base (ATTENTION : efface tout)"
    )
    args = parser.parse_args()

    bootstrap(Path(args.data_dir), force=args.force)
