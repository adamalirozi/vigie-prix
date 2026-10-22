"""Formatage des nombres à la française.

- séparateur de milliers : espace fine insécable (U+202F) pour éviter
  qu'un montant se coupe en fin de ligne ;
- séparateur décimal : virgule ;
- espace insécable (U+00A0) avant l'unité et le symbole « % ».
"""

from __future__ import annotations

NNBSP = "\u202f"  # espace fine insécable
NBSP = "\u00a0"  # espace insécable


def num(value: float, decimals: int = 0) -> str:
    """Nombre avec espaces fines pour les milliers et virgule décimale."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", NNBSP).replace(".", ",").replace("-", "−")


_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def month_label(ts) -> str:
    """« oct. 26 » : Plotly n'a pas de locale française dans Streamlit, on formate nous-mêmes."""
    return f"{_MOIS[ts.month - 1]} {ts.year % 100:02d}"


def month_label_long(ts) -> str:
    """« oct. 2026 »."""
    return f"{_MOIS[ts.month - 1]} {ts.year}"


def fcfa(value: float) -> str:
    """Montant en FCFA, ex. « 75 000 FCFA »."""
    return f"{num(value)}{NBSP}FCFA"


def kg(value: float, decimals: int = 0) -> str:
    """Prix au kilo, ex. « 212 FCFA/kg »."""
    return f"{num(value, decimals)}{NBSP}FCFA/kg"


def pct(value: float, signed: bool = True, decimals: int = 1) -> str:
    """Pourcentage, ex. « +12,3 % »."""
    text = f"{value:+.{decimals}f}" if signed else f"{value:.{decimals}f}"
    return text.replace(".", ",").replace("-", "−") + f"{NBSP}%"


def pct_delta(value: float, decimals: int = 1) -> str:
    """Pourcentage signé pour ``st.metric(delta=…)``.

    Streamlit repère un delta négatif à son tiret ASCII initial : on n'utilise donc pas
    le vrai signe moins (U+2212) ici, contrairement à ``pct``.
    """
    return f"{value:+.{decimals}f}".replace(".", ",") + f"{NBSP}%"
