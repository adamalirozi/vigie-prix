"""Évaluation des prévisions : rétro-test hors échantillon et comparaison à la référence « aucun changement ».

Le dossier du projet exige qu'un modèle ne soit retenu que s'il fait mieux que la méthode simple : ce module
mesure donc, sur l'historique public, (1) l'erreur de la référence saisonnière et de la méthode « prix inchangé »,
(2) le biais, (3) la détection des hausses importantes (rappel, précision, avance en semaines).

Les résultats portent sur les données publiques WFP ; ils seront à recalculer sur les séries SIMPA après l'audit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config as cfg
from services import prices as P


def backtest(prov_panel: pd.DataFrame, last_obs: pd.Timestamp) -> pd.DataFrame:
    """Une ligne par horizon (1..HORIZON). Test sur les ``BACKTEST_TEST_MONTHS`` derniers mois.

    La saisonnalité est estimée UNIQUEMENT sur les données antérieures à la période de test.
    """
    panel = prov_panel.loc[:last_obs]
    cut = last_obs - pd.DateOffset(months=cfg.BACKTEST_TEST_MONTHS)
    _, idx_by_col = P.seasonal_indices(panel.loc[:cut], cut)
    rows = []
    for h in range(1, cfg.HORIZON + 1):
        naive_err, seas_err, signed, act, pred = [], [], [], [], []
        for col in panel.columns:
            s = panel[col]
            origins = s.index[(s.index > cut) & (s.index <= last_obs - pd.DateOffset(months=h))]
            now = s.loc[origins].to_numpy(float)
            then = s.shift(-h).loc[origins].to_numpy(float)
            ratio = np.array([P.seasonal_ratio(idx_by_col[col], d.month, h) for d in origins])
            ok = np.isfinite(now) & np.isfinite(then) & (now > 0) & (then > 0)
            now, then, ratio = now[ok], then[ok], ratio[ok]
            naive_err.append(np.abs(now / then - 1))
            seas_err.append(np.abs(now * ratio / then - 1))
            signed.append(now * ratio / then - 1)
            act.append(then / now - 1)
            pred.append(ratio - 1)
        naive_err, seas_err, signed = map(np.concatenate, (naive_err, seas_err, signed))
        act, pred = np.concatenate(act) * 100, np.concatenate(pred) * 100
        rise = act >= cfg.BACKTEST_RISE
        signal = pred >= cfg.BACKTEST_SIGNAL
        hits = rise & signal
        rows.append(
            {
                "Horizon": h,
                "Cas_testes": int(len(act)),
                "Erreur_prix_inchange_pct": round(float(naive_err.mean() * 100), 1),
                "Erreur_saisonnier_pct": round(float(seas_err.mean() * 100), 1),
                "Biais_saisonnier_pct": round(float(signed.mean() * 100), 1),
                "Hausses_importantes": int(rise.sum()),
                "Hausses_detectees_pct": round(float(hits.sum() / max(rise.sum(), 1) * 100), 0),
                "Precision_signal_pct": round(float(hits.sum() / max(signal.sum(), 1) * 100), 0),
                "Part_hausses_reelles_pct": round(float(rise.mean() * 100), 0),
                "Part_hausses_annoncees_pct": round(float(signal.mean() * 100), 0),
                "Avance_semaines": round(h * cfg.WEEKS_PER_MONTH, 0),
            }
        )
    return pd.DataFrame(rows)


def verdict(bt: pd.DataFrame) -> str:
    """Phrase de synthèse honnête, construite à partir des résultats."""
    last = bt.iloc[-1]
    gain = last["Erreur_prix_inchange_pct"] - last["Erreur_saisonnier_pct"]
    detect = last["Hausses_detectees_pct"]
    if gain > 1:
        compare = f"La référence saisonnière réduit l'erreur à 3 mois de {gain:.1f} points par rapport au prix inchangé"
    elif gain > -1:
        compare = "À 3 mois, la référence saisonnière est à peu près aussi précise que « prix inchangé »"
    else:
        compare = "À 3 mois, la référence saisonnière est moins précise que « prix inchangé »"
    return (
        f"{compare} ({last['Erreur_saisonnier_pct']:.1f} % contre {last['Erreur_prix_inchange_pct']:.1f} %). "
        f"Elle signale {detect:.0f} % des hausses de {cfg.BACKTEST_RISE:.0f} % ou plus à 3 mois "
        f"(précision du signal : {last['Precision_signal_pct']:.0f} %). "
        "C'est le point de comparaison que les niveaux 2 et 3 devront battre."
    )


def pilot_markets(markets: pd.DataFrame, n: int = cfg.PILOT_MARKETS_N) -> pd.DataFrame:
    """Marchés pilotes proposés : le meilleur marché actif de chaque province (complétude puis récence), puis les
    ``n`` meilleurs de cette présélection. Critère : fiabilité des relevés, avec au plus un marché par province."""
    active = markets[markets["Actif"]].copy()
    if active.empty:
        return active
    active["_rec"] = active["Derniere_Obs"].astype("int64")
    best = (active.sort_values(["Completude_pct", "_rec"], ascending=False)
            .groupby("Province", as_index=False).head(1))
    return best.sort_values(["Completude_pct", "_rec"], ascending=False).head(n).drop(columns="_rec") \
        .reset_index(drop=True)
