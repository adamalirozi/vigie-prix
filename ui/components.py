"""Composants d'interface réutilisables."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config as cfg
from services.prices import Model
from ui.formatting import month_label_long


@st.cache_resource(show_spinner=False)
def _css() -> str:
    return cfg.STYLES_CSS.read_text(encoding="utf-8")


def inject_css() -> None:
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def months_behind(last_obs: pd.Timestamp, today: pd.Timestamp | None = None) -> int:
    """Nombre de mois entre le dernier relevé et aujourd'hui."""
    today = today or pd.Timestamp.now()
    return (today.year - last_obs.year) * 12 + today.month - last_obs.month


def render_header(model: Model) -> None:
    if model.is_replay:
        badge = (f'<span class="badge badge-warn">Relecture · prévision faite en {month_label_long(model.last_obs)} '
                 f"(données jusqu'à {month_label_long(model.data_last_obs)})</span>")
    else:
        lag = months_behind(model.last_obs)
        badge = (
            f'<span class="badge badge-warn">Données arrêtées à {month_label_long(model.last_obs)} '
            f"({lag} mois de retard)</span>"
            if lag > 2
            else f'<span class="badge">Dernier relevé : {month_label_long(model.last_obs)}</span>'
        )
    st.markdown(
        '<header class="dashboard-header">'
        "<div>"
        f'<h1 class="page-title">{cfg.APP_TITLE}</h1>'
        f'<p class="page-subtitle">{cfg.APP_SUBTITLE}</p>'
        f'<p class="demo-banner">{cfg.DEMO_BANNER}</p>'
        "</div>"
        '<div class="header-meta">'
        f"{badge}"
        f"<span>Source : {cfg.DATA_SOURCE} · prix de détail en {cfg.UNIT}</span>"
        "<span>Méthode : niveau 1 (référence saisonnière) · projections illustratives</span>"
        "</div>"
        "</header>",
        unsafe_allow_html=True,
    )


def with_level_icon(df: pd.DataFrame, column: str = "Vigilance", out: str = "Niveau") -> pd.DataFrame:
    """Ajoute une colonne « ▲ Élevé / ● Modéré / ○ Faible » : le niveau n'est pas porté par la couleur seule."""
    df = df.copy()
    df[out] = df[column].map(lambda v: f"{cfg.VIGILANCE_ICON[v]} {v}")
    return df


def methodology_panel(model: Model) -> None:
    n_active = int(model.markets["Actif"].sum())
    drifts = ", ".join(f"{name} ({d * 100:+.0f} %/mois)".replace(".", ",") for name, d in cfg.SCENARIOS.items())
    band = " · ".join(
        f"M+{h}: −{(1 - lo) * 100:.0f} % / +{(hi - 1) * 100:.0f} %" for h, (lo, hi) in enumerate(model.band, 1)
    )
    months = ", ".join(f"{month_label_long(d)}" for d in model.sync_months) or "aucun"
    with st.expander("Méthodologie, limites et définitions"):
        st.markdown(
            f"""
**Statut.** Démonstration sur données publiques WFP. Les seuils, les alertes et la composition du MEB ne sont **pas
validés par le SISAAP** ; toute publication exige la validation d'un analyste. Facteurs externes (carburant, pluie,
conflit, marchés frontaliers) : **non connectés** à ce stade.

**Source.** {cfg.DATA_SOURCE} : prix de détail mensuels par marché, en {cfg.UNIT}. Dernier relevé disponible :
**{month_label_long(model.data_last_obs)}**. {n_active} marchés géolocalisés ont un prix récent pour « {model.commodity} ».
Les marchés sans coordonnées (par exemple Oum Hadjer) ne sont pas utilisés.

**Nettoyage (audit).** {model.n_outliers} relevés isolés très éloignés de la médiane de leur marché sont écartés ;
les mois où tous les marchés bougent ensemble puis reviennent sont écartés comme probables artefacts de collecte
(mois écartés pour ce produit : {months}). À confirmer avec le SISAAP ; réglable dans `config.py`.

**Prix provincial.** Médiane des marchés actifs de la province. Un prix est « actuel » s'il date de moins de
{cfg.MAX_STALE_MONTHS} mois avant le dernier relevé ; sinon la province apparaît en gris (ex. Tibesti).
**Prix départemental.** Marchés du département, à défaut marché actif le plus proche (source et distance indiquées) :
prix estimé, non observé.

**Moyenne 5 ans et seuil d'alerte.** Moyenne du même mois sur les {cfg.REFERENCE_YEARS} années précédentes
(≥ {cfg.REFERENCE_MIN_YEARS}). Le seuil d'alerte de prix est un % au-dessus de cette référence.

**Projection (niveau 1).** Dernier prix × rapport saisonnier × (1 + dérive du scénario)^mois. Saisonnalité estimée
depuis {cfg.SEASONAL_FIRST_YEAR}, par province (poids {int(cfg.SEASONAL_OWN_WEIGHT * 100)} %) et nationale. C'est la
méthode simple que les niveaux 2 et 3 devront battre. Scénarios, **illustratifs** : {drifts}.
**Intervalle à 80 %** issu d'un rétro-test ({band}).

**Vigilance** (variation projetée) : ○ Faible < {int(cfg.ALERT_MID)} % ≤ ● Modéré < {int(cfg.ALERT_HIGH)} % ≤ ▲ Élevé pour
3 mois (seuils proportionnels à l'horizon). **Alertes** : « hausse rapide » (≥ {int(cfg.ALERT_MID)} %), « seuil de prix »
(écart à la moyenne 5 ans) et « seuil MEB ». **Confiance** : marchés actifs, complétude, horizon, largeur de
l'intervalle, retard de relevé.

**MEB.** Seule la composante céréales est calculée, selon `data/meb_composition.csv` (à remplacer par la composition
validée du Cluster). Ménage de {cfg.HOUSEHOLD_SIZE} personnes, {cfg.DAYS_PER_MONTH} jours par mois.

**Relecture.** Refait la prévision avec les seules données disponibles à la date choisie, puis compare au réalisé.
            """
        )
