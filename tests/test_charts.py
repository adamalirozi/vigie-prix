"""Tests de fumée : chaque figure se construit et se sérialise en JSON."""
import pytest

import config as cfg
from services import evaluation, meb
from services import geo as geomod
from ui import charts
from ui.formatting import month_label


def _ok(fig):
    assert len(fig.data) >= 1 and fig.to_json()
    return fig


def _province_map(model, geo, metric, markets=True, selected="TD-KA", offline=False):
    table = model.province_table("Référence", 2)
    missing = model.missing_provinces().merge(model.provinces, on="Province").assign(Dernier_Releve="août 2024")
    center, zoom = geomod.center_zoom(geo.bounds)
    return charts.province_map(table, geo.provinces, missing, geo.provinces_geojson, selected, metric, center, zoom,
                               model.active_markets() if markets else None, offline)


@pytest.mark.parametrize("metric", list(charts.MAP_METRICS))
def test_province_map_metrics(model, geo, metric):
    fig = _ok(_province_map(model, geo, metric))
    assert fig.layout.clickmode == "event+select" and fig.layout.map.style == cfg.MAP_STYLE


def test_offline_maps_have_no_basemap(model, geo):
    assert _province_map(model, geo, "Prix_Projete", offline=True).layout.map.style == cfg.MAP_STYLE_OFFLINE


def test_province_map_without_markets_or_selection(model, geo):
    _ok(_province_map(model, geo, "Prix_Projete", markets=False, selected="TD-TI"))  # Tibesti : pas de donnée


@pytest.mark.parametrize("horizon", cfg.HORIZONS)
def test_trend_highlights_the_chosen_horizon(model, horizon):
    s = model.province_series("Kanem", "Référence")
    fig = _ok(charts.trend_figure(model.dates_hist, s["hist"], model.dates_proj, s["proj"], s["band"], s["ref"], 20,
                                  horizon=horizon))
    sizes = next(t.marker.size for t in fig.data if t.name == "Projection indicative")
    assert sizes[horizon] == 12 and fig.layout.xaxis.type == "category"
    assert {t.name for t in fig.data} >= {"Prix observé", "Moyenne 5 ans", "Projection indicative"}


def test_trend_in_replay_shows_realised_prices(replay_models):
    m = replay_models["Mil"]
    s = m.province_series("Hadjer-Lamis", "Référence")
    fig = _ok(charts.trend_figure(m.dates_hist, s["hist"], m.dates_proj, s["proj"], s["band"], s["ref"], 20,
                                  actual=s["actual"]))
    assert "Prix réalisé" in {t.name for t in fig.data}
    assert any(a.text == "Date de la prévision" for a in fig.layout.annotations)
    assert any(a.text == "soudure" for a in fig.layout.annotations)


def test_province_comparisons(model):
    table = model.province_table("Référence")
    _ok(charts.dumbbell_figure(table, "Kanem"))
    _ok(charts.dumbbell_figure(table, "Tibesti"))  # sélection sans donnée
    _ok(charts.quadrant_figure(table, "Kanem"))
    labels = [month_label(d) for d in model.dates_hist + model.dates_proj]
    _ok(charts.heatmap_figure(model.deviation_matrix("Référence"), labels, cfg.HISTORY_MONTHS, "Kanem",
                              table["Province"].tolist()))


def test_bullets(model):
    _ok(charts.bullet_figure(-25.0, -10.0, 20))
    _ok(charts.bullet_figure(80.0, 95.0, 20))
    _ok(charts.bullet_figure(12_000, 16_000, 15_000, suffix=" FCFA", fmt=",.0f", lo=0, hi=20_000))


def test_markets_trend(model):
    mk = model.markets_in("Moyen-Chari")
    series = {r.Marché: model.market_series(r.market_id) for r in mk.itertuples()}
    _ok(charts.markets_trend_figure(model.dates_hist, series, "Moyen-Chari",
                                    model.prov_panel.loc[model.dates_hist, "Moyen-Chari"].tolist()))


def test_department_charts(model, geo):
    table = model.department_table("Référence", 3)
    sel = table["Code_ID"].iloc[0]
    amp = max(10.0, float(table["Ecart_Parent_pct"].abs().max()))
    center, zoom = geomod.center_zoom(geo.bounds)
    _ok(charts.department_map(table, geo.departments_geojson_for(table["Code_ID"].tolist()), sel, geo.departments,
                              amp, center, zoom, True, model.active_markets(), True))
    _ok(charts.gap_bar_figure(table, sel))
    one = table[table["Province"] == "N'Djamena Region"]  # périmètre à 1 département
    _ok(charts.gap_bar_figure(one, one["Code_ID"].iloc[0]))
    row = table.iloc[0]
    s = model.department_series(row["Code_ID"], row["Province"], "Référence")
    _ok(charts.comparison_trend_figure(row["Province"], row["Département"], model.dates_hist, model.dates_proj,
                                       s["parent_hist"], s["parent_proj"], s["hist"], s["proj"]))


def test_meb_backtest_and_coverage_figures(models, basket, geo):
    table = meb.cost_table(models, basket, "Référence", 3)
    fig = _ok(charts.meb_figure(table, 15_000, "Kanem"))
    assert any(s.x0 == 15_000 for s in fig.layout.shapes)  # le seuil est tracé
    bt = evaluation.backtest(models["Mil"].prov_panel, models["Mil"].last_obs)
    assert len(_ok(charts.backtest_figure(bt)).data) == 4
    center, zoom = geomod.center_zoom(geo.bounds)
    cov = _ok(charts.coverage_map(models["Mil"].markets, geo.provinces_geojson, center, zoom, True))
    assert {t.name.split(" (")[0] for t in cov.data if t.name} <= {"Bonne", "Moyenne", "Faible", "Inactif"}


def test_french_separators(model):
    assert charts.dumbbell_figure(model.province_table("Référence"), "Kanem").layout.separators == ", "
