import io

import pandas as pd

from services import export


def test_csv_and_excel_exports(model):
    table = model.province_table("Référence", 2)
    csv = export.to_csv_bytes(table, export.PROVINCE_COLUMNS)
    df = pd.read_csv(io.BytesIO(csv), encoding="utf-8-sig")
    assert len(df) == len(table) and "Prix actuel (FCFA/kg)" in df.columns
    assert (df["Horizon (mois)"] == 2).all()
    assert df["Dernier relevé"].str.match(r"\d{4}-\d{2}").all()  # dates lisibles, pas de datetime brut
    xlsx = export.to_excel_bytes(table, export.PROVINCE_COLUMNS, "Provinces", "note")
    assert set(pd.read_excel(io.BytesIO(xlsx), sheet_name=None)) == {"Provinces", "Dictionnaire", "Avertissement"}


def test_department_export_keeps_price_source(model):
    table = model.department_table("Référence", 3)
    df = pd.read_csv(io.BytesIO(export.to_csv_bytes(table, export.DEPARTMENT_COLUMNS)), encoding="utf-8-sig")
    assert "Source du prix" in df.columns and df["Source du prix"].notna().all()


def test_filename_is_ascii_and_dated():
    name = export.export_filename("vigie_prix_riz importé_provinces_m3", "Pression accrue", "csv")
    assert name.isascii() and " " not in name and name.endswith(".csv") and "pression-accrue" in name
