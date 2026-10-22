"""Constantes et aides partagées par les vues."""

from __future__ import annotations

CHART_CONFIG = {"displayModeBar": False}
HIGHLIGHT_STYLE = "background-color: #e8eff5; color: #244b6a; font-weight: 700;"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
METRIC_CHOICES = {"Prix projeté": "Prix_Projete", "Variation projetée": "Variation_pct",
                  "Écart moyenne 5 ans": "Ecart_Moy5_pct"}


def highlight_rows(column: str, value: str):
    """Styler : met en évidence la ligne dont ``column`` vaut ``value``."""
    return lambda row: [HIGHLIGHT_STYLE if row[column] == value else "" for _ in row]
