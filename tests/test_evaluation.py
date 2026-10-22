import numpy as np
import pandas as pd
import pytest

import config as cfg
from services import evaluation as ev


def test_backtest_on_known_seasonality_beats_no_change(seasonal_panel):
    noisy = seasonal_panel * np.random.default_rng(1).lognormal(0, 0.02, seasonal_panel.shape)
    bt = ev.backtest(noisy, pd.Timestamp("2023-12-01"))
    assert list(bt["Horizon"]) == [1, 2, 3]
    assert (bt["Erreur_saisonnier_pct"] < bt["Erreur_prix_inchange_pct"]).all()
    assert bt.loc[2, "Hausses_detectees_pct"] > 50  # une saisonnalité de ±20 % est détectée
    assert (bt["Avance_semaines"] == (bt["Horizon"] * cfg.WEEKS_PER_MONTH).round(0)).all()


def test_backtest_uses_only_data_before_the_test_window(seasonal_panel):
    """Modifier le futur de la période de test ne doit pas changer la saisonnalité estimée avant elle."""
    last = pd.Timestamp("2023-12-01")
    base = ev.backtest(seasonal_panel, last)
    cut = last - pd.DateOffset(months=cfg.BACKTEST_TEST_MONTHS)
    tampered = seasonal_panel.copy()
    tampered.loc[tampered.index > cut] *= 1.5  # tout le futur change d'échelle : les erreurs relatives restent nulles
    assert ev.backtest(tampered, last)["Erreur_saisonnier_pct"].tolist() == pytest.approx(
        base["Erreur_saisonnier_pct"].tolist(), abs=0.01)


def test_backtest_on_real_data_is_honest(models):
    m = models["Mil"]
    bt = ev.backtest(m.prov_panel, m.last_obs)
    assert (bt["Cas_testes"] > 500).all()
    assert bt["Erreur_saisonnier_pct"].between(1, 40).all()
    text = ev.verdict(bt)
    assert "prix inchangé" in text and "%" in text and "niveaux 2 et 3" in text


def test_verdict_wording_follows_the_numbers():
    row = dict(Horizon=3, Erreur_prix_inchange_pct=15.0, Erreur_saisonnier_pct=10.0, Hausses_detectees_pct=50.0,
               Precision_signal_pct=30.0)
    better = ev.verdict(pd.DataFrame([row]))
    worse = ev.verdict(pd.DataFrame([{**row, "Erreur_saisonnier_pct": 20.0}]))
    similar = ev.verdict(pd.DataFrame([{**row, "Erreur_saisonnier_pct": 15.3}]))
    assert "réduit l'erreur" in better and "moins précise" in worse and "à peu près aussi précise" in similar


def test_pilot_markets(model):
    pilots = ev.pilot_markets(model.markets)
    assert 0 < len(pilots) <= cfg.PILOT_MARKETS_N
    assert pilots["Province"].is_unique and pilots["Actif"].all()
    assert pilots["Completude_pct"].is_monotonic_decreasing
