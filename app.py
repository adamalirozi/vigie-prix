"""Vigie Prix — démonstration (MVP) — point d'entrée Streamlit.

Ce fichier ne contient que la mise en page, les filtres et le câblage des interactions.
Données → services/, graphiques → ui/charts.py, pages → ui/views/.

Lancer :  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config as cfg
from services import cached
from services.geo import GeoError
from ui import components as ui
from ui.context import Ctx
from ui.formatting import month_label_long
from ui.views import alerts, bulletin, departments, meb, provinces, reliability

st.set_page_config(
    page_title=f"{cfg.APP_TITLE} | démonstration",
    page_icon=cfg.APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)
ui.inject_css()

VIEWS = ("Provinces", "Départements", "MEB", "Alertes", "Al Aswak", "Fiabilité & données")
PROVINCE_VIEWS = ("Provinces", "MEB", "Al Aswak")
SEUIL_VIEWS = ("Provinces", "Alertes", "Al Aswak")
MEB_VIEWS = ("MEB", "Alertes", "Al Aswak")

# --------------------------------------------------------------------------- #
# Chargement (erreurs de données → message clair, pas de trace Python)
# --------------------------------------------------------------------------- #
try:
    geo = cached.get_geo()
    dk = cached.data_version()
except (GeoError, FileNotFoundError) as exc:
    st.error(f"Impossible de charger les données : {exc}")
    st.stop()

PROVINCES = sorted(geo.provinces["Province"], key=str.casefold)
DEFAULTS = {
    "view": VIEWS[0], "commodity": cfg.DEFAULT_COMMODITY, "scenario": cfg.DEFAULT_SCENARIO,
    "horizon": cfg.DEFAULT_HORIZON, "province": cfg.DEFAULT_PROVINCE, "seuil": cfg.SEUIL_DEFAULT,
    "meb_seuil": cfg.MEB_SEUIL_DEFAULT, "as_of": "", "episode": None, "role": cfg.ROLES[0], "offline": False,
    "map_metric": "Prix projeté", "show_markets": True, "show_markets_dept": True, "dept_scope": cfg.ALL_PROVINCES,
}
for key, default in DEFAULTS.items():
    st.session_state.setdefault(key, default)
    # Streamlit supprime l'état d'un widget non affiché dans l'exécution courante : on le réaffecte pour le conserver
    st.session_state[key] = st.session_state[key]


# --------------------------------------------------------------------------- #
# Callbacks (exécutés AVANT le rerun du script)
# --------------------------------------------------------------------------- #
def _clicked_location(widget_key: str) -> str | None:
    """Identifiant de l'entité cliquée sur une carte Plotly (ou None)."""
    state = st.session_state.get(widget_key)
    try:
        points = state["selection"]["points"]
    except (KeyError, TypeError):
        return None
    return points[0].get("location") if points else None  # un clic sur un marché n'a pas de « location »


def on_province_click() -> None:
    names = dict(zip(geo.provinces["Code_ID"], geo.provinces["Province"], strict=True))
    name = names.get(_clicked_location("map_provinces"))
    if name:
        st.session_state["province"] = name


def on_department_click() -> None:
    location = _clicked_location("map_departments")
    if location in set(geo.departments["Code_ID"]):
        st.session_state["dept_sel"] = location


def go_to_departments() -> None:
    """Exploration : province sélectionnée → ses départements."""
    st.session_state["dept_scope"] = st.session_state["province"]
    st.session_state["view"] = "Départements"


def apply_episode() -> None:
    """Charge un épisode d'illustration : produit, province, date de prévision, horizon et scénario."""
    i = st.session_state.get("episode")
    if i is None:
        return
    ep = cfg.REPLAY_EPISODES[i]
    st.session_state.update(commodity=ep["commodity"], province=ep["province"], as_of=ep["as_of"],
                            view="Provinces", scenario=cfg.DEFAULT_SCENARIO, horizon=cfg.DEFAULT_HORIZON)
    st.session_state["episode"] = None


# --------------------------------------------------------------------------- #
# En-tête
# --------------------------------------------------------------------------- #
commodity = st.session_state.get("commodity") or cfg.DEFAULT_COMMODITY
header_model = cached.get_model(commodity, st.session_state["as_of"], dk)
ui.render_header(header_model)
if header_model.is_replay:
    st.markdown(
        f'<div class="replay-banner"><b>Mode relecture</b> : l\'outil est montré tel qu\'il aurait fonctionné en '
        f"{month_label_long(header_model.last_obs)}, avec les seules données disponibles à cette date. "
        f"Les prix réalisés ensuite (jusqu'en {month_label_long(header_model.data_last_obs)}) servent à vérifier "
        "les prévisions et les alertes.</div>", unsafe_allow_html=True)

with st.expander("Parcours de démonstration"):
    st.markdown(
        """
1. **Situation** : onglet *Provinces*, bouton d'horizon **M+1 / M+2 / M+3** ; cliquez une province sur la carte.
2. **« Agir avant la hausse »** : *Épisode d'illustration* → « Soudure 2024 · mil, Hadjer-Lamis ». La courbe verte
   montre ce qui s'est réellement passé après la prévision ; l'onglet *Alertes* indique quelles alertes se sont
   confirmées.
3. **Validation** : profil *Analyste SISAAP* → onglet *Alertes* → valider une alerte → message prêt pour le Cluster.
4. **MEB** : coût de la ration céréalière par province, seuil réglable (non validé).
5. **Al Aswak** : brouillon de rubrique généré, export Word.
6. **Honnêteté** : onglet *Fiabilité & données* — performance mesurée contre « prix inchangé », niveaux de méthode,
   qualité des données et marchés pilotes.
        """
    )

