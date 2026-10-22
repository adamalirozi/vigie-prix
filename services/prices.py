"""Modèle de prix à partir des relevés de marché (WFP / HDX).

Aucune dépendance à Streamlit : tout est testable en isolation.

Chaîne de calcul
----------------
1. ``WfpPriceSource``  : prix mensuels par marché, en FCFA/kg, pour un produit.
2. ``build_model``     : rattache les marchés aux provinces / départements, comble les petits
                         trous, agrège (médiane des marchés) et estime la saisonnalité,
                         la moyenne de référence sur 5 ans et l'incertitude de la projection.
3. ``Model``           : tables et séries prêtes pour l'affichage, pour un scénario donné.

Principes
---------
- Une seule série par province (et par département) alimente cartes, tableaux, KPI et graphiques.
- « Prix actuel » = dernier prix valide dans les ``MAX_STALE_MONTHS`` derniers mois ; au-delà la
  province n'a pas de prix actuel (ex. Tibesti, dont le suivi s'arrête en août 2024).
- Un département sans marché prend le prix du marché actif le plus proche (source indiquée).
- La date de référence est la dernière observation des données, jamais la date du jour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

import config as cfg
from services.geo import GeoData, haversine_km

# --------------------------------------------------------------------------- #
# Dates et classification
# --------------------------------------------------------------------------- #


def month_start(ts) -> pd.Timestamp:
    return pd.Timestamp(ts).to_period("M").to_timestamp()


def month_range_ending(end: pd.Timestamp, periods: int) -> list[pd.Timestamp]:
    return list(pd.date_range(end=end, periods=periods, freq="MS"))


def projection_dates(last_obs: pd.Timestamp, steps: int = cfg.HORIZON) -> list[pd.Timestamp]:
    return list(pd.date_range(start=last_obs + pd.offsets.MonthBegin(1), periods=steps, freq="MS"))


def classify_vigilance(variation_pct: float, horizon: int = cfg.HORIZON) -> str:
    """Niveau de vigilance ; les seuils (définis pour 3 mois) sont proportionnels à l'horizon."""
    scale = horizon / cfg.HORIZON
    if variation_pct >= cfg.ALERT_HIGH * scale:
        return "Élevé"
    if variation_pct >= cfg.ALERT_MID * scale:
        return "Modéré"
    return "Faible"


def classify_gap(gap_pct: float) -> str:
    if gap_pct >= cfg.GAP_THRESHOLD:
        return "Au-dessus du niveau provincial"
    if gap_pct <= -cfg.GAP_THRESHOLD:
        return "En dessous du niveau provincial"
    return "Proche du niveau provincial"


# --------------------------------------------------------------------------- #
# Source de données
# --------------------------------------------------------------------------- #


class PriceSource(Protocol):
    """Contrat à respecter par une source (fichier WFP, base SIMPA, API…)."""

    def version(self) -> str:
        """Identifiant de version des données (invalide le cache quand les données changent)."""

    def markets(self) -> pd.DataFrame:
        """Colonnes : market_id, Marché, admin1, lat, lon (marchés géolocalisés uniquement)."""

    def monthly_prices(self, commodity: str) -> pd.DataFrame:
        """Prix FCFA/kg : index = mois (début de mois, continu), colonnes = market_id."""


class WfpPriceSource:
    """Fichiers « Food Prices » et « Markets » du WFP pour le Tchad (export HDX)."""

    def __init__(self, prices_csv=cfg.PRICES_CSV, markets_csv=cfg.MARKETS_CSV):
        self._prices_csv, self._markets_csv = prices_csv, markets_csv
        self._raw: pd.DataFrame | None = None

    def version(self) -> str:
        return f"{self._prices_csv.stat().st_mtime_ns}-{self._markets_csv.stat().st_mtime_ns}"

    def markets(self) -> pd.DataFrame:
        m = pd.read_csv(self._markets_csv, encoding="utf-8")
        m = m.dropna(subset=["latitude", "longitude"])
        m = m.rename(columns={"market": "Marché", "latitude": "lat", "longitude": "lon"})
        return m[["market_id", "Marché", "admin1", "lat", "lon"]].reset_index(drop=True)

    def _load(self) -> pd.DataFrame:
        if self._raw is None:
            wanted = {name for names in cfg.COMMODITIES.values() for name in names}
            df = pd.read_csv(
                self._prices_csv, usecols=["date", "market_id", "commodity", "unit", "price"], parse_dates=["date"]
            )
            df = df[(df["unit"] == "KG") & df["commodity"].isin(wanted)].copy()
            df["Date"] = df["date"].dt.to_period("M").dt.to_timestamp()
            self._raw = df[["Date", "market_id", "commodity", "price"]]
        return self._raw

    def monthly_prices(self, commodity: str) -> pd.DataFrame:
        raw, merged = self._load(), None
        for name in cfg.COMMODITIES[commodity]:  # par ordre de priorité
            wide = raw[raw["commodity"] == name].pivot_table(
                index="Date", columns="market_id", values="price", aggfunc="mean"
            )
            merged = wide if merged is None else merged.combine_first(wide)
        full = pd.date_range(merged.index.min(), merged.index.max(), freq="MS")
        return merged.reindex(full).sort_index(axis=1)


