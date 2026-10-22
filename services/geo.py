"""Chargement et préparation des géométries (provinces et départements).

Ce module est volontairement indépendant de Streamlit pour rester testable.
La mise en cache est appliquée dans ``services/cached.py``.

Améliorations par rapport à l'ancienne version :
- ``shapely.representative_point()`` remplace ~60 lignes de géométrie maison
  et gère correctement les trous et les ``MultiPolygon`` ;
- les géométries sont simplifiées une seule fois (charge utile réduite) ;
- le rattachement département → province utilise la plus grande aire
  d'intersection (robuste aux limites qui se touchent) ;
- les erreurs de données lèvent ``GeoError`` avec un message exploitable.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, mapping, shape

Bounds = tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)


def _norm(text: object) -> str:
    """Minuscules, sans accents ni ponctuation : « Ndjaména » → « ndjamena »."""
    ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", ascii_text.lower())


# Libellés administratifs de la source (WFP) → libellés des GeoJSON (après normalisation)
_PROVINCE_ALIASES = {"ndjamena": "ndjamenaregion", "barhelgazal": "bahrelgazel"}


class GeoError(ValueError):
    """Données géographiques invalides ou incohérentes."""


@dataclass
class GeoData:
    """Géométries prêtes à l'emploi pour Plotly."""

    provinces_geojson: dict
    departments_geojson: dict
    provinces: pd.DataFrame  # Code_ID, Province, lon, lat, min_lon, min_lat, max_lon, max_lat
    departments: pd.DataFrame  # Code_ID, Département, Province, Code_Province, lon, lat
    bounds: Bounds  # emprise du pays
    _dept_raw: list = field(default_factory=list, repr=False)  # géométries d'origine (non simplifiées)

    def departments_geojson_for(self, ids: list[str]) -> dict:
        """Sous-ensemble du GeoJSON départemental (conserve l'ordre demandé)."""
        wanted = set(ids)
        feats = [f for f in self.departments_geojson["features"] if f["properties"]["shapeID"] in wanted]
        return {"type": "FeatureCollection", "features": feats}

    def province_bounds(self, province: str) -> Bounds:
        row = self.provinces.loc[self.provinces["Province"] == province].iloc[0]
        return (float(row["min_lon"]), float(row["min_lat"]), float(row["max_lon"]), float(row["max_lat"]))

    def assign_points(
        self, df: pd.DataFrame, lon: str = "lon", lat: str = "lat", province_col: str | None = None
    ) -> pd.DataFrame:
        """Rattache chaque point (marché) à un département et à sa province parente.

        - Si ``province_col`` est fourni (libellé administratif de la source), la province de la
          source fait foi — les limites du GeoJSON sont approchées et un marché proche d'une
          frontière peut sinon basculer dans la mauvaise province (cas de Moundou). Le département
          est alors cherché parmi ceux de cette province (contenant le point, sinon le plus proche).
        - Sinon, ou si le libellé n'est pas reconnu, le test d'appartenance spatial s'applique.
        La colonne ``Hors_limites`` signale les points rattachés par proximité plutôt que par inclusion.
        """
        xs, ys = df[lon].to_numpy(float), df[lat].to_numpy(float)
        depts = self.departments
        by_norm = {_norm(n): c for n, c in zip(self.provinces["Province"], self.provinces["Code_ID"])}
        dept_idx = np.full(len(df), -1)
        outside = np.zeros(len(df), dtype=bool)
        wanted = (
            [by_norm.get(_PROVINCE_ALIASES.get(_norm(v), _norm(v))) for v in df[province_col]]
            if province_col
            else [None] * len(df)
        )
        for k, code in enumerate(wanted):
            pt = Point(xs[k], ys[k])
            cand = np.where(depts["Code_Province"].to_numpy() == code)[0] if code else np.arange(len(depts))
            if len(cand) == 0:
                cand = np.arange(len(depts))
            inside = [i for i in cand if self._dept_raw[i].contains(pt)]
            if inside:
                dept_idx[k] = inside[0]
            else:
                dept_idx[k] = int(cand[np.argmin([self._dept_raw[i].distance(pt) for i in cand])])
                outside[k] = True
        info = depts.iloc[dept_idx].reset_index(drop=True)
        out = df.reset_index(drop=True).copy()
        out["Dept_ID"] = info["Code_ID"]
        out["Département"] = info["Département"]
        out["Province"] = info["Province"]
        out["Code_Province"] = info["Code_Province"]
        out["Hors_limites"] = outside
        return out


