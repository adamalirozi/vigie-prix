"""Configuration centrale de la Vigie des prix.

Toutes les constantes métier, les seuils, la palette et les libellés
vivent ici : aucune « valeur magique » ne doit apparaître ailleurs.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Chemins
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PRICES_CSV = DATA_DIR / "wfp_food_prices_tcd.csv"
MARKETS_CSV = DATA_DIR / "wfp_markets_tcd.csv"
GEO_PROVINCES = DATA_DIR / "geo" / "tchad_provinces.geojson"
GEO_DEPARTMENTS = DATA_DIR / "geo" / "tchad_departments.geojson"
STYLES_CSS = BASE_DIR / "ui" / "styles.css"
MEB_CSV = DATA_DIR / "meb_composition.csv"
STATE_DIR = Path(os.environ.get("VIGIE_STATE_DIR", DATA_DIR / "state"))  # validations des alertes : créé à l'exécution

# --------------------------------------------------------------------------- #
# Identité
# --------------------------------------------------------------------------- #
APP_TITLE = "Vigie Prix"
APP_SUBTITLE = "Prévisions de prix des céréales à 1, 2 et 3 mois, et alertes MEB"
APP_BRAND = "Vigie Prix · démonstration"
APP_ICON = "🌾"
DATA_SOURCE = "WFP Price Database (HDX)"
DEMO_BANNER = "Démonstration · données publiques WFP · seuils et alertes non validés par le SISAAP"
ORG_NAME = "adamalirozi/vigie-prix"
UNIT = "FCFA/kg"

# --------------------------------------------------------------------------- #
# Produits suivis : libellé affiché → noms dans le fichier WFP (par ordre de priorité).
# Plusieurs noms = séries à fusionner (ex. « Sorghum » et « Sorghum (red) » se recouvrent).
# --------------------------------------------------------------------------- #
COMMODITIES = {
    "Mil": ("Millet",),
    "Sorgho": ("Sorghum", "Sorghum (red)"),
    "Maïs": ("Maize (white)",),
    "Riz importé": ("Rice (imported)",),
}
DEFAULT_COMMODITY = "Mil"

# --------------------------------------------------------------------------- #
# Méthodologie (documentée dans l'expander « Méthodologie »)
# --------------------------------------------------------------------------- #
HISTORY_MONTHS = 24  # mois d'historique affichés
HORIZON = 3  # mois de projection
HORIZONS = (1, 2, 3)  # horizons proposés à l'utilisateur
DEFAULT_HORIZON = 3
MAX_STALE_MONTHS = 3  # au-delà, un prix n'est plus « actuel » (marché ou province sans donnée récente)
# Nettoyage : un relevé est écarté s'il s'éloigne trop de la médiane glissante du même marché
OUTLIER_WINDOW = 7
OUTLIER_LOW, OUTLIER_HIGH = 0.6, 1.6
# Anomalie synchronisée : tous les marchés bougent ensemble puis reviennent (probable artefact de collecte)
SYNC_LOW, SYNC_HIGH, SYNC_MIN_MARKETS = 0.85, 1.18, 15
MASK_SYNC_ANOMALIES = True
MAX_INTERPOLATION_MONTHS = 2  # trous comblés par interpolation dans la série d'un marché
SEASONAL_FIRST_YEAR = 2015  # début de la période servant à estimer la saisonnalité
SEASONAL_OWN_WEIGHT = 0.5  # poids de la saisonnalité propre à la province (le reste = saisonnalité nationale)
SEASONAL_MIN_OBS = 36  # mois minimum pour utiliser la saisonnalité propre d'une province
REFERENCE_YEARS = 5  # moyenne de référence : même mois des 5 années précédentes
REFERENCE_MIN_YEARS = 3  # nombre minimal d'années pour calculer cette moyenne
BACKTEST_MONTHS = 60  # fenêtre pour estimer l'incertitude de la projection
BAND_QUANTILES = (0.10, 0.90)  # intervalle empirique à 80 %

# Scénarios illustratifs : dérive mensuelle ajoutée à la projection saisonnière (à valider avec le SISAAP)
LEAN_SEASON = (6, 7, 8, 9)  # soudure (indicatif) : repère visuel sur les graphiques

SCENARIOS = {
    "Référence": 0.0,
    "Détente": -0.01,
    "Pression accrue": 0.02,
}
DEFAULT_SCENARIO = "Référence"
DEFAULT_PROVINCE = "Kanem"

# Niveaux de vigilance : seuils définis pour 3 mois, proportionnels à l'horizon choisi (×h/3)
ALERT_HIGH = 20.0
ALERT_MID = 10.0
# Écart département / province jugé significatif (en %)
GAP_THRESHOLD = 10.0
# Seuil d'alerte réglable : écart toléré par rapport à la moyenne des 5 dernières années (en %)
SEUIL_MIN, SEUIL_MAX, SEUIL_STEP, SEUIL_DEFAULT = 0, 50, 5, 20

VIGILANCE_ORDER = ("Faible", "Modéré", "Élevé")
# Le niveau n'est jamais porté par la couleur seule (accessibilité)
VIGILANCE_ICON = {"Faible": "○", "Modéré": "●", "Élevé": "▲"}

ALL_PROVINCES = "Toutes les provinces"

# --------------------------------------------------------------------------- #
# Palette (Tableau 10 + neutres) — noms sémantiques
# --------------------------------------------------------------------------- #
COLORS = {
    "primary": "#4e79a7",
    "primary_dark": "#355c7d",
    "positive": "#59a14f",
    "warning": "#f28e2b",
    "danger": "#e15759",
    "neutral": "#aab2bd",
    "ink": "#30343b",
    "muted": "#69717c",
    "line": "#d7dbe0",
    "paper": "#f4f5f7",
    "surface": "#ffffff",
    "highlight": "#2f5597",
}
VIGILANCE_COLORS = {
    "Faible": COLORS["primary"],
    "Modéré": COLORS["warning"],
    "Élevé": COLORS["danger"],
}
# Échelle séquentielle (niveau de prix) : une seule teinte
SEQUENTIAL_SCALE = ["#e6eef5", "#b7cde0", "#86aac9", "#5a86b0", "#355c7d"]
# Échelle divergente (écart), centrée sur 0 : bleu = plus bas, rouge = plus haut
DIVERGING_SCALE = [[0.0, COLORS["primary"]], [0.5, COLORS["paper"]], [1.0, COLORS["danger"]]]

# --------------------------------------------------------------------------- #
# Carte
# --------------------------------------------------------------------------- #
MAP_STYLE = "carto-positron"
MAP_STYLE_OFFLINE = "white-bg"  # sans fond de carte : fonctionne sans connexion
GEO_SIMPLIFY_TOLERANCE = 0.004  # degrés (≈ 450 m) : allège le GeoJSON sans effet visible
MAP_HEIGHT_PROVINCES = 520
MAP_HEIGHT_DEPARTMENTS = 540
FALLBACK_CENTER = {"lat": 13.0, "lon": 18.5}

# --------------------------------------------------------------------------- #
# MEB (composante céréales) — composition dans data/meb_composition.csv
# --------------------------------------------------------------------------- #
HOUSEHOLD_SIZE = 6  # personnes par ménage (à confirmer avec le Cluster)
DAYS_PER_MONTH = 30
MEB_SEUIL_MIN, MEB_SEUIL_MAX, MEB_SEUIL_STEP, MEB_SEUIL_DEFAULT = 8_000, 30_000, 500, 15_000  # FCFA/ménage/mois

# --------------------------------------------------------------------------- #
# Évaluation des prévisions (rétro-test hors échantillon)
# --------------------------------------------------------------------------- #
BACKTEST_TEST_MONTHS = 54  # période de test (les mois précédents servent à estimer la saisonnalité)
BACKTEST_RISE = 10.0  # une « hausse importante » = +10 % ou plus à l'horizon considéré
BACKTEST_SIGNAL = 5.0  # la méthode « signale » une hausse si elle en prévoit au moins +5 %
WEEKS_PER_MONTH = 4.35

# --------------------------------------------------------------------------- #
# Alertes
# --------------------------------------------------------------------------- #
ROLES = ("Analyste SISAAP", "Lecteur")
# Démonstration publique : chaque visiteur a ses propres validations (aucun visiteur n'écrase celles d'un autre).
# Mettre VIGIE_ISOLATE_SESSIONS=0 pour un pilote réel où les analystes partagent un même état (avec authentification).
ISOLATE_SESSIONS = os.environ.get("VIGIE_ISOLATE_SESSIONS", "1") != "0"
ALERT_STATUSES = ("À valider", "Validée", "Suspendue", "Rejetée")
CONFIDENCE_LEVELS = ("Élevée", "Moyenne", "Faible")
RELIABILITY_GOOD, RELIABILITY_MEDIUM = 80.0, 50.0  # complétude (%) sur 24 mois : bonne ≥ 80, moyenne ≥ 50
PILOT_MARKETS_N = 15

# --------------------------------------------------------------------------- #
# Relecture (replay) : épisodes d'illustration, vérifiés par les tests
# --------------------------------------------------------------------------- #
REPLAY_MONTHS = 60  # profondeur de la relecture
REPLAY_EPISODES = [
    {
        "titre": "Soudure 2024 · mil, Hadjer-Lamis",
        "commodity": "Mil", "province": "Hadjer-Lamis", "as_of": "2024-03",
        "note": "Alerte de prix dès M+1, puis « hausse rapide » à M+2 ; la hausse constatée dépasse nettement la projection.",
    },
    {
        "titre": "Soudure 2024 · mil, Kanem (exemple du dossier)",
        "commodity": "Mil", "province": "Kanem", "as_of": "2024-03",
        "note": "Le prix est déjà bien au-dessus de la moyenne 5 ans : l'alerte part à M+1, mais l'ampleur de la hausse est sous-estimée.",
    },
    {
        "titre": "Soudure 2024 · sorgho, Wadi Fira",
        "commodity": "Sorgho", "province": "Wadi Fira", "as_of": "2024-04",
        "note": "Alerte de prix à M+1 ; la hausse constatée à 3 mois est très supérieure à la projection saisonnière.",
    },
]  # épisodes où la méthode a alerté ; la page « Fiabilité » montre les performances moyennes, y compris les hausses manquées
