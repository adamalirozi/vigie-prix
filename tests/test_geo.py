import json

import pytest

import config as cfg
from services import geo as geomod


def test_counts_and_parents(geo):
    assert len(geo.provinces) == 23 and len(geo.departments) == 70
    assert set(geo.departments["Province"]) == set(geo.provinces["Province"])  # aucune province vide
    assert geo.departments["Code_ID"].is_unique


def test_label_points_inside_bounds(geo):
    min_lon, min_lat, max_lon, max_lat = geo.bounds
    for df in (geo.provinces, geo.departments):
        assert df["lon"].between(min_lon, max_lon).all() and df["lat"].between(min_lat, max_lat).all()


def test_simplification_shrinks_payload():
    raw = geomod.load_geo(cfg.GEO_PROVINCES, cfg.GEO_DEPARTMENTS, 0)
    slim = geomod.load_geo(cfg.GEO_PROVINCES, cfg.GEO_DEPARTMENTS, cfg.GEO_SIMPLIFY_TOLERANCE)
    assert len(json.dumps(slim.provinces_geojson)) < 0.4 * len(json.dumps(raw.provinces_geojson))


def test_province_codes_check(geo):
    geomod.check_province_codes(geo, {"TD-KA", "TD-LC"})
    with pytest.raises(geomod.GeoError, match="TD-XX"):
        geomod.check_province_codes(geo, {"TD-XX"})


def test_missing_file_raises(tmp_path):
    with pytest.raises(geomod.GeoError, match="introuvable"):
        geomod.load_geo(tmp_path / "nope.geojson", cfg.GEO_DEPARTMENTS)


def test_duplicate_department_ids_raise(tmp_path):
    feat = {"type": "Feature", "properties": {"shapeID": "A", "shapeName": "x"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
    bad = tmp_path / "d.geojson"
    bad.write_text(json.dumps({"type": "FeatureCollection", "features": [feat, feat]}))
    with pytest.raises(geomod.GeoError, match="dupliqués"):
        geomod.load_geo(cfg.GEO_PROVINCES, bad)


def test_multipolygon_with_hole_gets_interior_label(tmp_path):
    """L'ancienne version lisait coordinates[0] seulement et ignorait trous et MultiPolygon."""
    ring = lambda a, b: [[a, a], [b, a], [b, b], [a, b], [a, a]]
    geom = {"type": "MultiPolygon", "coordinates": [[ring(0, 10), ring(4, 6)[::-1]], [ring(20, 22)]]}
    prov = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"shapeISO": "TD-ZZ", "shapeName": "Zed"}, "geometry": geom}]}
    dept = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"shapeID": "d1", "shapeName": "D"}, "geometry": geom}]}
    (tmp_path / "p.geojson").write_text(json.dumps(prov))
    (tmp_path / "d.geojson").write_text(json.dumps(dept))
    g = geomod.load_geo(tmp_path / "p.geojson", tmp_path / "d.geojson")
    assert g.departments.iloc[0]["Province"] == "Zed"
    x, y = g.provinces.iloc[0][["lon", "lat"]]
    assert not (4 < x < 6 and 4 < y < 6)  # le point n'est pas tombé dans le trou


def test_center_zoom():
    center, zoom = geomod.center_zoom((13.0, 7.0, 24.0, 23.5))
    assert 13 < center["lon"] < 24 and 7 < center["lat"] < 23.5
    small_center, small_zoom = geomod.center_zoom((14.0, 12.0, 15.0, 13.0))
    assert small_zoom > zoom  # une province se cadre plus serré que le pays


def test_assign_points_prefers_source_province(geo):
    import pandas as pd

    pts = pd.DataFrame({"Marché": ["Moundou"], "admin1": ["Logone Occidental"], "lon": [16.08], "lat": [8.57]})
    out = geo.assign_points(pts, province_col="admin1")
    assert out.loc[0, "Province"] == "Logone Occidental" and bool(out.loc[0, "Hors_limites"])
    spatial = geo.assign_points(pts)  # sans libellé : appartenance spatiale pure
    assert spatial.loc[0, "Province"] == "Logone Oriental" and not bool(spatial.loc[0, "Hors_limites"])


def test_assign_points_unknown_label_falls_back_to_polygon(geo):
    import pandas as pd

    pts = pd.DataFrame({"admin1": ["Atlantide"], "lon": [15.04], "lat": [12.11]})
    assert geo.assign_points(pts, province_col="admin1").loc[0, "Province"] == "N'Djamena Region"


def test_haversine():
    # N'Djamena -> Abéché ; contrôle indépendant par l'approximation équirectangulaire (≈ 656 km)
    import math

    lon1, lat1, lon2, lat2 = 15.04, 12.11, 20.83, 13.83
    flat = 6371.0088 * math.hypot(math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2)),
                                  math.radians(lat2 - lat1))
    assert abs(geomod.haversine_km(lon1, lat1, lon2, lat2) - flat) < 0.01 * flat
    assert geomod.haversine_km(lon1, lat1, lon1, lat1) == 0
