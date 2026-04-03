-- ============================================================
-- SCHEMA SQLite — Kolda Agri Dashboard (sans API)
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ── 1. LOCALITES ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS localites (
    geo_id          TEXT PRIMARY KEY,
    nom             TEXT NOT NULL,
    type            TEXT NOT NULL CHECK(type IN ('region','departement','commune','village')),
    parent_id       TEXT REFERENCES localites(geo_id) ON DELETE RESTRICT,
    latitude        REAL,
    longitude       REAL,
    nom_standardise TEXT,
    abreviation     TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_localites_type     ON localites(type);
CREATE INDEX IF NOT EXISTS idx_localites_parent   ON localites(parent_id);
CREATE INDEX IF NOT EXISTS idx_localites_nom_std  ON localites(nom_standardise);

-- ── 2. CAMPAGNES ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campagnes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    annee_debut     INTEGER NOT NULL,
    annee_fin       INTEGER NOT NULL,
    libelle         TEXT NOT NULL,
    source_fichier  TEXT,
    date_import     TEXT DEFAULT (datetime('now')),
    UNIQUE(annee_debut, annee_fin)
);

-- ── 3. PRODUCTIONS ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campagne_id     INTEGER NOT NULL REFERENCES campagnes(id) ON DELETE CASCADE,
    localite_id     TEXT    NOT NULL REFERENCES localites(geo_id) ON DELETE RESTRICT,
    culture         TEXT    NOT NULL,
    type_culture    TEXT    CHECK(type_culture IN (
                        'cereales','oleagineux','tubercules',
                        'legumineuses','maraîchers','fruitiers','autres'
                    )),
    superficie_ha   REAL,
    rendement_kgha  REAL,
    production_t    REAL,
    niveau          TEXT    CHECK(niveau IN ('localite','departement','region')),
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(campagne_id, localite_id, culture)
);

CREATE INDEX IF NOT EXISTS idx_prod_campagne  ON productions(campagne_id);
CREATE INDEX IF NOT EXISTS idx_prod_localite  ON productions(localite_id);
CREATE INDEX IF NOT EXISTS idx_prod_culture   ON productions(culture);
CREATE INDEX IF NOT EXISTS idx_prod_type      ON productions(type_culture);

-- ── 4. MAGASINS ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS magasins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    localite_id     TEXT    REFERENCES localites(geo_id) ON DELETE SET NULL,
    departement     TEXT,
    commune         TEXT,
    village         TEXT,
    capacite_t      REAL,
    etat            TEXT    CHECK(etat IN ('Bon','Mauvais','En construction','Inconnu')),
    contact         TEXT,
    latitude        REAL,
    longitude       REAL,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_magasins_localite ON magasins(localite_id);

-- ── 5. CONFIGURATION ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS configuration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cle             TEXT    NOT NULL,
    valeur          TEXT    NOT NULL,
    valeur_defaut   TEXT    NOT NULL,
    categorie       TEXT    NOT NULL CHECK(categorie IN (
                        'theme','typographie','couleurs','affichage','carte'
                    )),
    label           TEXT    NOT NULL,
    description     TEXT,
    type_valeur     TEXT    CHECK(type_valeur IN (
                        'color','font','select','number',
                        'boolean','text','range'
                    )),
    options         TEXT,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(cle)
);

-- ── 6. TRIGGERS updated_at ───────────────────────────────────
CREATE TRIGGER IF NOT EXISTS trg_localites_upd
    AFTER UPDATE ON localites
    BEGIN UPDATE localites SET updated_at = datetime('now') WHERE geo_id = NEW.geo_id; END;

CREATE TRIGGER IF NOT EXISTS trg_productions_upd
    AFTER UPDATE ON productions
    BEGIN UPDATE productions SET updated_at = datetime('now') WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_magasins_upd
    AFTER UPDATE ON magasins
    BEGIN UPDATE magasins SET updated_at = datetime('now') WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_config_upd
    AFTER UPDATE ON configuration
    BEGIN UPDATE configuration SET updated_at = datetime('now') WHERE id = NEW.id; END;

-- ── 7. CONFIGURATION PAR DÉFAUT ──────────────────────────────
INSERT OR IGNORE INTO configuration (cle, valeur, valeur_defaut, categorie, label, description, type_valeur, options) VALUES

-- Thème général
('theme_mode',        'dark',          'dark',          'theme',       'Mode d''affichage',    'Thème clair ou sombre',              'select',  '["dark","light"]'),
('theme_accent',      '#3fb950',       '#3fb950',       'theme',       'Couleur d''accentuation','Couleur principale des éléments actifs','color', NULL),

