"""Alertes : génération, niveau de confiance, facteurs, validation par les analystes et message au Cluster.

Chaque alerte est une *proposition* : elle ne devient une alerte publiable qu'après validation d'un analyste du
SISAAP (statut « Validée »). Les validations sont journalisées. Les seuils sont ceux choisis dans l'interface ;
dans la démonstration ils sont « non validés par le SISAAP ».
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg
from services import meb
from services.prices import Model, seasonal_ratio
from ui.formatting import month_label_long

TYPES = ("Hausse rapide", "Seuil de prix", "Seuil MEB")


# --------------------------------------------------------------------------- #
# Confiance
# --------------------------------------------------------------------------- #
def confidence(n_markets: int, completeness: float, month_k: int, band_halfwidth_pct: float,
               lag_months: int = 0) -> tuple[str, list[str]]:
    """Niveau de confiance (Élevée / Moyenne / Faible) et ses motifs.

    Points : marchés actifs (≥3 : 2, 2 : 1) ; complétude des relevés (≥80 % : 2, ≥60 % : 1) ;
    horizon (M+1 : 2, M+2 : 1) ; intervalle (± ≤ 12 % : 1) ; retard de relevé (−1 si > 1 mois).
    Total ≥ 6 : Élevée ; ≥ 4 : Moyenne ; sinon Faible.
    """
    pts = (2 if n_markets >= 3 else 1 if n_markets == 2 else 0)
    pts += 2 if completeness >= cfg.RELIABILITY_GOOD else 1 if completeness >= 60 else 0
    pts += {1: 2, 2: 1}.get(month_k, 0)
    pts += 1 if band_halfwidth_pct <= 12 else 0
    pts -= 1 if lag_months > 1 else 0
    level = "Élevée" if pts >= 6 else "Moyenne" if pts >= 4 else "Faible"
    reasons = [f"{n_markets} marché(s) actif(s)", f"{completeness:.0f} % des 24 derniers mois relevés",
               f"horizon M+{month_k}", f"intervalle ± {band_halfwidth_pct:.0f} %"]
    if lag_months > 1:
        reasons.append(f"dernier relevé il y a {lag_months} mois")
    return level, reasons


def _factors(model: Model, province: str, k: int, scenario: str, row: pd.Series) -> list[str]:
    season = (seasonal_ratio(model.seasonal_prov[province], model.last_obs.month, k) - 1) * 100
    out = [f"Saisonnalité : {season:+.1f} % attendus d'ici {month_label_long(model.dates_proj[k - 1])}"]
    if pd.notna(row["Ecart_Moy5_pct"]):
        out.append(f"Prix actuel : {row['Ecart_Moy5_pct']:+.0f} % par rapport à la moyenne des 5 dernières années")
    if pd.notna(row["Var_1m_pct"]) and pd.notna(row["YoY_pct"]):
        out.append(f"Évolution récente : {row['Var_1m_pct']:+.0f} % sur 1 mois, {row['YoY_pct']:+.0f} % sur 1 an")
    if cfg.SCENARIOS[scenario]:
        out.append(f"Scénario « {scenario} » : {cfg.SCENARIOS[scenario] * 100:+.0f} % par mois")
    out.append("Facteurs externes (carburant, pluie, conflit, marchés frontaliers) : non connectés dans la démonstration")
    return out


# --------------------------------------------------------------------------- #
# Génération
# --------------------------------------------------------------------------- #
def generate(models: dict[str, Model], basket: pd.DataFrame, scenario: str, horizon: int, seuil_pct: float,
             meb_seuil: float) -> pd.DataFrame:
    """Propose les alertes pour tous les produits et la composante céréales du MEB."""
    rows = []
    ref_model = next(iter(models.values()))
    as_label = f"{ref_model.last_obs:%Y-%m}"
    for product, model in models.items():
        table = model.province_table(scenario, horizon).set_index("Province")
        for province, row in table.iterrows():
            s = model.province_series(province, scenario)
            lag = (model.last_obs.year - row["Derniere_Obs"].year) * 12 + model.last_obs.month - row["Derniere_Obs"].month
            checks = []
            for k in range(1, horizon + 1):
                price_k = s["proj"][k - 1]
                var_k = (price_k / row["Prix_Actuel"] - 1) * 100
                ref_k = s["ref"][cfg.HISTORY_MONTHS + k - 1]
                dev_k = (price_k / ref_k - 1) * 100 if pd.notna(ref_k) and ref_k > 0 else np.nan
                checks.append((k, price_k, var_k, dev_k))
            for kind, test in (
                ("Hausse rapide", lambda k, p, v, d: v >= cfg.ALERT_MID),
                ("Seuil de prix", lambda k, p, v, d: pd.notna(d) and d > seuil_pct),
            ):
                hit = next((c for c in checks if test(*c)), None)
                if hit is None:
                    continue
                k, price_k, var_k, dev_k = hit
                lo, hi = model.band[k - 1]
                level, reasons = confidence(int(row["Nb_Marches"]), float(row["Completude_pct"]), k,
                                            (hi - lo) / 2 * 100, max(lag, 0))
                actual = s["actual"][k - 1] if s["actual"] else np.nan
                rows.append(
                    {
                        "Cle": f"{kind}|{product}|{province}|{as_label}",
                        "Type": kind, "Produit": product, "Province": province, "Premier_Mois_k": k,
                        "Premier_Mois": model.dates_proj[k - 1],
                        "Valeur_Projetee": round(price_k, 1), "Unite": cfg.UNIT,
                        "Variation_pct": round(var_k, 1), "Ecart_Moy5_Projete_pct": round(dev_k, 1) if pd.notna(dev_k) else np.nan,
                        "Seuil": f"+{seuil_pct:.0f} % vs moyenne 5 ans" if kind == "Seuil de prix"
                        else f"hausse ≥ +{cfg.ALERT_MID:.0f} % d'ici M+{k}",
                        "Confiance": level, "Motifs_confiance": reasons,
                        "Facteurs": _factors(model, province, k, scenario, row),
                        "Constate_pct": round((actual / row["Prix_Actuel"] - 1) * 100, 1) if pd.notna(actual) else np.nan,
                        "Constate": _outcome(kind, actual, row["Prix_Actuel"], s, k, seuil_pct),
                    }
                )
    # Seuil MEB (composante céréales)
    cost_now = meb.cost_table(models, basket, scenario, horizon).set_index("Province") if len(models) else None
    if cost_now is not None and not cost_now.empty:
        for province, crow in cost_now.iterrows():
            path = meb.cost_path(models, basket, province, scenario)
            if path is None:
                continue
            k = next((i + 1 for i, c in enumerate(path[:horizon]) if c > meb_seuil), None)
            if k is None:
                continue
            per_model = [(m, m.province_table(scenario, horizon).set_index("Province").loc[province]) for m in
                         (models[p] for p in basket["produit"])]
            n_markets = min(int(r["Nb_Marches"]) for _, r in per_model)
            compl = min(float(r["Completude_pct"]) for _, r in per_model)
            half = max((m.band[k - 1][1] - m.band[k - 1][0]) / 2 * 100 for m, _ in per_model)
            level, reasons = confidence(n_markets, compl, k, half)
            first_model, first_row = per_model[0]
            real = _realised_cost(models, basket, province, k)
            rows.append(
                {
                    "Cle": f"Seuil MEB|MEB céréales|{province}|{as_label}",
                    "Type": "Seuil MEB", "Produit": "MEB (céréales)", "Province": province, "Premier_Mois_k": k,
                    "Premier_Mois": first_model.dates_proj[k - 1],
                    "Valeur_Projetee": path[k - 1], "Unite": "FCFA/ménage/mois",
                    "Variation_pct": round((path[k - 1] / crow["Cout_Actuel"] - 1) * 100, 1),
                    "Ecart_Moy5_Projete_pct": np.nan,
                    "Seuil": f"> {meb_seuil:,.0f} FCFA/ménage/mois".replace(",", "\u202f"),
                    "Confiance": level, "Motifs_confiance": reasons,
                    "Facteurs": _factors(first_model, province, k, scenario, first_row),
                    "Constate_pct": round((real / crow["Cout_Actuel"] - 1) * 100, 1) if pd.notna(real) else np.nan,
                    "Constate": ("n.d." if pd.isna(real) else "Confirmée" if real > meb_seuil else "Non confirmée")
                    if first_model.is_replay else "",
                }
            )
    cols = ["Cle", "Type", "Produit", "Province", "Premier_Mois_k", "Premier_Mois", "Valeur_Projetee", "Unite",
            "Variation_pct", "Ecart_Moy5_Projete_pct", "Seuil", "Confiance", "Motifs_confiance", "Facteurs",
            "Constate_pct", "Constate"]
    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    order = {"Élevée": 0, "Moyenne": 1, "Faible": 2}
    return out.assign(_c=out["Confiance"].map(order)).sort_values(["_c", "Variation_pct"], ascending=[True, False]) \
        .drop(columns="_c").reset_index(drop=True)


def _outcome(kind: str, actual: float, current: float, series: dict, k: int, seuil_pct: float) -> str:
    """En mode relecture : l'alerte s'est-elle réalisée ? (vide hors relecture)."""
    if not series["actual"]:
        return ""
    if pd.isna(actual):
        return "n.d."
    if kind == "Hausse rapide":
        return "Confirmée" if (actual / current - 1) * 100 >= cfg.ALERT_MID else "Non confirmée"
    ref_k = series["ref"][cfg.HISTORY_MONTHS + k - 1]
    if pd.isna(ref_k) or ref_k <= 0:
        return "n.d."
    return "Confirmée" if (actual / ref_k - 1) * 100 > seuil_pct else "Non confirmée"


def _realised_cost(models: dict[str, Model], basket: pd.DataFrame, province: str, k: int) -> float:
    kg = meb.kg_per_household_month(basket)
    total = 0.0
    for product, qty in kg.items():
        actual = models[product].prov_actual
        if province not in actual or len(actual) < k or pd.isna(actual[province].iloc[k - 1]):
            return np.nan
        total += qty * float(actual[province].iloc[k - 1])
    return total


# --------------------------------------------------------------------------- #
# Validation et journal
# --------------------------------------------------------------------------- #
class AlertStore:
    """Statuts des alertes (JSON) et journal des actions (JSON Lines). Aucun accès réseau."""

    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else cfg.STATE_DIR
        self._state = self.dir / "alerts_state.json"
        self._log = self.dir / "audit_log.jsonl"

    def statuses(self) -> dict[str, dict]:
        if not self._state.exists():
            return {}
        return json.loads(self._state.read_text(encoding="utf-8"))

    def set_status(self, key: str, status: str, user: str, comment: str = "", label: str = "") -> None:
        if status not in cfg.ALERT_STATUSES:
            raise ValueError(f"Statut inconnu : {status}")
        self.dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now().isoformat(timespec="seconds")
        state = self.statuses()
        state[key] = {"statut": status, "par": user, "le": now, "commentaire": comment}
        self._state.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        with self._log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"le": now, "par": user, "cle": key, "alerte": label, "statut": status,
                                 "commentaire": comment}, ensure_ascii=False) + "\n")

    def log(self) -> pd.DataFrame:
        if not self._log.exists():
            return pd.DataFrame(columns=["le", "par", "cle", "alerte", "statut", "commentaire"])
        lines = [json.loads(x) for x in self._log.read_text(encoding="utf-8").splitlines() if x.strip()]
        return pd.DataFrame(lines).iloc[::-1].reset_index(drop=True)

    def reset(self) -> None:
        for path in (self._state, self._log):
            path.unlink(missing_ok=True)


def with_status(alerts: pd.DataFrame, store: AlertStore) -> pd.DataFrame:
    state = store.statuses()
    out = alerts.copy()
    out["Statut"] = [state.get(k, {}).get("statut", "À valider") for k in out["Cle"]]
    out["Valide_par"] = [state.get(k, {}).get("par", "") for k in out["Cle"]]
    out["Date_decision"] = [state.get(k, {}).get("le", "") for k in out["Cle"]]
    out["Commentaire"] = [state.get(k, {}).get("commentaire", "") for k in out["Cle"]]
    return out


def cluster_message(validated: pd.DataFrame, period: str, scenario: str, horizon: int) -> str:
    """Message prêt à relire à l'attention du Cluster Sécurité Alimentaire (alertes validées uniquement)."""
    lines = [
        "Objet : Vigie Prix — alertes validées par le SISAAP",
        "",
        f"Période de référence : {period} · horizon M+{horizon} · scénario « {scenario} »",
        "",
    ]
    if validated.empty:
        lines.append("Aucune alerte validée à ce jour.")
    for r in validated.itertuples():
        lines += [
            f"• {r.Type} — {r.Produit} — {r.Province}",
            f"  Premier dépassement prévu : {month_label_long(r.Premier_Mois)} (M+{r.Premier_Mois_k}) ; "
            f"valeur projetée : {r.Valeur_Projetee:,.0f} {r.Unite}".replace(",", "\u202f"),
            f"  Seuil : {r.Seuil} ; confiance : {r.Confiance}",
            f"  Validée par {r.Valide_par} le {r.Date_decision[:10]}" + (f" — {r.Commentaire}" if r.Commentaire else ""),
            "",
        ]
    lines += [
        "Précautions : projections indicatives issues d'une référence saisonnière sur données publiques WFP ; "
        "seuils non validés tant que le SISAAP ne les a pas fixés ; facteurs externes (carburant, pluie, conflit) "
        "non intégrés à ce stade.",
        "Source : WFP Price Database (HDX).",
    ]
    return "\n".join(lines)
