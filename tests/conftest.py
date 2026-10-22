import numpy as np
import pandas as pd
import pytest

import config as cfg
from services import geo as geomod
from services import meb
from services import prices as P


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Aucun test n'écrit dans data/state : validations et journal vont dans un dossier temporaire."""
    monkeypatch.setattr(cfg, "STATE_DIR", tmp_path / "state")
    return tmp_path / "state"


@pytest.fixture(scope="session")
def geo():
    return geomod.load_geo(cfg.GEO_PROVINCES, cfg.GEO_DEPARTMENTS, cfg.GEO_SIMPLIFY_TOLERANCE)


@pytest.fixture(scope="session")
def source():
    return P.WfpPriceSource()


@pytest.fixture(scope="session")
def basket():
    return meb.load_basket()


@pytest.fixture(scope="session")
def models(geo, source):
    """Un modèle par produit au dernier relevé (construits une seule fois pour toute la session de tests)."""
    return {c: P.build_model(source, geo, c) for c in cfg.COMMODITIES}


@pytest.fixture(scope="session")
def model(models):
    return models["Mil"]


@pytest.fixture(scope="session")
def replay_models(geo, source):
    """Relecture : prévision faite en mars 2024 (avec les seules données disponibles à cette date)."""
    asof = pd.Timestamp("2024-03-01")
    return {c: P.build_model(source, geo, c, asof) for c in cfg.COMMODITIES}


@pytest.fixture
def seasonal_panel():
    """Panneau synthétique 2 séries × 10 ans, saisonnalité connue et sans bruit."""
    dates = pd.date_range("2014-01-01", "2023-12-01", freq="MS")
    shape = 1 + 0.2 * np.sin(2 * np.pi * (dates.month - 1) / 12)
    return pd.DataFrame({"A": 100 * shape, "B": 250 * shape}, index=dates)
