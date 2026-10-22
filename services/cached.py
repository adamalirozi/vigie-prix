"""Couche de cache Streamlit.

Règle : les fonctions mises en cache ne reçoivent que de **petits arguments hachables** (produit, scénario, date de
prévision, horizon, province…). Elles récupèrent elles-mêmes les gros objets (GeoJSON, modèles de prix).

``as_of`` : « » = dernier relevé ; « AAAA-MM » = relecture (la prévision est refaite avec les seules données
disponibles à cette date). ``dk`` = version des données (date de modification des fichiers) : le cache expire dès que
les fichiers WFP sont remplacés.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from services import alerts as alert_engine
from services import evaluation, meb
from services import geo as geomod
from services import prices as P
from ui import charts
from ui.formatting import month_label, month_label_long


# --------------------------------------------------------------------------- #
# Ressources (objets en lecture seule, partagés)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def get_source() -> P.PriceSource:
    """Source de prix. Remplacer ici ``WfpPriceSource`` pour brancher les séries SIMPA après l'audit."""
    return P.WfpPriceSource()


def data_version() -> str:
    return get_source().version()


@st.cache_resource(show_spinner="Chargement des cartes…")
def get_geo() -> geomod.GeoData:
    return geomod.load_geo(cfg.GEO_PROVINCES, cfg.GEO_DEPARTMENTS, cfg.GEO_SIMPLIFY_TOLERANCE)


@st.cache_resource(show_spinner=False)
def get_basket() -> pd.DataFrame:
    return meb.load_basket()


def _ts(as_of: str) -> pd.Timestamp | None:
    return pd.Timestamp(f"{as_of}-01") if as_of else None


@st.cache_resource(show_spinner="Préparation des séries de prix…", max_entries=24)
def get_model(commodity: str, as_of: str, dk: str) -> P.Model:
    return P.build_model(get_source(), get_geo(), commodity, _ts(as_of))


def get_models(as_of: str, dk: str) -> dict[str, P.Model]:
    return {c: get_model(c, as_of, dk) for c in cfg.COMMODITIES}


def replay_options(dk: str) -> list[str]:
    """Dates de prévision proposées en relecture (du plus récent au plus ancien), au format AAAA-MM."""
    last = get_model(cfg.DEFAULT_COMMODITY, "", dk).data_last_obs
    return [f"{last - pd.DateOffset(months=k):%Y-%m}" for k in range(1, cfg.REPLAY_MONTHS + 1)]


# --------------------------------------------------------------------------- #
# Données
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def get_province_table(commodity: str, scenario: str, as_of: str, horizon: int, dk: str) -> pd.DataFrame:
    return get_model(commodity, as_of, dk).province_table(scenario, horizon)


@st.cache_data(show_spinner=False)
def get_missing_provinces(commodity: str, as_of: str, dk: str) -> pd.DataFrame:
    """Provinces sans prix récent : Code_ID, Province, Dernier_Releve (texte)."""
    model = get_model(commodity, as_of, dk)
    miss = model.missing_provinces().merge(model.provinces, on="Province")
    miss["Dernier_Releve"] = miss["Derniere_Obs"].map(lambda d: month_label_long(d) if pd.notna(d) else "aucun")
    return miss[["Code_ID", "Province", "Dernier_Releve"]]


@st.cache_data(show_spinner=False)
def get_department_table(commodity: str, scenario: str, as_of: str, horizon: int, dk: str) -> pd.DataFrame:
    return get_model(commodity, as_of, dk).department_table(scenario, horizon)


def filter_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == cfg.ALL_PROVINCES:
        return df.copy()
    return df.loc[df["Province"] == scope].copy()


@st.cache_data(show_spinner=False)
def get_province_series(commodity: str, province: str, scenario: str, as_of: str, dk: str) -> dict:
    return get_model(commodity, as_of, dk).province_series(province, scenario)


@st.cache_data(show_spinner=False)
def get_department_series(commodity: str, dept_id: str, province: str, scenario: str, as_of: str, dk: str) -> dict:
    return get_model(commodity, as_of, dk).department_series(dept_id, province, scenario)