# --------------------------------------------------------------------------- #
# Statistiques : saisonnalité, projection, incertitude, référence 5 ans
# --------------------------------------------------------------------------- #


def seasonal_indices(panel: pd.DataFrame, last_obs: pd.Timestamp) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Indices saisonniers (12 valeurs, moyenne 1) : national, puis un par série.

    Pour chaque série et chaque année complète (≥ 9 mois), prix du mois ÷ moyenne de l'année ;
    médiane depuis ``SEASONAL_FIRST_YEAR``. L'indice d'une province mélange sa propre saisonnalité
    (poids ``SEASONAL_OWN_WEIGHT``) et la saisonnalité nationale, pour rester stable sur les séries courtes.
    """
    last_full_year = last_obs.year if last_obs.month == 12 else last_obs.year - 1
    sub = panel[(panel.index.year >= cfg.SEASONAL_FIRST_YEAR) & (panel.index.year <= last_full_year)]
    by_year = sub.groupby(sub.index.year)
    norm = (sub / by_year.transform("mean")).where(by_year.transform("count") >= 9)

    def _profile(values: pd.Series) -> pd.Series:
        prof = values.dropna().groupby(values.dropna().index.month).median().reindex(range(1, 13))
        return prof.interpolate().bfill().ffill()

    stacked = norm.stack()
    if stacked.empty:
        return np.ones(12), {c: np.ones(12) for c in panel.columns}
    national = stacked.groupby(stacked.index.get_level_values(0).month).median().reindex(range(1, 13))
    national = national.interpolate().bfill().ffill().fillna(1.0)
    national = national / national.mean()

    per_series = {}
    w = cfg.SEASONAL_OWN_WEIGHT
    for col in panel.columns:
        s = norm[col].dropna()
        if len(s) >= cfg.SEASONAL_MIN_OBS:
            own = _profile(norm[col])
            mixed = (1 - w) * national + w * (own / own.mean())
            per_series[col] = (mixed / mixed.mean()).to_numpy()
        else:
            per_series[col] = national.to_numpy()
    return national.to_numpy(), per_series


def seasonal_ratio(idx: np.ndarray, month: int, h: int) -> float:
    """Rapport saisonnier entre le mois ``month`` + h et le mois ``month``."""
    return float(idx[(month - 1 + h) % 12] / idx[month - 1])


def project(current: float, origin: pd.Timestamp, idx: np.ndarray, drift: float) -> list[float]:
    """Prix projetés à M+1..M+HORIZON : saisonnalité × dérive mensuelle du scénario."""
    return [
        float(current * seasonal_ratio(idx, origin.month, h) * (1 + drift) ** h) for h in range(1, cfg.HORIZON + 1)
    ]


def forecast_band(
    panel: pd.DataFrame, idx_by_col: dict[str, np.ndarray], last_obs: pd.Timestamp
) -> list[tuple[float, float]]:
    """Intervalle empirique (multiplicateurs bas/haut) de la projection saisonnière à M+1..M+HORIZON.

    Rétro-test sur les ``BACKTEST_MONTHS`` derniers mois : erreur relative (log) entre projection
    et réalisé, sur toutes les provinces ; quantiles ``BAND_QUANTILES``. La saisonnalité étant
    estimée sur la même période, l'intervalle est un peu optimiste.
    """
    start = last_obs - pd.DateOffset(months=cfg.BACKTEST_MONTHS)
    band = []
    for h in range(1, cfg.HORIZON + 1):
        origins = panel.index[(panel.index >= start) & (panel.index <= last_obs - pd.DateOffset(months=h))]
        errors = []
        for col in panel.columns:
            ratios = np.array([seasonal_ratio(idx_by_col[col], d.month, h) for d in origins])
            pred = panel.loc[origins, col].to_numpy(float) * ratios
            actual = panel[col].shift(-h).loc[origins].to_numpy(float)
            with np.errstate(invalid="ignore", divide="ignore"):
                e = np.log(actual / pred)
            errors.append(e[np.isfinite(e)])
        err = np.concatenate(errors) if errors else np.array([])
        if len(err) < 30:
            band.append((0.9, 1.1))
            continue
        lo, hi = np.quantile(err, cfg.BAND_QUANTILES[0]), np.quantile(err, cfg.BAND_QUANTILES[1])
        band.append((float(np.exp(min(lo, 0.0))), float(np.exp(max(hi, 0.0)))))
    return band


def five_year_reference(panel: pd.DataFrame) -> pd.DataFrame:
    """Moyenne du même mois sur les ``REFERENCE_YEARS`` années précédentes (≥ ``REFERENCE_MIN_YEARS``)."""
    stack = np.stack([panel.shift(12 * k).to_numpy(float) for k in range(1, cfg.REFERENCE_YEARS + 1)])
    count = np.sum(~np.isnan(stack), axis=0)
    total = np.nansum(stack, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(count >= cfg.REFERENCE_MIN_YEARS, total / count, np.nan)
    return pd.DataFrame(mean, index=panel.index, columns=panel.columns)


def _last_valid(series: pd.Series, cutoff: pd.Timestamp) -> tuple[float, pd.Timestamp | None]:
    """Dernier prix valide et sa date ; (NaN, date) si plus ancien que ``cutoff``."""
    valid = series.dropna()
    if valid.empty:
        return np.nan, None
    date = valid.index[-1]
    return (float(valid.iloc[-1]) if date >= cutoff else np.nan), date


# --------------------------------------------------------------------------- #
# Modèle
# --------------------------------------------------------------------------- #


@dataclass
class Model:
    """Données préparées pour un produit ; fournit les tables par scénario."""

    commodity: str
    last_obs: pd.Timestamp
    dates_hist: list[pd.Timestamp]
    dates_proj: list[pd.Timestamp]
    provinces: pd.DataFrame  # Code_ID, Province
    departments: pd.DataFrame  # Code_ID, Département, Province, lon, lat
    markets: pd.DataFrame  # marchés géolocalisés, rattachés, avec prix actuel
    market_panel: pd.DataFrame  # Date × market_id (FCFA/kg, trous comblés)
    prov_panel: pd.DataFrame  # Date × Province (+ HORIZON mois vides)
    prov_ref: pd.DataFrame  # moyenne 5 ans, mêmes axes
    dept_panel: pd.DataFrame  # Date × Dept_ID (+ HORIZON mois vides)
    dept_ref: pd.DataFrame
    dept_info: pd.DataFrame  # Dept_ID, Source_Prix, Nb_Marches, Marche_ref, Distance_km
    seasonal: np.ndarray  # indice national
    seasonal_prov: dict[str, np.ndarray]  # indice par province
    band: list[tuple[float, float]]
    market_ref: pd.DataFrame  # moyenne 5 ans par marché (mêmes axes que market_panel étendu)
    prov_actual: pd.DataFrame  # prix réalisés APRÈS la date de prévision (relecture) ; vide sinon
    as_of: pd.Timestamp | None  # date de prévision demandée (None = dernier relevé)
    data_last_obs: pd.Timestamp  # dernier relevé disponible dans les données
    n_outliers: int = 0  # relevés isolés écartés par le nettoyage
    sync_months: dict = field(default_factory=dict)  # mois synchronisés écartés → médiane des écarts

    @property
    def is_replay(self) -> bool:
        return self.last_obs < self.data_last_obs

    # -- utilitaires ---------------------------------------------------------
    @property
    def cutoff(self) -> pd.Timestamp:
        return self.last_obs - pd.DateOffset(months=cfg.MAX_STALE_MONTHS)

    @staticmethod
    def _drift(scenario: str) -> float:
        return cfg.SCENARIOS[scenario]

    def _hist(self, panel: pd.DataFrame, key: str) -> list[float]:
        return panel.loc[self.dates_hist, key].tolist()

    # -- provinces -----------------------------------------------------------
    def province_table(self, scenario: str, horizon: int = cfg.HORIZON) -> pd.DataFrame:
        """Une ligne par province disposant d'un prix actuel ; projection à ``horizon`` mois."""
        drift, rows = self._drift(scenario), []
        h_date = self.dates_proj[horizon - 1]
        for code, name in zip(self.provinces["Code_ID"], self.provinces["Province"], strict=True):
            current, last_date = _last_valid(self.prov_panel[name], self.cutoff)
            if np.isnan(current):
                continue
            path = project(current, self.last_obs, self.seasonal_prov[name], drift)
            proj = path[horizon - 1]
            variation = (proj / current - 1) * 100
            ref_now = self.prov_ref.loc[self.last_obs, name]
            ref_end = self.prov_ref.loc[h_date, name]
            prev = self.prov_panel.loc[self.last_obs - pd.DateOffset(months=1), name]
            year_ago = self.prov_panel.loc[self.last_obs - pd.DateOffset(years=1), name]
            spark = pd.Series(self._hist(self.prov_panel, name)).ffill().bfill().tolist() + path
            active = self.markets[(self.markets["Province"] == name) & self.markets["Actif"]]
            rows.append(
                {
                    "Code_ID": code,
                    "Province": name,
                    "Prix_Actuel": round(current, 1),
                    "Prix_Projete": round(proj, 1),
                    "Variation_pct": round(variation, 1),
                    "Vigilance": classify_vigilance(variation, horizon),
                    "Var_1m_pct": round((current / prev - 1) * 100, 1) if pd.notna(prev) else np.nan,
                    "YoY_pct": round((current / year_ago - 1) * 100, 1) if pd.notna(year_ago) else np.nan,
                    "Ref_5ans": round(ref_now, 1) if pd.notna(ref_now) else np.nan,
                    "Ecart_Moy5_pct": round((current / ref_now - 1) * 100, 1) if pd.notna(ref_now) else np.nan,
                    "Ecart_Moy5_Projete_pct": round((proj / ref_end - 1) * 100, 1) if pd.notna(ref_end) else np.nan,
                    "Mois_Pic": self.dates_proj[int(np.argmax(path))],
                    "Nb_Marches": len(active),
                    "Completude_pct": round(float(active["Completude_pct"].mean()), 0) if len(active) else np.nan,
                    "Derniere_Obs": last_date,
                    "Sparkline": spark,
                    "Horizon": horizon,
                    "Scénario": scenario,
                }
            )
        return pd.DataFrame(rows)

    def missing_provinces(self) -> pd.DataFrame:
        """Provinces sans prix actuel, avec la date de leur dernière observation."""
        rows = []
        for name in self.provinces["Province"]:
            current, last_date = _last_valid(self.prov_panel[name], self.cutoff)
            if np.isnan(current):
                rows.append({"Province": name, "Derniere_Obs": last_date if last_date is not None else pd.NaT})
        return pd.DataFrame(rows, columns=["Province", "Derniere_Obs"])

    def province_series(self, province: str, scenario: str) -> dict:
        """Historique, projection, intervalle, référence 5 ans (pour le graphique de tendance)."""
        current, _ = _last_valid(self.prov_panel[province], self.cutoff)
        path = project(current, self.last_obs, self.seasonal_prov[province], self._drift(scenario))
        all_dates = self.dates_hist + self.dates_proj
        return {
            "hist": self._hist(self.prov_panel, province),
            "proj": path,
            "band": [(p * lo, p * hi) for p, (lo, hi) in zip(path, self.band, strict=True)],
            "ref": self.prov_ref.loc[all_dates, province].tolist(),
            "actual": self.prov_actual[province].reindex(self.dates_proj).tolist() if self.is_replay else [],
        }

    def deviation_matrix(self, scenario: str) -> pd.DataFrame:
        """Écart (%) à la moyenne 5 ans : provinces × (historique + projection)."""
        all_dates = self.dates_hist + self.dates_proj
        rows = {}
        for name in self.province_table(scenario)["Province"]:
            s = self.province_series(name, scenario)
            values = np.array(s["hist"] + s["proj"], dtype=float)
            ref = np.array(s["ref"], dtype=float)
            with np.errstate(invalid="ignore", divide="ignore"):
                rows[name] = (values / ref - 1) * 100
        return pd.DataFrame(rows, index=all_dates).T

    # -- départements --------------------------------------------------------
    def department_table(self, scenario: str, horizon: int = cfg.HORIZON) -> pd.DataFrame:
        """Départements avec prix actuel (local ou marché le plus proche) et province renseignée."""
        prov = self.province_table(scenario, horizon).set_index("Province")
        drift, rows = self._drift(scenario), []
        info = self.dept_info.set_index("Dept_ID")
        for d in self.departments.itertuples(index=False):
            if d.Province not in prov.index:
                continue
            current, _ = _last_valid(self.dept_panel[d.Code_ID], self.cutoff)
            if np.isnan(current):
                continue
            proj = project(current, self.last_obs, self.seasonal_prov[d.Province], drift)[horizon - 1]
            gap = (proj / prov.loc[d.Province, "Prix_Projete"] - 1) * 100
            ref_now = self.dept_ref.loc[self.last_obs, d.Code_ID]
            variation = (proj / current - 1) * 100
            rows.append(
                {
                    "Code_ID": d.Code_ID,
                    "Département": d.Département,
                    "Province": d.Province,
                    "Prix_Actuel": round(current, 1),
                    "Prix_Projete": round(proj, 1),
                    "Variation_pct": round(variation, 1),
                    "Ecart_Parent_pct": round(gap, 1),
                    "Ecart_Moy5_pct": round((current / ref_now - 1) * 100, 1) if pd.notna(ref_now) else np.nan,
                    "Signal_Local": classify_gap(gap),
                    "Vigilance": classify_vigilance(variation, horizon),
                    "Source_Prix": info.loc[d.Code_ID, "Source_Prix"],
                    "Nb_Marches": int(info.loc[d.Code_ID, "Nb_Marches"]),
                    "Distance_km": float(info.loc[d.Code_ID, "Distance_km"]),
                    "Horizon": horizon,
                    "Scénario": scenario,
                }
            )
        return pd.DataFrame(rows)

    def department_series(self, dept_id: str, province: str, scenario: str) -> dict:
        current, _ = _last_valid(self.dept_panel[dept_id], self.cutoff)
        parent = self.province_series(province, scenario)
        return {
            "hist": self._hist(self.dept_panel, dept_id),
            "proj": project(current, self.last_obs, self.seasonal_prov[province], self._drift(scenario)),
            "parent_hist": parent["hist"],
            "parent_proj": parent["proj"],
        }

    # -- marchés -------------------------------------------------------------
    def active_markets(self) -> pd.DataFrame:
        return self.markets[self.markets["Actif"]].reset_index(drop=True)

    def markets_in(self, province: str) -> pd.DataFrame:
        m = self.markets
        return m[(m["Province"] == province) & m["Actif"]].sort_values("Marché").reset_index(drop=True)

    def market_series(self, market_id: int) -> list[float]:
        return self.market_panel[market_id].reindex(self.dates_hist).tolist()

    def market_table(self, scenario: str, horizon: int = cfg.HORIZON) -> pd.DataFrame:
        """Prévision par marché (saisonnalité de sa province) et fiabilité des données."""
        drift, rows = self._drift(scenario), []
        h_date = self.dates_proj[horizon - 1]
        for m in self.active_markets().itertuples(index=False):
            if m.Province not in self.seasonal_prov:
                continue
            path = project(m.Prix_Actuel, self.last_obs, self.seasonal_prov[m.Province], drift)
            proj = path[horizon - 1]
            ref_now = self.market_ref.loc[self.last_obs, m.market_id]
            ref_end = self.market_ref.loc[h_date, m.market_id]
            variation = (proj / m.Prix_Actuel - 1) * 100
            rows.append(
                {
                    "market_id": m.market_id,
                    "Marché": m.Marché,
                    "Province": m.Province,
                    "Département": m.Département,
                    "Prix_Actuel": round(m.Prix_Actuel, 1),
                    "Prix_Projete": round(proj, 1),
                    "Variation_pct": round(variation, 1),
                    "Vigilance": classify_vigilance(variation, horizon),
                    "Ecart_Moy5_pct": round((m.Prix_Actuel / ref_now - 1) * 100, 1) if pd.notna(ref_now) else np.nan,
                    "Ecart_Moy5_Projete_pct": round((proj / ref_end - 1) * 100, 1) if pd.notna(ref_end) else np.nan,
                    "Completude_pct": m.Completude_pct,
                    "Fiabilite": m.Fiabilite,
                    "Derniere_Obs": m.Derniere_Obs,
                    "lon": m.lon,
                    "lat": m.lat,
                    "Horizon": horizon,
                }
            )
        return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #


