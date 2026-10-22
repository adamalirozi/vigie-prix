import pandas as pd
import pytest

import config as cfg
from services import alerts as engine


def _alerts(models, basket, scenario="Référence", horizon=3, seuil=20, meb_seuil=15_000):
    return engine.generate(models, basket, scenario, horizon, seuil, meb_seuil)


# --------------------------------------------------------------------------- #
# Confiance
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("args,expected", [
    ((4, 90, 1, 8), "Élevée"),    # 2 + 2 + 2 + 1 = 7
    ((3, 80, 3, 10), "Moyenne"),  # 2 + 2 + 0 + 1 = 5
    ((2, 70, 2, 15), "Faible"),   # 1 + 1 + 1 + 0 = 3
    ((1, 50, 3, 20), "Faible"),   # 0
])
def test_confidence_levels(args, expected):
    level, reasons = engine.confidence(*args)
    assert level == expected and len(reasons) >= 4


def test_stale_data_lowers_confidence():
    fresh, _ = engine.confidence(3, 85, 2, 10, lag_months=0)  # 2+2+1+1 = 6
    stale, reasons = engine.confidence(3, 85, 2, 10, lag_months=3)  # 5
    assert fresh == "Élevée" and stale == "Moyenne" and any("dernier relevé" in r for r in reasons)


# --------------------------------------------------------------------------- #
# Génération
# --------------------------------------------------------------------------- #
def test_generate_on_latest_data(models, basket):
    a = _alerts(models, basket)
    assert a["Cle"].is_unique and set(a["Type"]) <= set(engine.TYPES)
    assert set(a["Confiance"]) <= set(cfg.CONFIDENCE_LEVELS)
    assert (a["Premier_Mois_k"].between(1, 3)).all()
    assert (a["Constate"] == "").all()  # pas de relecture : rien n'est « constaté »
    assert a["Facteurs"].map(len).min() >= 3 and a["Facteurs"].map(lambda f: "non connectés" in f[-1]).all()


def test_alert_rules_match_their_definitions(models, basket):
    a = _alerts(models, basket, "Pression accrue")
    rapid = a[a["Type"] == "Hausse rapide"]
    assert (rapid["Variation_pct"] >= cfg.ALERT_MID).all() and len(rapid) > 0
    price = _alerts(models, basket, "Pression accrue", seuil=0)
    assert (price[price["Type"] == "Seuil de prix"]["Ecart_Moy5_Projete_pct"] > 0).all()
    meb_low = _alerts(models, basket, meb_seuil=cfg.MEB_SEUIL_MIN)
    meb_high = _alerts(models, basket, meb_seuil=cfg.MEB_SEUIL_MAX)
    assert (meb_low["Type"] == "Seuil MEB").sum() > (meb_high["Type"] == "Seuil MEB").sum()


def test_higher_threshold_gives_fewer_price_alerts(replay_models, basket):
    low = _alerts(replay_models, basket, seuil=10)
    high = _alerts(replay_models, basket, seuil=40)
    assert (low["Type"] == "Seuil de prix").sum() > (high["Type"] == "Seuil de prix").sum()


def test_shorter_horizon_cannot_add_alert_months(replay_models, basket):
    a1 = _alerts(replay_models, basket, horizon=1)
    assert (a1["Premier_Mois_k"] == 1).all()


def test_demo_episodes_are_selectable_dates():
    """Chaque épisode doit correspondre à une date proposée dans le sélecteur de relecture."""
    last = pd.Timestamp("2026-06-01")
    options = {f"{last - pd.DateOffset(months=k):%Y-%m}" for k in range(1, cfg.REPLAY_MONTHS + 1)}
    assert all(e["as_of"] in options and e["commodity"] in cfg.COMMODITIES for e in cfg.REPLAY_EPISODES)


def test_every_demo_episode_raises_alerts_that_were_confirmed(geo, source, basket):
    """Garantit que la démonstration ne peut pas « tomber à vide » : chaque épisode alerte, puis se confirme."""
    from services import prices as P

    by_date: dict[str, dict] = {}
    for ep in cfg.REPLAY_EPISODES:
        models = by_date.setdefault(
            ep["as_of"], {c: P.build_model(source, geo, c, pd.Timestamp(f"{ep['as_of']}-01")) for c in cfg.COMMODITIES})
        a = _alerts(models, basket, horizon=3)
        mine = a[(a["Produit"] == ep["commodity"]) & (a["Province"] == ep["province"])]
        assert len(mine) >= 1, ep["titre"]
        assert (mine["Constate"] == "Confirmée").any(), ep["titre"]
        assert mine["Confiance"].isin(cfg.CONFIDENCE_LEVELS).all()


# --------------------------------------------------------------------------- #
# Validation et journal
# --------------------------------------------------------------------------- #
def test_store_workflow_and_audit_log(tmp_path):
    store = engine.AlertStore(tmp_path)
    assert store.statuses() == {} and store.log().empty
    store.set_status("k1", "Validée", "Analyste SISAAP", "ok DPSA", "Hausse rapide · Mil · Kanem")
    store.set_status("k1", "Suspendue", "Analyste SISAAP", "à revérifier", "Hausse rapide · Mil · Kanem")
    state = store.statuses()
    assert state["k1"]["statut"] == "Suspendue" and state["k1"]["commentaire"] == "à revérifier"
    log = store.log()
    assert list(log["statut"]) == ["Suspendue", "Validée"]  # le plus récent d'abord ; aucune action n'est effacée
    store.reset()
    assert store.statuses() == {} and store.log().empty


def test_invalid_status_is_refused(tmp_path):
    with pytest.raises(ValueError, match="Statut inconnu"):
        engine.AlertStore(tmp_path).set_status("k", "Publiée", "x")


def test_with_status_defaults_to_pending(models, basket, tmp_path):
    a = _alerts(models, basket, "Pression accrue")
    store = engine.AlertStore(tmp_path)
    store.set_status(a["Cle"].iloc[0], "Validée", "Analyste SISAAP")
    out = engine.with_status(a, store)
    assert out["Statut"].iloc[0] == "Validée" and (out["Statut"].iloc[1:] == "À valider").all()
    assert out["Valide_par"].iloc[0] == "Analyste SISAAP"


def test_cluster_message_only_contains_validated_alerts(models, basket, tmp_path):
    a = _alerts(models, basket, "Pression accrue")
    store = engine.AlertStore(tmp_path)
    store.set_status(a["Cle"].iloc[0], "Validée", "Analyste SISAAP", "confirmé")
    out = engine.with_status(a, store)
    msg = engine.cluster_message(out[out["Statut"] == "Validée"], "2026-06", "Pression accrue", 3)
    assert a["Province"].iloc[0] in msg and "Validée par Analyste SISAAP" in msg
    assert "non validés" in msg and "WFP" in msg
    assert msg.count("•") == 1
    empty = engine.cluster_message(out.iloc[0:0], "2026-06", "Référence", 3)
    assert "Aucune alerte validée" in empty
