import pandas as pd
import pytest

import config as cfg
from services import meb


def test_basket_loads_and_matches_tracked_products(basket):
    assert set(basket["produit"]) <= set(cfg.COMMODITIES)
    assert (basket["kg_par_personne_jour"] > 0).all() and basket["statut"].str.contains("valider").all()


def test_unknown_product_is_rejected(tmp_path):
    bad = tmp_path / "meb.csv"
    bad.write_text("produit,kg_par_personne_jour,statut,source\nQuinoa,0.1,x,y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Quinoa"):
        meb.load_basket(bad)


def test_monthly_quantities(basket):
    kgm = meb.kg_per_household_month(basket)
    assert kgm["Mil"] == pytest.approx(0.15 * cfg.HOUSEHOLD_SIZE * cfg.DAYS_PER_MONTH)


def test_cost_formula_matches_a_manual_calculation(models, basket):
    table = meb.cost_table(models, basket, "Référence", 3).set_index("Province")
    province = "Kanem"
    kgm = meb.kg_per_household_month(basket)
    manual = sum(kgm[p] * models[p].province_table("Référence", 3).set_index("Province").loc[province, "Prix_Actuel"]
                 for p in kgm)
    assert table.loc[province, "Cout_Actuel"] == pytest.approx(manual, abs=1)
    assert (table["Cout_Projete"] > 0).all() and table["Horizon"].eq(3).all()


def test_cost_path_ends_on_the_table_value(models, basket):
    table = meb.cost_table(models, basket, "Pression accrue", 3).set_index("Province")
    path = meb.cost_path(models, basket, "Kanem", "Pression accrue")
    assert len(path) == cfg.HORIZON and path[2] == pytest.approx(table.loc["Kanem", "Cout_Projete"], abs=2)
    assert meb.cost_path(models, basket, "Tibesti", "Référence") is None  # pas de prix récent


def test_province_missing_a_product_is_left_out(models, basket):
    table = meb.cost_table(models, basket, "Référence", 3)
    assert "Tibesti" not in set(table["Province"]) and isinstance(table, pd.DataFrame)
