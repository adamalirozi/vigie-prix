"""Composante « céréales » du MEB (panier de dépenses minimum).

Le MEB complet (viande séchée, huile, légumineuses, sel, non-alimentaire…) dépend de la composition validée par le
Cluster Sécurité Alimentaire, sous l'égide du SISAAP. La démonstration calcule uniquement la ration céréalière,
d'après ``data/meb_composition.csv`` : remplacer ce fichier suffit à changer la composition (autres produits
suivis : ajouter une ligne dont le nom figure dans ``config.COMMODITIES``).

Coût mensuel par ménage = Σ (kg/personne/jour × prix du kg) × jours par mois × personnes par ménage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config as cfg
from services.prices import Model


def load_basket(path=cfg.MEB_CSV) -> pd.DataFrame:
    basket = pd.read_csv(path, encoding="utf-8")
    unknown = set(basket["produit"]) - set(cfg.COMMODITIES)
    if unknown:
        raise ValueError(f"Produits du MEB non suivis par l'application : {sorted(unknown)}")
    return basket


def kg_per_household_month(basket: pd.DataFrame) -> dict[str, float]:
    factor = cfg.HOUSEHOLD_SIZE * cfg.DAYS_PER_MONTH
    return {row.produit: row.kg_par_personne_jour * factor for row in basket.itertuples()}


def cost_table(models: dict[str, Model], basket: pd.DataFrame, scenario: str, horizon: int) -> pd.DataFrame:
    """Coût de la ration par province (FCFA/ménage/mois) : actuel, projeté, référence 5 ans."""
    kg = kg_per_household_month(basket)
    merged: pd.DataFrame | None = None
    for product in kg:
        t = models[product].province_table(scenario, horizon)[
            ["Code_ID", "Province", "Prix_Actuel", "Prix_Projete", "Ref_5ans", "Ecart_Moy5_Projete_pct"]
        ].rename(columns={"Prix_Actuel": f"a_{product}", "Prix_Projete": f"p_{product}", "Ref_5ans": f"r_{product}"})
        t = t.drop(columns=["Ecart_Moy5_Projete_pct"])
        merged = t if merged is None else merged.merge(t, on=["Code_ID", "Province"], how="inner")
    if merged is None or merged.empty:
        return pd.DataFrame()
    merged["Cout_Actuel"] = sum(qty * merged[f"a_{p}"] for p, qty in kg.items()).round(0)
    merged["Cout_Projete"] = sum(qty * merged[f"p_{p}"] for p, qty in kg.items()).round(0)
    ref = sum(qty * merged[f"r_{p}"] for p, qty in kg.items())  # NaN si une référence manque
    merged["Ref_5ans"] = ref.round(0)
    merged["Variation_pct"] = ((merged["Cout_Projete"] / merged["Cout_Actuel"] - 1) * 100).round(1)
    merged["Ecart_Moy5_pct"] = ((merged["Cout_Actuel"] / ref - 1) * 100).round(1)
    merged["Horizon"] = horizon
    keep = ["Code_ID", "Province", "Cout_Actuel", "Cout_Projete", "Variation_pct", "Ref_5ans", "Ecart_Moy5_pct", "Horizon"]
    return merged[keep + [c for c in merged.columns if c[:2] in ("a_", "p_")]]


def cost_path(models: dict[str, Model], basket: pd.DataFrame, province: str, scenario: str) -> list[float] | None:
    """Coût projeté à M+1..M+HORIZON pour une province (None si un produit manque)."""
    kg = kg_per_household_month(basket)
    total = np.zeros(cfg.HORIZON)
    for product, qty in kg.items():
        model = models[product]
        if province not in set(model.province_table(scenario)["Province"]):
            return None
        total += qty * np.array(model.province_series(province, scenario)["proj"])
    return total.round(0).tolist()