# --------------------------------------------------------------------------- #
# Navigation et filtres
# --------------------------------------------------------------------------- #
st.segmented_control("Vue", VIEWS, key="view", label_visibility="collapsed")
view = st.session_state.get("view") or VIEWS[0]

replay_opts = ["", *cached.replay_options(dk)]


def _as_of_label(value: str) -> str:
    if not value:
        return f"Dernier relevé ({month_label_long(header_model.data_last_obs)})"
    return f"{month_label_long(pd.Timestamp(value + '-01'))} · relecture"


def _episode_label(i: int | None) -> str:
    return "—" if i is None else cfg.REPLAY_EPISODES[i]["titre"]


with st.container(key="filters"):
    row1 = [("commodity", 1.25), ("scenario", 1.5), ("horizon", 1.0)]
    if view in PROVINCE_VIEWS:
        row1.append(("province", 1.0))
    if view in SEUIL_VIEWS:
        row1.append(("seuil", 1.15))
    if view in MEB_VIEWS:
        row1.append(("meb_seuil", 1.15))
    cols = dict(zip((k for k, _ in row1), st.columns([w for _, w in row1], gap="medium"), strict=True))
    with cols["commodity"]:
        st.segmented_control("Produit", list(cfg.COMMODITIES), key="commodity",
                             help="Prix de détail au kilo, médiane des marchés.")
    with cols["scenario"]:
        st.segmented_control("Scénario illustratif", list(cfg.SCENARIOS), key="scenario",
                             help="Dérive mensuelle ajoutée à la projection saisonnière (illustratif, non validé).")
    with cols["horizon"]:
        st.segmented_control("Horizon", list(cfg.HORIZONS), key="horizon", format_func=lambda h: f"M+{h}",
                             help="Projection à 1, 2 ou 3 mois.")
    if "province" in cols:
        with cols["province"]:
            st.selectbox("Province", PROVINCES, key="province",
                         help="Vous pouvez aussi cliquer sur une province de la carte.")
    if "seuil" in cols:
        with cols["seuil"]:
            st.slider("Seuil de prix (% > moy. 5 ans)", cfg.SEUIL_MIN, cfg.SEUIL_MAX, step=cfg.SEUIL_STEP, key="seuil",
                      help="Seuil d'alerte de prix : écart à la moyenne du même mois sur 5 ans. "
                           "Non validé par le SISAAP (démonstration).")
    if "meb_seuil" in cols:
        with cols["meb_seuil"]:
            st.slider("Seuil MEB (FCFA/ménage/mois)", cfg.MEB_SEUIL_MIN, cfg.MEB_SEUIL_MAX,
                      step=cfg.MEB_SEUIL_STEP, key="meb_seuil",
                      help="Coût mensuel de la ration céréalière au-delà duquel une alerte MEB est proposée. "
                           "Non validé par le SISAAP (démonstration).")
    r1, r2, r3, r4 = st.columns([1.5, 1.7, 1.1, 1.0], gap="medium")
    with r1:
        st.selectbox("Date de la prévision", replay_opts, key="as_of", format_func=_as_of_label,
                     help="Dernier relevé = situation actuelle. Une date passée rejoue l'outil tel qu'il aurait "
                          "fonctionné, puis compare au réalisé.")
    with r2:
        st.selectbox("Épisode d'illustration", [None, *range(len(cfg.REPLAY_EPISODES))], key="episode",
                     format_func=_episode_label, on_change=apply_episode,
                     help="Charge un cas réel de la soudure 2024 où la méthode a alerté.")
    with r3:
        st.selectbox("Profil", list(cfg.ROLES), key="role",
                     help="Les analystes valident les alertes ; les lecteurs ne voient que les alertes validées.")
    with r4:
        st.toggle("Carte sans fond (hors ligne)", key="offline",
                  help="À activer sans connexion internet : les cartes s'affichent sans fond de carte.")

ss = st.session_state
commodity = ss.get("commodity") or cfg.DEFAULT_COMMODITY
ctx = Ctx(
    commodity=commodity, scenario=ss.get("scenario") or cfg.DEFAULT_SCENARIO,
    horizon=int(ss.get("horizon") or cfg.DEFAULT_HORIZON), province=ss["province"],
    seuil_pct=int(ss["seuil"]), meb_seuil=int(ss["meb_seuil"]), as_of=ss["as_of"], dk=dk, role=ss["role"],
    offline=bool(ss["offline"]),
)
model = cached.get_model(ctx.commodity, ctx.as_of, ctx.dk)

# --------------------------------------------------------------------------- #
# Rendu de la vue
# --------------------------------------------------------------------------- #
if view == "Provinces":
    provinces.render(ctx, geo, on_province_click, go_to_departments)
elif view == "Départements":
    departments.render(ctx, geo, on_department_click)
elif view == "MEB":
    meb.render(ctx)
elif view == "Alertes":
    alerts.render(ctx)
elif view == "Al Aswak":
    bulletin.render(ctx)
else:
    reliability.render(ctx)

st.divider()
ui.methodology_panel(model)
st.caption(f"Vigie Prix · démonstration · {cfg.ORG_NAME} · source des prix : {cfg.DATA_SOURCE}")
