"""Contexte d'une exécution : tous les choix de l'utilisateur, passés tels quels aux vues."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Ctx:
    commodity: str
    scenario: str
    horizon: int
    province: str
    seuil_pct: int  # seuil d'alerte de prix : écart à la moyenne 5 ans (%)
    meb_seuil: int  # seuil MEB : FCFA / ménage / mois
    as_of: str  # « » = dernier relevé ; « AAAA-MM » = relecture
    dk: str  # version des données
    role: str
    offline: bool

    @property
    def is_analyst(self) -> bool:
        return self.role == "Analyste SISAAP"

    @property
    def as_of_ts(self) -> pd.Timestamp | None:
        return pd.Timestamp(f"{self.as_of}-01") if self.as_of else None