@st.cache_data(show_spinner=False)
def get_markets(commodity: str, as_of: str, dk: str, province: str = cfg.ALL_PROVINCES) -> pd.DataFrame:
    """Marchés actifs (prix récent), éventuellement limités à une province."""
    model = get_model(commodity, as_of, dk)
    return model.active_markets() if province == cfg.ALL_PROVINCES else model.markets_in(province)


@st.cache_data(show_spinner=False)
def get_market_table(commodity: str, scenario: str, as_of: str, horizon: int, dk: str) -> pd.DataFrame:
    return get_model(commodity, as_of, dk).market_table(scenario, horizon)


@st.cache_data(show_spinner=False)
def get_all_markets(commodity: str, as_of: str, dk: str) -> pd.DataFrame:
    """Tous les marchés géolocalisés (actifs ou non), avec fiabilité des relevés."""
    return get_model(commodity, as_of, dk).markets.copy()


@st.cache_data(show_spinner=False)
def get_meb_table(scenario: str, as_of: str, horizon: int, dk: str) -> pd.DataFrame:
    return meb.cost_table(get_models(as_of, dk), get_basket(), scenario, horizon)


@st.cache_data(show_spinner="Calcul des alertes…")
def get_alerts(scenario: str, as_of: str, horizon: int, seuil_pct: int, meb_seuil: int, dk: str) -> pd.DataFrame:
    return alert_engine.generate(get_models(as_of, dk), get_basket(), scenario, horizon, seuil_pct, meb_seuil)


@st.cache_data(show_spinner="Rétro-test en cours…")
def get_backtest(commodity: str, as_of: str, dk: str) -> pd.DataFrame:
    model = get_model(commodity, as_of, dk)
    return evaluation.backtest(model.prov_panel, model.last_obs)


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def fig_province_map(commodity: str, scenario: str, as_of: str, horizon: int, dk: str, selected_code: str,
                     metric: str, show_markets: bool, offline: bool) -> go.Figure:
    geo = get_geo()
    center, zoom = geomod.center_zoom(geo.bounds, 720, cfg.MAP_HEIGHT_PROVINCES)
    markets = get_markets(commodity, as_of, dk) if show_markets else None
    return charts.province_map(
        get_province_table(commodity, scenario, as_of, horizon, dk), geo.provinces,
        get_missing_provinces(commodity, as_of, dk), geo.provinces_geojson, selected_code, metric, center, zoom,
        markets, offline,
    )


@st.cache_data(show_spinner=False)
def fig_trend(commodity: str, province: str, scenario: str, as_of: str, horizon: int, dk: str,
              seuil_pct: int) -> go.Figure:
    model = get_model(commodity, as_of, dk)
    s = get_province_series(commodity, province, scenario, as_of, dk)
    return charts.trend_figure(model.dates_hist, s["hist"], model.dates_proj, s["proj"], s["band"], s["ref"],
                               seuil_pct, horizon=horizon, actual=s["actual"] or None)


@st.cache_data(show_spinner=False)
def fig_dumbbell(commodity: str, province: str, scenario: str, as_of: str, horizon: int, dk: str) -> go.Figure:
    return charts.dumbbell_figure(get_province_table(commodity, scenario, as_of, horizon, dk), province)


@st.cache_data(show_spinner=False)
def fig_quadrant(commodity: str, province: str, scenario: str, as_of: str, horizon: int, dk: str) -> go.Figure:
    return charts.quadrant_figure(get_province_table(commodity, scenario, as_of, horizon, dk), province)


@st.cache_data(show_spinner=False)
def fig_heatmap(commodity: str, province: str, scenario: str, as_of: str, horizon: int, dk: str) -> go.Figure:
    model = get_model(commodity, as_of, dk)
    matrix = model.deviation_matrix(scenario)
    labels = [month_label(d) for d in model.dates_hist + model.dates_proj]
    order = get_province_table(commodity, scenario, as_of, horizon, dk).sort_values(
        "Variation_pct", ascending=False)["Province"]
    return charts.heatmap_figure(matrix, labels, len(model.dates_hist), province, order.tolist())