def _extend(panel: pd.DataFrame, steps: int) -> pd.DataFrame:
    """Ajoute ``steps`` mois vides pour permettre les décalages (moyenne 5 ans des mois projetés)."""
    future = pd.date_range(panel.index[-1] + pd.offsets.MonthBegin(1), periods=steps, freq="MS")
    return panel.reindex(panel.index.append(future))


def clean_outliers(wide: pd.DataFrame) -> tuple[pd.DataFrame, int, dict[pd.Timestamp, float]]:
    """Nettoyage en deux étapes ; retourne (série nettoyée, nb de relevés isolés écartés, mois synchronisés écartés).

    1. Relevé isolé très éloigné de la médiane glissante de son marché (erreur de saisie probable).
    2. Mois où la médiane des écarts de tous les marchés s'éloigne de la tendance (≥ ``SYNC_MIN_MARKETS`` marchés) :
       anomalie synchronisée, probable artefact de collecte ; à confirmer avec le SISAAP (liste affichée dans l'application).

    La fenêtre est centrée mais n'utilise que les données présentes : appliquée à une série tronquée à la date de
    prévision, elle ne regarde jamais l'avenir de cette date.
    """
    med = wide.rolling(cfg.OUTLIER_WINDOW, center=True, min_periods=3).median()
    ratio = wide / med
    bad = (ratio > cfg.OUTLIER_HIGH) | (ratio < cfg.OUTLIER_LOW)
    cleaned = wide.mask(bad)
    sync: dict[pd.Timestamp, float] = {}
    if cfg.MASK_SYNC_ANOMALIES:
        nat = ratio.median(axis=1)
        flagged = nat[((nat > cfg.SYNC_HIGH) | (nat < cfg.SYNC_LOW)) & (wide.notna().sum(axis=1) >= cfg.SYNC_MIN_MARKETS)]
        sync = {d: round(float(v), 2) for d, v in flagged.items()}
        cleaned.loc[list(sync)] = np.nan
    return cleaned, int(bad.sum().sum()), sync