def haversine_km(lon1, lat1, lon2, lat2):
    """Distance orthodromique en km (vectorisée)."""
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def _read_features(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise GeoError(f"Fichier GeoJSON introuvable : {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise GeoError(f"GeoJSON illisible ({path.name}) : {exc}") from exc
    features = data.get("features", [])
    if not features:
        raise GeoError(f"Aucune entité dans {path.name}.")
    return features


def _simplify(feature: dict, tolerance: float, keep: tuple[str, ...]) -> tuple[dict, object]:
    geom = shape(feature["geometry"])
    if tolerance > 0:
        simplified = geom.simplify(tolerance, preserve_topology=True)
        geom = simplified if not simplified.is_empty else geom
    props = {k: feature["properties"].get(k) for k in keep}
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}, geom


def load_geo(provinces_path: Path, departments_path: Path, tolerance: float = 0.0) -> GeoData:
    """Charge, valide et prépare les deux GeoJSON."""
    prov_features = _read_features(provinces_path)
    dept_features = _read_features(departments_path)

    # --- provinces -------------------------------------------------------- #
    prov_out, prov_geoms, prov_rows = [], [], []
    for feat in prov_features:
        props = feat.get("properties", {})
        code, name = props.get("shapeISO"), props.get("shapeName")
        if not code or not name:
            raise GeoError("Chaque province doit fournir `shapeISO` et `shapeName`.")
        out, geom = _simplify(feat, tolerance, ("shapeISO", "shapeName"))
        point = geom.representative_point()
        min_lon, min_lat, max_lon, max_lat = geom.bounds
        prov_out.append(out)
        prov_geoms.append(shape(feat["geometry"]))  # géométrie d'origine pour les tests spatiaux
        prov_rows.append(
            {
                "Code_ID": code, "Province": name, "lon": point.x, "lat": point.y,
                "min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat,
            }
        )
    provinces = pd.DataFrame(prov_rows)
    if provinces["Code_ID"].duplicated().any():
        raise GeoError("Le GeoJSON des provinces contient des `shapeISO` dupliqués.")

    # --- départements ----------------------------------------------------- #
    ids = [f.get("properties", {}).get("shapeID") for f in dept_features]
    if any(not i for i in ids):
        raise GeoError("Le GeoJSON des départements doit fournir un `shapeID` pour chaque entité.")
    if len(ids) != len(set(ids)):
        raise GeoError("Le GeoJSON des départements contient des `shapeID` dupliqués.")

    dept_out, dept_rows, dept_raw = [], [], []
    for feat in dept_features:
        out, geom = _simplify(feat, tolerance, ("shapeID", "shapeName"))
        raw = shape(feat["geometry"])
        dept_raw.append(raw)
        # Rattachement à la province qui recouvre la plus grande part du département
        areas = [raw.intersection(pg).area for pg in prov_geoms]
        best = max(range(len(areas)), key=areas.__getitem__)
        if areas[best] <= 0:
            raise GeoError(
                f"Impossible d'associer le département « {feat['properties'].get('shapeName', '?')} » "
                "à une province."
            )
        point = geom.representative_point()
        dept_out.append(out)
        dept_rows.append(
            {
                "Code_ID": feat["properties"]["shapeID"],
                "Département": feat["properties"].get("shapeName") or "Sans nom",
                "Province": prov_rows[best]["Province"],
                "Code_Province": prov_rows[best]["Code_ID"],
                "lon": point.x, "lat": point.y,
            }
        )

    bounds = (
        float(provinces["min_lon"].min()), float(provinces["min_lat"].min()),
        float(provinces["max_lon"].max()), float(provinces["max_lat"].max()),
    )
    return GeoData(
        provinces_geojson={"type": "FeatureCollection", "features": prov_out},
        departments_geojson={"type": "FeatureCollection", "features": dept_out},
        provinces=provinces,
        departments=pd.DataFrame(dept_rows),
        bounds=bounds,
        _dept_raw=dept_raw,
    )


def check_province_codes(geo: GeoData, expected_codes: set[str]) -> None:
    """Vérifie que chaque province du référentiel existe dans le GeoJSON."""
    missing = expected_codes - set(geo.provinces["Code_ID"])
    if missing:
        raise GeoError(f"Codes absents de `shapeISO` dans le GeoJSON : {', '.join(sorted(missing))}")


def center_zoom(bounds: Bounds, width_px: int = 720, height_px: int = 520, padding: float = 0.15) -> tuple[dict, float]:
    """Centre et niveau de zoom (Plotly/MapLibre, tuiles 512 px) pour cadrer une emprise."""
    min_lon, min_lat, max_lon, max_lat = bounds
    center = {"lat": (min_lat + max_lat) / 2, "lon": (min_lon + max_lon) / 2}
    lon_span = max(max_lon - min_lon, 1e-6)
    lat_span = max(max_lat - min_lat, 1e-6)
    cos_lat = max(math.cos(math.radians(center["lat"])), 0.1)
    zoom_x = math.log2(width_px * 360 / (512 * lon_span))
    zoom_y = math.log2(height_px * 360 * cos_lat / (512 * lat_span))
    zoom = min(zoom_x, zoom_y) - padding
    return center, round(max(3.0, min(zoom, 9.0)), 2)
