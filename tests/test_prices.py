import numpy as np
import pandas as pd
import pytest

import config as cfg
from services import prices as P

# --------------------------------------------------------------------------- #
# Statistiques sur données synthétiques (résultat connu d'avance)
# --------------------------------------------------------------------------- #


def test_seasonal_index_recovers_known_shape(seasonal_panel):
    national, per = P.seasonal_indices(seasonal_panel, pd.Timestamp("2023-12-01"))
    expected = 1 + 0.2 * np.sin(2 * np.pi * np.arange(12) / 12)
    assert national.shape == (12,) and national.mean() == pytest.approx(1)
    assert np.allclose(national, expected / expected.mean(), atol=1e-6)
    assert set(per) == {"A", "B"}


def test_seasonal_ratio_round_trip():
    idx = np.linspace(0.9, 1.1, 12)
    assert P.seasonal_ratio(idx, 3, 4) * P.seasonal_ratio(idx, 7, 8) == pytest.approx(1)


def test_projection_follows_season_and_drift():
    flat, origin = np.ones(12), pd.Timestamp("2026-06-01")
    assert P.project(100, origin, flat, 0.0) == pytest.approx([100.0] * cfg.HORIZON)
    assert P.project(100, origin, flat, 0.02)[2] == pytest.approx(100 * 1.02**3)
    idx = np.array([1.0] * 6 + [1.1] + [1.0] * 5)  # juillet 10 % plus cher
    assert P.project(100, origin, idx, 0.0)[0] == pytest.approx(110)


def test_five_year_reference():
    dates = pd.date_range("2018-01-01", "2024-12-01", freq="MS")
    ref = P.five_year_reference(pd.DataFrame({"A": 100.0}, index=dates))
    assert ref.loc["2024-06-01", "A"] == pytest.approx(100)
    assert np.isnan(ref.loc["2020-06-01", "A"])  # seulement 2 années disponibles
    assert ref.loc["2021-06-01", "A"] == pytest.approx(100)  # 3 années : minimum atteint


def test_forecast_band_is_tight_without_noise_and_wide_with(seasonal_panel):
    last = pd.Timestamp("2023-12-01")
    _, per = P.seasonal_indices(seasonal_panel, last)
    assert all(lo == pytest.approx(1, abs=1e-6) and hi == pytest.approx(1, abs=1e-6)
               for lo, hi in P.forecast_band(seasonal_panel, per, last))
    noisy = seasonal_panel * np.random.default_rng(0).lognormal(0, 0.1, seasonal_panel.shape)
    wide = P.forecast_band(noisy, per, last)
    assert all(lo < 1 < hi for lo, hi in wide) and wide[2][1] - wide[2][0] > 0.1


@pytest.mark.parametrize("variation,horizon,expected", [
    (-3, 3, "Faible"), (9.9, 3, "Faible"), (10, 3, "Modéré"), (19.9, 3, "Modéré"), (20, 3, "Élevé"),
    (3.4, 1, "Modéré"), (3.2, 1, "Faible"), (6.7, 2, "Modéré"),  # seuils proportionnels à l'horizon
])
def test_vigilance_thresholds_scale_with_horizon(variation, horizon, expected):
    assert P.classify_vigilance(variation, horizon) == expected


@pytest.mark.parametrize("gap,prefix", [(10, "Au-dessus"), (-10, "En dessous"), (9.9, "Proche")])
def test_gap_signal(gap, prefix):
    assert P.classify_gap(gap).startswith(prefix)


def test_cleaning_masks_isolated_and_synchronized_anomalies():
    dates = pd.date_range("2020-01-01", periods=36, freq="MS")
    wide = pd.DataFrame({i: 100.0 for i in range(20)}, index=dates)
    wide.iloc[10, 0] = 300.0  # relevé isolé aberrant
    wide.iloc[20, :] = 140.0  # tous les marchés bondissent ensemble puis reviennent
    cleaned, n_isolated, sync = P.clean_outliers(wide)
    assert np.isnan(cleaned.iloc[10, 0]) and n_isolated >= 1
    assert list(sync) == [dates[20]] and cleaned.iloc[20].isna().all()
    assert cleaned.iloc[5].notna().all()


# --------------------------------------------------------------------------- #
# Source WFP (fichiers réels)
# --------------------------------------------------------------------------- #


def test_source_monthly_panel(source):
    wide = source.monthly_prices("Sorgho")
    assert wide.index.is_monotonic_increasing and (wide.index.to_series().diff().dropna().dt.days >= 28).all()
    assert wide.index[-1] >= pd.Timestamp("2026-06-01")
    assert wide.loc["2026-06-01"].notna().sum() > 50  # « Sorghum (red) » s'arrête en février : fusion avec « Sorghum »
    assert source.markets()[["lat", "lon"]].notna().all().all()


# --------------------------------------------------------------------------- #
# Modèle (fichiers réels)
# --------------------------------------------------------------------------- #


def test_last_observation_anchors_the_model(model):
    assert model.last_obs == pd.Timestamp("2026-06-01") and not model.is_replay
    assert len(model.dates_hist) == cfg.HISTORY_MONTHS and model.dates_hist[-1] == model.last_obs
    assert model.dates_proj[0] == pd.Timestamp("2026-07-01") and len(model.dates_proj) == cfg.HORIZON


