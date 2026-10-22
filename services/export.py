"""Exports CSV / Excel (avec dictionnaire de données)."""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date

import pandas as pd

PROVINCE_COLUMNS = {
    "Code_ID": ("Code province", "Code ISO de la province (shapeISO)."),
    "Province": ("Province", "Nom de la province."),
    "Prix_Actuel": ("Prix actuel (FCFA/kg)", "Médiane des prix des marchés de la province au dernier relevé."),
    "Horizon": ("Horizon (mois)", "Nombre de mois de la projection (1, 2 ou 3)."),
    "Prix_Projete": ("Prix projeté (FCFA/kg)", "Prix actuel × saisonnalité × dérive du scénario, à l'horizon indiqué."),
    "Variation_pct": ("Variation projetée (%)", "Prix projeté / prix actuel − 1."),
    "Vigilance": ("Niveau de vigilance", "Faible < 10 % ≤ Modéré < 20 % ≤ Élevé pour 3 mois (seuils proportionnels à l'horizon)."),
    "Var_1m_pct": ("Variation sur 1 mois (%)", "Prix actuel / prix du mois précédent − 1."),
    "YoY_pct": ("Variation sur 1 an (%)", "Prix actuel / prix du même mois l'an dernier − 1."),
    "Ref_5ans": ("Moyenne 5 ans (FCFA/kg)", "Moyenne du même mois sur les 5 années précédentes."),
    "Ecart_Moy5_pct": ("Écart à la moyenne 5 ans (%)", "Prix actuel / moyenne 5 ans − 1."),
    "Nb_Marches": ("Marchés actifs", "Nombre de marchés avec un prix récent dans la province."),
    "Derniere_Obs": ("Dernier relevé", "Mois du dernier prix utilisé."),
    "Scénario": ("Scénario illustratif", "Dérive mensuelle ajoutée à la projection saisonnière."),
}

DEPARTMENT_COLUMNS = {
    "Code_ID": ("Code département", "Identifiant du département (shapeID)."),
    "Département": ("Département", "Nom du département."),
    "Province": ("Province parente", "Province du département."),
    "Prix_Actuel": ("Prix actuel (FCFA/kg)", "Prix du marché local (médiane) ou du marché actif le plus proche."),
    "Horizon": ("Horizon (mois)", "Nombre de mois de la projection (1, 2 ou 3)."),
    "Prix_Projete": ("Prix projeté (FCFA/kg)", "Prix actuel × saisonnalité provinciale × dérive du scénario."),
    "Variation_pct": ("Variation projetée (%)", "Prix projeté / prix actuel − 1."),
    "Ecart_Parent_pct": ("Écart vs province (%)", "Prix projeté du département / prix projeté de la province − 1."),
    "Ecart_Moy5_pct": ("Écart à la moyenne 5 ans (%)", "Prix actuel / moyenne 5 ans du département − 1."),
    "Signal_Local": ("Signal local", "Écart supérieur à ±10 % : au-dessus / en dessous du niveau provincial."),
    "Vigilance": ("Niveau de vigilance", "Faible < 10 % ≤ Modéré < 20 % ≤ Élevé."),
    "Source_Prix": ("Source du prix", "« Marché local » ou marché actif le plus proche (distance)."),
    "Nb_Marches": ("Marchés locaux actifs", "Nombre de marchés actifs dans le département."),
    "Distance_km": ("Distance au marché (km)", "0 si le prix vient d'un marché du département."),
    "Scénario": ("Scénario illustratif", "Dérive mensuelle ajoutée à la projection saisonnière."),
}


def _prepare(df: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = df[list(spec)].copy()
    for col in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[col]):
            data[col] = data[col].dt.strftime("%Y-%m")
    data = data.rename(columns={k: v[0] for k, v in spec.items()})
    dictionary = pd.DataFrame(
        [{"Colonne": label, "Description": desc} for label, desc in spec.values()]
    )
    return data, dictionary


def to_csv_bytes(df: pd.DataFrame, spec: dict) -> bytes:
    data, _ = _prepare(df, spec)
    return data.to_csv(index=False).encode("utf-8-sig")  # BOM : accents corrects dans Excel


def to_excel_bytes(df: pd.DataFrame, spec: dict, sheet: str, note: str) -> bytes:
    data, dictionary = _prepare(df, spec)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name=sheet, index=False)
        dictionary.to_excel(writer, sheet_name="Dictionnaire", index=False)
        pd.DataFrame({"Note": [note]}).to_excel(writer, sheet_name="Avertissement", index=False)
        for ws in writer.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(width + 2, 70)
            ws.freeze_panes = "A2"
    return buffer.getvalue()


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def export_filename(prefix: str, scenario: str, ext: str) -> str:
    return f"{_slug(prefix).replace('-', '_')}_{_slug(scenario)}_{date.today():%Y-%m-%d}.{ext}"