def reliability_level(completeness_pct: float, active: bool) -> str:
    """Fiabilité d'un marché : part des 24 derniers mois réellement relevés (hors interpolation)."""
    if not active:
        return "Inactif"
    if completeness_pct >= cfg.RELIABILITY_GOOD:
        return "Bonne"
    return "Moyenne" if completeness_pct >= cfg.RELIABILITY_MEDIUM else "Faible"


def build_model(source: PriceSource, geo: GeoData, commodity: str, as_of: pd.Timestamp | None = None) -> Model:
    """Construit le modèle. ``as_of`` : date de prévision (relecture) ; aucune donnée postérieure n'est utilisée
    pour la saisonnalité, l'intervalle ou les prix actuels : elle sert uniquement à comparer au réalisé."""
    markets = geo.assign_points(source.markets(), province_col="admin1")
    full = source.monthly_prices(commodity)
    full = full[[c for c in full.columns if c in set(markets["market_id"])]]
    data_last = full.dropna(how="all").index.max()
    last_obs = min(month_start(as_of), data_last) if as_of is not None else data_last
    observed, n_outliers, sync_months = clean_outliers(full.loc[:last_obs])
    wide = observed.interpolate(limit=cfg.MAX_INTERPOLATION_MONTHS, limit_area="inside")
    cutoff = last_obs - pd.DateOffset(months=cfg.MAX_STALE_MONTHS)
    window = observed.index[-cfg.HISTORY_MONTHS:]

    # -- marchés : prix actuel, dernière observation, variations ------------------
    cur, last = [], []
    for mid in markets["market_id"]:
        price, date = _last_valid(wide[mid], cutoff) if mid in wide else (np.nan, None)
        cur.append(price)
        last.append(date)
    markets = markets.assign(Prix_Actuel=cur, Derniere_Obs=last)
    markets["Actif"] = markets["Prix_Actuel"].notna()
    markets["Completude_pct"] = [
        round(float(observed.loc[window, m].notna().mean() * 100), 0) if m in observed else 0.0
        for m in markets["market_id"]
    ]
    markets["Fiabilite"] = [reliability_level(c, a) for c, a in zip(markets["Completude_pct"], markets["Actif"], strict=True)]

    def _change(mid: int, months: int) -> float:
        if mid not in wide:
            return np.nan
        s = wide[mid]
        then, now = s.get(last_obs - pd.DateOffset(months=months), np.nan), s.get(last_obs, np.nan)
        return round((now / then - 1) * 100, 1) if pd.notna(now) and pd.notna(then) else np.nan

    markets["Var_1m_pct"] = [_change(m, 1) for m in markets["market_id"]]
    markets["YoY_pct"] = [_change(m, 12) for m in markets["market_id"]]

    # -- provinces : médiane des marchés --------------------------------------------
    prov_series = {}
    for name in geo.provinces["Province"]:
        ids = [m for m in markets.loc[markets["Province"] == name, "market_id"] if m in wide]
        prov_series[name] = wide[ids].median(axis=1, skipna=True) if ids else pd.Series(np.nan, index=wide.index)
    prov_panel = pd.DataFrame(prov_series)

    # -- départements : marchés locaux, sinon marché actif le plus proche ------------
    active = markets[markets["Actif"]]
    dept_series, info = {}, []
    for d in geo.departments.itertuples(index=False):
        local_active = active[active["Dept_ID"] == d.Code_ID]
        if len(local_active):
            s = wide[local_active["market_id"].tolist()].median(axis=1, skipna=True)
            info.append((d.Code_ID, "Marché local", len(local_active), ", ".join(local_active["Marché"]), 0.0))
        elif len(active):
            dist = haversine_km(d.lon, d.lat, active["lon"].to_numpy(), active["lat"].to_numpy())
            k = int(np.argmin(dist))
            near = active.iloc[k]
            s = wide[near["market_id"]]
            info.append((d.Code_ID, f"Marché de {near['Marché']} ({dist[k]:.0f} km)", 0, near["Marché"], float(dist[k])))
        else:
            s = pd.Series(np.nan, index=wide.index)
            info.append((d.Code_ID, "Aucune donnée", 0, "", np.nan))
        dept_series[d.Code_ID] = s
    dept_panel = pd.DataFrame(dept_series)

    # Prix réalisés après la date de prévision (uniquement pour la comparaison en mode relecture)
    prov_actual = pd.DataFrame(index=pd.date_range(last_obs, periods=cfg.HORIZON + 1, freq="MS")[1:])
    if last_obs < data_last:
        full_i = clean_outliers(full)[0].interpolate(limit=cfg.MAX_INTERPOLATION_MONTHS, limit_area="inside")
        for name in geo.provinces["Province"]:
            ids = [m for m in markets.loc[markets["Province"] == name, "market_id"] if m in full_i]
            prov_actual[name] = full_i[ids].median(axis=1, skipna=True).reindex(prov_actual.index) if ids else np.nan

    seasonal, seasonal_prov = seasonal_indices(prov_panel, last_obs)
    band = forecast_band(prov_panel, seasonal_prov, last_obs)
    prov_ext, dept_ext = _extend(prov_panel, cfg.HORIZON), _extend(dept_panel, cfg.HORIZON)

    return Model(
        commodity=commodity,
        last_obs=last_obs,
        dates_hist=month_range_ending(last_obs, cfg.HISTORY_MONTHS),
        dates_proj=projection_dates(last_obs),
        provinces=geo.provinces[["Code_ID", "Province"]].reset_index(drop=True),
        departments=geo.departments[["Code_ID", "Département", "Province", "lon", "lat"]].reset_index(drop=True),
        markets=markets.reset_index(drop=True),
        market_panel=wide,
        prov_panel=prov_ext,
        prov_ref=five_year_reference(prov_ext),
        dept_panel=dept_ext,
        dept_ref=five_year_reference(dept_ext),
        dept_info=pd.DataFrame(info, columns=["Dept_ID", "Source_Prix", "Nb_Marches", "Marche_ref", "Distance_km"]),
        seasonal=seasonal,
        seasonal_prov=seasonal_prov,
        band=band,
        market_ref=five_year_reference(_extend(wide, cfg.HORIZON)),
        prov_actual=prov_actual,
        as_of=as_of,
        data_last_obs=data_last,
        n_outliers=n_outliers,
        sync_months=sync_months,
    )