-- Couleurs
('color_primary',     '#3fb950',       '#3fb950',       'couleurs',    'Couleur primaire',     'Boutons, liens, actif',              'color',   NULL),
('color_secondary',   '#58a6ff',       '#58a6ff',       'couleurs',    'Couleur secondaire',   'Info, graphiques secondaires',       'color',   NULL),
('color_danger',      '#f85149',       '#f85149',       'couleurs',    'Couleur danger',       'Erreurs, suppressions',              'color',   NULL),
('color_warning',     '#d29922',       '#d29922',       'couleurs',    'Couleur avertissement','Alertes, valeurs à vérifier',        'color',   NULL),
('color_success',     '#3fb950',       '#3fb950',       'couleurs',    'Couleur succès',       'Validations, données correctes',     'color',   NULL),
('color_cereales',    '#3fb950',       '#3fb950',       'couleurs',    'Couleur céréales',     'Graphiques — cultures céréalières',  'color',   NULL),
('color_industriel',  '#d29922',       '#d29922',       'couleurs',    'Couleur industrielles','Graphiques — cultures industrielles','color',   NULL),
('color_autres',      '#58a6ff',       '#58a6ff',       'couleurs',    'Couleur autres',       'Graphiques — autres cultures',       'color',   NULL),

-- Typographie
('font_family',       'IBM Plex Mono, Sora, sans-serif', 'IBM Plex Mono, Sora, sans-serif',
                                                         'typographie', 'Police principale',    'Police du dashboard',                'select',
                      '["IBM Plex Mono, Sora, sans-serif","Inter, sans-serif","DM Sans, sans-serif","Roboto Mono, monospace","Lato, sans-serif"]'),
('font_size_base',    '14',            '14',            'typographie', 'Taille de base (px)',  'Taille du texte courant',            'range',   '{"min":11,"max":18}'),

-- Affichage
('table_rows_per_page','25',           '25',            'affichage',   'Lignes par page',      'Pagination des tableaux',            'select',  '["10","25","50","100"]'),
('show_ids',          'false',         'false',         'affichage',   'Afficher les IDs',     'Afficher geo_id dans les tableaux',  'boolean', NULL),
('date_format',       'DD/MM/YYYY',    'DD/MM/YYYY',    'affichage',   'Format de date',       NULL,                                 'select',  '["DD/MM/YYYY","YYYY-MM-DD","MM/DD/YYYY"]'),
('unite_superficie',  'Ha',            'Ha',            'affichage',   'Unité superficie',     NULL,                                 'select',  '["Ha","m²","km²"]'),
('unite_production',  'Tonnes',        'Tonnes',        'affichage',   'Unité production',     NULL,                                 'select',  '["Tonnes","kg","Quintaux"]'),

-- Carte
('carte_zoom_defaut', '9',             '9',             'carte',       'Zoom carte par défaut','Niveau de zoom initial',             'range',   '{"min":5,"max":15}'),
('carte_lat_defaut',  '12.9033',       '12.9033',       'carte',       'Latitude centre carte','Centre de la carte — Kolda',         'number',  NULL),
('carte_lon_defaut',  '-14.946',       '-14.946',       'carte',       'Longitude centre carte','Centre de la carte — Kolda',        'number',  NULL),
('carte_style',       'OpenStreetMap', 'OpenStreetMap', 'carte',       'Style de fond de carte',NULL,                                'select',  '["OpenStreetMap","CartoDB positron","CartoDB dark_matter","Stamen Terrain"]'),

-- Ajout : couleur de fond générale
('body_bg_color',     '#0d1117',       '#0d1117',       'theme',       'Couleur de fond générale', 'Arrière‑plan de toute l''application', 'color', NULL),

-- Thème onglets et bandeau
('header_bg_color',     '#1c2a1e',       '#1c2a1e',       'theme', 'Fond du bandeau titre',      'Couleur de fond de la bande titre de chaque page',          'color', NULL),
('header_border_color', '#3fb950',       '#3fb950',       'theme', 'Bordure gauche du bandeau',  'Couleur de la bordure gauche du bandeau titre',             'color', NULL),
('header_text_color',   '#e6edf3',       '#e6edf3',       'theme', 'Texte du bandeau titre',     'Couleur du titre dans le bandeau',                         'color', NULL),
('tab_active_color',    '#3fb950',       '#3fb950',       'theme', 'Couleur onglet actif',       'Soulignement et texte de l''onglet principal actif',        'color', NULL),
('tab_hover_bg',        'rgba(255,255,255,0.04)',     'rgba(255,255,255,0.04)',     'theme', 'Fond onglet au survol',      'Fond quand on survole un onglet principal',                'color', NULL),
('subtab_active_color', '#58a6ff',       '#58a6ff',       'theme', 'Couleur sous-onglet actif',  'Soulignement et texte du sous-onglet actif',                'color', NULL),
('subtab_hover_bg',     'rgba(88,166,255,0.06)',      'rgba(88,166,255,0.06)',      'theme', 'Fond sous-onglet au survol', 'Fond quand on survole un sous-onglet',                     'color', NULL);