@pytest.mark.parametrize("horizon", cfg.HORIZONS)
def test_province_table_is_consistent_for_every_horizon(model, horizon):
    table = model.province_table("Référence", horizon)
    assert table["Code_ID"].is_unique and len(table) == 22 and (table["Horizon"] == horizon).all()
    for _, row in table.iterrows():
        s = model.province_series(row["Province"], "Référence")
        assert s["proj"][horizon - 1] == pytest.approx(row["Prix_Projete"], abs=0.06)
        assert row["Sparkline"][-cfg.HORIZON:] == pytest.approx(s["proj"])
        assert len(row["Sparkline"]) == cfg.HISTORY_MONTHS + cfg.HORIZON
        assert row["Mois_Pic"] in model.dates_proj
    assert (table["Prix_Actuel"] > 50).all() and (table["Prix_Actuel"] < 1500).all()  # FCFA/kg, pas par sac


def test_horizon_one_is_between_now_and_horizon_three(model):
    t1 = model.province_table("Référence", 1).set_index("Province")
    t3 = model.province_table("Référence", 3).set_index("Province")
    assert (t1["Prix_Actuel"] == t3["Prix_Actuel"]).all()
    assert (t1["Prix_Projete"] != t3["Prix_Projete"]).any()


def test_vigilance_matches_variation(model):
    table = model.province_table("Pression accrue", 3)
    for _, row in table.iterrows():
        v = row["Variation_pct"]
        if abs(v - cfg.ALERT_MID) > 0.1 and abs(v - cfg.ALERT_HIGH) > 0.1:
            assert P.classify_vigilance(v, 3) == row["Vigilance"]


def test_stale_provinces_have_no_current_price(model, models):
    missing = model.missing_provinces()
    assert "Tibesti" in set(missing["Province"])  # suivi arrêté en août 2024
    assert missing.set_index("Province").loc["Tibesti", "Derniere_Obs"] < model.cutoff
    assert "Tibesti" not in set(model.province_table("Référence")["Province"])
    assert {"Tibesti", "Borkou"} <= set(models["Maïs"].missing_provinces()["Province"])


def test_scenarios_are_ordered(model):
    med = {s: model.province_table(s)["Variation_pct"].median() for s in cfg.SCENARIOS}
    assert med["Détente"] < med["Référence"] < med["Pression accrue"]
    assert model.province_table("Référence")["Variation_pct"].nunique() > 5  # saisonnalité propre à chaque province


def test_band_brackets_the_projection(model):
    s = model.province_series("Kanem", "Référence")
    assert all(lo <= p <= hi for p, (lo, hi) in zip(s["proj"], s["band"], strict=True))
    widths = [hi - lo for lo, hi in s["band"]]
    assert widths == sorted(widths)  # l'incertitude croît avec l'horizon


def test_markets_reliability_and_assignment(model):
    mk = model.markets.set_index("Marché")
    assert mk.loc["Moundou", "Province"] == "Logone Occidental"  # la frontière du GeoJSON le met à côté
    active = mk[mk["Actif"]]
    assert len(active) > 50 and set(active["Fiabilite"]) <= {"Bonne", "Moyenne", "Faible"}
    assert active["Completude_pct"].between(0, 100).all()
    inactive = mk[~mk["Actif"]]
    assert (inactive["Fiabilite"] == "Inactif").all()


def test_market_table_forecasts_every_active_market(model):
    mt = model.market_table("Référence", 2)
    assert len(mt) == int(model.markets["Actif"].sum()) and (mt["Horizon"] == 2).all()
    assert (mt["Prix_Projete"] > 0).all() and mt["Fiabilite"].notna().all()


def test_department_table_and_series(model):
    table = model.department_table("Pression accrue", 2)
    assert len(table) == 68 and table["Code_ID"].is_unique
    local = table[table["Distance_km"] == 0]
    assert (local["Source_Prix"] == "Marché local").all() and (local["Nb_Marches"] > 0).all()
    nearest = table[table["Distance_km"] > 0]
    assert nearest["Source_Prix"].str.contains("km").all() and (nearest["Nb_Marches"] == 0).all()
    t = table.set_index("Code_ID")
    for dept_id in t.index[:15]:
        s = model.department_series(dept_id, t.loc[dept_id, "Province"], "Pression accrue")
        assert s["proj"][1] == pytest.approx(t.loc[dept_id, "Prix_Projete"], abs=0.06)


# --------------------------------------------------------------------------- #
# Relecture : aucune fuite d'information
# --------------------------------------------------------------------------- #


def test_replay_never_uses_data_after_the_forecast_date(replay_models, models):
    m, full = replay_models["Mil"], models["Mil"]
    assert m.is_replay and m.last_obs == pd.Timestamp("2024-03-01") and m.data_last_obs == full.last_obs
    future = m.prov_panel.loc[m.last_obs + pd.offsets.MonthBegin(1):]
    assert future.notna().sum().sum() == 0
    assert m.market_panel.index.max() == m.last_obs
    # la saisonnalité et l'intervalle diffèrent de ceux calculés avec toutes les données
    assert not np.allclose(m.seasonal, full.seasonal) or m.band != full.band


def test_replay_exposes_realised_prices_only_for_comparison(replay_models):
    m = replay_models["Mil"]
    s = m.province_series("Hadjer-Lamis", "Référence")
    assert len(s["actual"]) == cfg.HORIZON and all(pd.notna(s["actual"]))
    assert s["actual"][2] > s["proj"][2]  # la hausse de la soudure 2024 dépasse la projection


def test_latest_model_has_no_realised_series(model):
    assert model.province_series("Kanem", "Référence")["actual"] == []