@st.cache_data(show_spinner=False)
def fig_bullet(actual: float, projected: float, seuil: float, kind: str) -> go.Figure:
    """kind = « pct » (écart à la moyenne 5 ans) ou « meb » (FCFA/ménage/mois)."""
    if kind == "meb":
        top = max(actual, projected, seuil) * 1.15
        return charts.bullet_figure(actual, projected, seuil, suffix=" FCFA", fmt=",.0f", lo=0, hi=top)
    return charts.bullet_figure(actual, projected, seuil)


@st.cache_data(show_spinner=False)
def fig_markets_trend(commodity: str, province: str, as_of: str, dk: str) -> go.Figure:
    model = get_model(commodity, as_of, dk)
    mk = model.markets_in(province)
    series = {r.Marché: model.market_series(r.market_id) for r in mk.itertuples()}
    return charts.markets_trend_figure(model.dates_hist, series, province,
                                       model.prov_panel.loc[model.dates_hist, province].tolist())


@st.cache_data(show_spinner=False)
def fig_department_map(commodity: str, scenario: str, as_of: str, horizon: int, dk: str, scope: str,
                       selected_id: str, show_markets: bool, offline: bool) -> go.Figure:
    geo = get_geo()
    table = get_department_table(commodity, scenario, as_of, horizon, dk)
    df = filter_scope(table, scope)
    amplitude = max(10.0, float(table["Ecart_Parent_pct"].abs().max()))  # échelle fixe entre périmètres
    if scope == cfg.ALL_PROVINCES:
        center, zoom = geomod.center_zoom(geo.bounds, 720, cfg.MAP_HEIGHT_DEPARTMENTS)
    else:
        center, zoom = geomod.center_zoom(geo.province_bounds(scope), 560, cfg.MAP_HEIGHT_DEPARTMENTS)
    markets = get_markets(commodity, as_of, dk, scope) if show_markets else None
    return charts.department_map(
        df, geo.departments_geojson_for(df["Code_ID"].tolist()), selected_id,
        geo.departments, amplitude, center, zoom, scope == cfg.ALL_PROVINCES, markets, offline,
    )


@st.cache_data(show_spinner=False)
def fig_gap_bar(commodity: str, scenario: str, as_of: str, horizon: int, dk: str, scope: str,
                selected_id: str) -> go.Figure:
    df = filter_scope(get_department_table(commodity, scenario, as_of, horizon, dk), scope)
    return charts.gap_bar_figure(df, selected_id)


@st.cache_data(show_spinner=False)
def fig_comparison(commodity: str, dept_id: str, scenario: str, as_of: str, horizon: int, dk: str) -> go.Figure:
    model = get_model(commodity, as_of, dk)
    dept = get_department_table(commodity, scenario, as_of, horizon, dk).set_index("Code_ID").loc[dept_id]
    s = get_department_series(commodity, dept_id, dept["Province"], scenario, as_of, dk)
    return charts.comparison_trend_figure(
        dept["Province"], dept["Département"], model.dates_hist, model.dates_proj,
        s["parent_hist"], s["parent_proj"], s["hist"], s["proj"],
    )


@st.cache_data(show_spinner=False)
def fig_meb(scenario: str, as_of: str, horizon: int, dk: str, meb_seuil: int, province: str) -> go.Figure:
    return charts.meb_figure(get_meb_table(scenario, as_of, horizon, dk), meb_seuil, province)


@st.cache_data(show_spinner=False)
def fig_backtest(commodity: str, as_of: str, dk: str) -> go.Figure:
    return charts.backtest_figure(get_backtest(commodity, as_of, dk))


@st.cache_data(show_spinner=False)
def fig_coverage(commodity: str, as_of: str, dk: str, offline: bool) -> go.Figure:
    geo = get_geo()
    center, zoom = geomod.center_zoom(geo.bounds, 720, cfg.MAP_HEIGHT_PROVINCES)
    return charts.coverage_map(get_all_markets(commodity, as_of, dk), geo.provinces_geojson, center, zoom, offline)
