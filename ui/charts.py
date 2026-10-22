"""Constructeurs de graphiques Plotly (fonctions pures, sans Streamlit).

Toutes les figures partagent la même mise en page (``_layout``) : police,
séparateurs français, grille discrète, marges serrées, fond blanc.
Les mois sont des libellés français sur un axe catégoriel, car Plotly
n'embarque pas la locale française dans Streamlit.
Les prix sont en FCFA/kg.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import config as cfg
from ui.formatting import month_label

C = cfg.COLORS
GRID = "#e4e7eb"
PRICE_SCALE = cfg.SEQUENTIAL_SCALE
VARIATION_SCALE = ["#fdf1e3", "#fbd3a1", "#f7aa5a", "#f28e2b", "#c8631a"]

# Indicateurs colorables sur la carte des provinces : clé de colonne → (titre de la barre, type d'échelle)
MAP_METRICS = {
    "Prix_Projete": ("FCFA / kg", "price"),
    "Variation_pct": ("Variation (%)", "variation"),
    "Ecart_Moy5_pct": ("Écart moy. 5 ans (%)", "diverging"),
}


# --------------------------------------------------------------------------- #
# Aides communes
# --------------------------------------------------------------------------- #
def _scale(colors: list[str]) -> list[list]:
    n = len(colors) - 1
    return [[i / n, c] for i, c in enumerate(colors)]


def _layout(fig: go.Figure, height: int, **extra) -> go.Figure:
    base = dict(
        height=height,
        margin=dict(l=8, r=8, t=12, b=8),
        paper_bgcolor=C["surface"],
        plot_bgcolor=C["surface"],
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color=C["ink"]),
        separators=", ",  # décimale « , » et milliers « espace »
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=C["line"], font_size=13),
    )
    fig.update_layout(**{**base, **extra})  # `extra` l'emporte sur les valeurs par défaut
    return fig


def _axes(fig: go.Figure, **kw) -> None:
    fig.update_xaxes(**{"showgrid": False, "zeroline": False, "linecolor": "#c8cdd3", **kw.get("x", {})})
    fig.update_yaxes(**{"gridcolor": GRID, "zeroline": False, **kw.get("y", {})})


def _halo_labels(lon, lat, text, size: int, color: str = C["ink"]) -> list[go.Scattermap]:
    """Étiquettes avec halo blanc (texte blanc plus grand dessous) pour rester lisibles sur la carte."""
    common = dict(lon=list(lon), lat=list(lat), text=list(text), mode="text", hoverinfo="skip", showlegend=False)
    return [
        go.Scattermap(**common, textfont=dict(size=size + 3, color="#ffffff")),
        go.Scattermap(**common, textfont=dict(size=size, color=color)),
    ]


def _outline(geojson: dict, location: str, id_field: str) -> go.Choroplethmap:
    """Contour épais autour de l'entité sélectionnée (aucun remplissage)."""
    feats = [f for f in geojson["features"] if f["properties"][id_field] == location]
    return go.Choroplethmap(
        geojson={"type": "FeatureCollection", "features": feats},
        locations=[location], z=[1], featureidkey=f"properties.{id_field}",
        colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
        marker_line_color=C["highlight"], marker_line_width=3, hoverinfo="skip", showlegend=False,
    )


def _no_dim(trace: go.Choroplethmap, opacity: float) -> None:
    """Évite que la sélection par clic n'atténue les autres entités."""
    trace.update(selected=dict(marker=dict(opacity=opacity)), unselected=dict(marker=dict(opacity=opacity)))


def _map_layout(fig: go.Figure, center: dict, zoom: float, height: int, offline: bool = False) -> go.Figure:
    _layout(fig, height, clickmode="event+select")
    fig.update_layout(
        map=dict(style=cfg.MAP_STYLE_OFFLINE if offline else cfg.MAP_STYLE, center=center, zoom=zoom),
        margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _grey_layer(geojson: dict, ids: list[str], id_field: str, hover: list[str]) -> go.Choroplethmap:
    """Entités sans donnée récente : gris neutre, infobulle explicite."""
    return go.Choroplethmap(
        geojson=geojson, locations=ids, z=[0] * len(ids), featureidkey=f"properties.{id_field}",
        colorscale=[[0, "#e3e6ea"], [1, "#e3e6ea"]], showscale=False, marker_opacity=0.9,
        marker_line_width=0.6, marker_line_color="#ffffff", text=hover,
        hovertemplate="%{text}<extra></extra>", showlegend=False,
    )


def markets_trace(markets: pd.DataFrame) -> go.Scattermap:
    """Points des marchés suivis (infobulle : prix, variation mensuelle et annuelle)."""
    custom = np.column_stack([
        markets["Marché"], markets["Province"], markets["Prix_Actuel"].round(0),
        markets["Var_1m_pct"].fillna(np.nan), markets["YoY_pct"].fillna(np.nan),
        markets["Derniere_Obs"].map(lambda d: month_label(d) if pd.notna(d) else ""),
    ]).astype(object)
    return go.Scattermap(
        lon=markets["lon"], lat=markets["lat"], mode="markers", name="Marchés", showlegend=False,
        marker=dict(size=8, color=C["ink"], opacity=0.85),
        customdata=custom,
        hovertemplate=(
            "<b>Marché de %{customdata[0]}</b> (%{customdata[1]})<br>"
            "Prix : %{customdata[2]:,.0f} FCFA/kg · relevé %{customdata[5]}<br>"
            "Variation sur 1 mois : %{customdata[3]:+.1f} %<br>"
            "Variation sur 1 an : %{customdata[4]:+.1f} %<extra></extra>"
        ),
    )


def _today_marker(fig: go.Figure, label: str, text: str = "Dernier relevé") -> None:
    """Repère de la dernière observation (shape + annotation : add_vline plante sur axe catégoriel)."""
    fig.add_shape(type="line", x0=label, x1=label, y0=0, y1=1, yref="paper",
                  line=dict(color=C["neutral"], width=1, dash="dot"))
    fig.add_annotation(x=label, y=1, yref="paper", text=text, showarrow=False,
                       yshift=10, font=dict(size=11, color=C["muted"]))


def _lean_season(fig: go.Figure, dates: list[pd.Timestamp]) -> None:
    """Bande « soudure » (indicatif) sur un axe catégoriel : mois consécutifs de ``LEAN_SEASON``."""
    start = None
    for i, d in enumerate([*dates, None]):
        inside = d is not None and d.month in cfg.LEAN_SEASON
        if inside and start is None:
            start = i
        if not inside and start is not None:
            fig.add_shape(type="rect", x0=start - 0.5, x1=i - 0.5, y0=0, y1=1, yref="paper", layer="below",
                          fillcolor="rgba(242,142,43,0.08)", line_width=0)
            fig.add_annotation(x=(start + i - 1) / 2, y=0, yref="paper", text="soudure", showarrow=False,
                               yshift=8, font=dict(size=10, color="#b46a14"))
            start = None


# --------------------------------------------------------------------------- #
# Carte provinciale
# --------------------------------------------------------------------------- #
def province_map(
    table: pd.DataFrame,
    provinces_xy: pd.DataFrame,
    missing: pd.DataFrame,
    geojson: dict,
    selected_code: str | None,
    metric: str,
    center: dict,
    zoom: float,
    markets: pd.DataFrame | None = None,
    offline: bool = False,
) -> go.Figure:
    """Carte choroplèthe cliquable ; ``metric`` ∈ ``MAP_METRICS`` ; ``missing`` = provinces sans prix récent."""
    title, kind = MAP_METRICS[metric]
    values = table[metric]
    kw: dict = {}
    if kind == "price":
        kw = dict(colorscale=_scale(PRICE_SCALE))
    elif kind == "variation":
        kw = dict(colorscale=_scale(VARIATION_SCALE))
    else:
        amp = max(10.0, float(np.nanmax(np.abs(values))) if values.notna().any() else 10.0)
        kw = dict(colorscale=cfg.DIVERGING_SCALE, zmid=0, zmin=-amp, zmax=amp)

    fig = go.Figure()
    if len(missing):
        fig.add_trace(_grey_layer(
            geojson, missing["Code_ID"].tolist(), "shapeISO",
            [f"<b>{r.Province}</b><br>Pas de prix récent (dernier relevé : {r.Dernier_Releve})"
             for r in missing.itertuples()],
        ))
    custom = table[["Province", "Prix_Actuel", "Prix_Projete", "Variation_pct", "Ecart_Moy5_pct", "Vigilance",
                    "Nb_Marches"]].to_numpy().astype(object)
    main = go.Choroplethmap(
        geojson=geojson, locations=table["Code_ID"], z=values, featureidkey="properties.shapeISO",
        marker_opacity=0.88, marker_line_width=0.6, marker_line_color="#ffffff", customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b> · %{customdata[6]} marché(s)<br>"
            "Prix actuel : %{customdata[1]:,.0f} FCFA/kg<br>"
            "Prix projeté (3 mois) : %{customdata[2]:,.0f} FCFA/kg<br>"
            "Variation projetée : %{customdata[3]:+.1f} %<br>"
            "Écart à la moyenne 5 ans : %{customdata[4]:+.1f} %<br>"
            "Niveau de vigilance : %{customdata[5]}<extra></extra>"
        ),
        colorbar=dict(title=dict(text=title, side="right"), thickness=11, len=0.7,
                      tickformat=",.0f"),
        **kw,
    )
    _no_dim(main, 0.88)
    fig.add_trace(main)
    if selected_code and selected_code in set(table["Code_ID"]):
        fig.add_trace(_outline(geojson, selected_code, "shapeISO"))
    if markets is not None and len(markets):
        fig.add_trace(markets_trace(markets))

    # Étiquettes : province sélectionnée + 3 plus fortes valeurs (le reste via l'infobulle)
    top = set(table.nlargest(3, metric)["Code_ID"]) | ({selected_code} if selected_code else set())
    lab = provinces_xy[provinces_xy["Code_ID"].isin(top)]
    for trace in _halo_labels(lab["lon"], lab["lat"], lab["Province"], 11):
        fig.add_trace(trace)
    return _map_layout(fig, center, zoom, cfg.MAP_HEIGHT_PROVINCES, offline)


# --------------------------------------------------------------------------- #
# Tendance + projection
# --------------------------------------------------------------------------- #
def trend_figure(
    dates_hist: list[pd.Timestamp],
    hist: list[float],
    dates_proj: list[pd.Timestamp],
    proj: list[float],
    band: list[tuple[float, float]],
    ref: list[float],
    seuil_pct: float,
    height: int = 440,
    horizon: int = cfg.HORIZON,
    actual: list[float] | None = None,
) -> go.Figure:
    """Historique, projection + intervalle empirique, moyenne 5 ans, seuil d'alerte ; en relecture : prix réalisés."""
    x_h = [month_label(d) for d in dates_hist]
    x_p = [x_h[-1]] + [month_label(d) for d in dates_proj]
    x_all = x_h + x_p[1:]
    last = next((v for v in reversed(hist) if pd.notna(v)), proj[0])
    y_p = [last] + list(proj)
    upper = [last] + [b[1] for b in band]
    lower = [last] + [b[0] for b in band]
    threshold = [r * (1 + seuil_pct / 100) if pd.notna(r) else np.nan for r in ref]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_p, y=upper, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=x_p, y=lower, fill="tonexty", fillcolor="rgba(242,142,43,0.16)", line=dict(width=0),
        name="Intervalle à 80 %", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=x_all, y=ref, mode="lines", name="Moyenne 5 ans", connectgaps=False,
        line=dict(color=C["neutral"], width=2, dash="dot"),
        hovertemplate="%{y:,.0f} FCFA/kg<extra>Moyenne 5 ans</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x_all, y=threshold, mode="lines", name=f"Seuil d'alerte (+{seuil_pct:.0f} %)", connectgaps=False,
        line=dict(color=C["danger"], width=1.3),
        hovertemplate="%{y:,.0f} FCFA/kg<extra>Seuil d'alerte</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x_h, y=hist, mode="lines+markers", name="Prix observé", connectgaps=False,
        line=dict(color=C["primary"], width=2.5), marker=dict(size=6),
        hovertemplate="%{y:,.0f} FCFA/kg<extra>Observé</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x_p, y=y_p, mode="lines+markers", name="Projection indicative",
        line=dict(color=C["warning"], width=2.5, dash="dash"),
        marker=dict(size=[6] + [12 if i + 1 == horizon else 6 for i in range(len(proj))]),
        hovertemplate="%{y:,.0f} FCFA/kg<extra>Projection</extra>",
    ))
    replay = bool(actual)
    if replay:
        fig.add_trace(go.Scatter(
            x=x_p[1:], y=actual, mode="lines+markers", name="Prix réalisé", connectgaps=False,
            line=dict(color=C["positive"], width=2.5), marker=dict(size=9, symbol="diamond"),
            hovertemplate="%{y:,.0f} FCFA/kg<extra>Réalisé</extra>",
        ))
    _today_marker(fig, x_h[-1], "Date de la prévision" if replay else "Dernier relevé")
    _lean_season(fig, dates_hist + dates_proj)
    end_y = y_p[horizon]
    fig.add_annotation(x=x_p[horizon], y=end_y, text=f"{end_y:,.0f}".replace(",", "\u202f"), showarrow=False,
                       xanchor="left", xshift=8, font=dict(size=12, color=C["warning"]))

    finite = [v for v in [*hist, *upper, *lower, *ref, *threshold, *(actual or [])] if pd.notna(v)]
    _layout(fig, height, hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x_all)
    _axes(fig, y=dict(tickformat=",.0f", range=[min(finite) * 0.95, max(finite) * 1.05], title="FCFA / kg"))
    return fig


# --------------------------------------------------------------------------- #
# Classement : haltères (actuel → projeté)
# --------------------------------------------------------------------------- #
def dumbbell_figure(table: pd.DataFrame, selected: str) -> go.Figure:
    """Prix actuel et projeté par province, triées par variation (lecture sur axe commun)."""
    df = table.sort_values("Variation_pct", ascending=True).reset_index(drop=True)
    xs, ys = [], []
    for r in df.itertuples():
        xs += [r.Prix_Actuel, r.Prix_Projete, None]
        ys += [r.Province, r.Province, None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#c8cdd3", width=3),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=df["Prix_Actuel"], y=df["Province"], mode="markers", name="Actuel",
        marker=dict(color=C["neutral"], size=9),
        hovertemplate="<b>%{y}</b><br>Actuel : %{x:,.0f} FCFA/kg<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["Prix_Projete"], y=df["Province"], mode="markers", name="Projeté (3 mois)",
        marker=dict(color=[cfg.VIGILANCE_COLORS[v] for v in df["Vigilance"]], size=11, symbol="diamond"),
        customdata=df[["Variation_pct", "Vigilance"]].to_numpy(),
        hovertemplate=("<b>%{y}</b><br>Projeté : %{x:,.0f} FCFA/kg<br>"
                       "Variation : %{customdata[0]:+.1f} %<br>Vigilance : %{customdata[1]}<extra></extra>"),
    ))
    sel = df[df["Province"] == selected]
    fig.add_trace(go.Scatter(
        x=sel["Prix_Projete"], y=sel["Province"], mode="markers", hoverinfo="skip", showlegend=False,
        marker=dict(size=20, color="rgba(0,0,0,0)", line=dict(color=C["highlight"], width=2.5)),
    ))
    _layout(fig, max(380, 24 * len(df) + 90), legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"))
    _axes(fig, x=dict(tickformat=",.0f", gridcolor=GRID, showgrid=True, title="FCFA / kg"),
          y=dict(showgrid=False, categoryorder="array", categoryarray=df["Province"].tolist()))
    return fig


# --------------------------------------------------------------------------- #
# Quadrant : niveau de prix × écart à la moyenne 5 ans
# --------------------------------------------------------------------------- #
def quadrant_figure(table: pd.DataFrame, selected: str) -> go.Figure:
    df = table.dropna(subset=["Ecart_Moy5_pct"])
    fig = go.Figure()
    for level in cfg.VIGILANCE_ORDER:
        d = df[df["Vigilance"] == level]
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["Prix_Actuel"], y=d["Ecart_Moy5_pct"], mode="markers", name=f"{cfg.VIGILANCE_ICON[level]} {level}",
            marker=dict(color=cfg.VIGILANCE_COLORS[level], size=12, line=dict(color="#fff", width=1)),
            customdata=d[["Province", "Variation_pct"]].to_numpy(),
            hovertemplate=("<b>%{customdata[0]}</b><br>Prix actuel : %{x:,.0f} FCFA/kg<br>"
                           "Écart à la moyenne 5 ans : %{y:+.1f} %<br>"
                           "Variation projetée : %{customdata[1]:+.1f} %<extra></extra>"),
        ))
    sel = df[df["Province"] == selected]
    fig.add_trace(go.Scatter(
        x=sel["Prix_Actuel"], y=sel["Ecart_Moy5_pct"], mode="markers", hoverinfo="skip", showlegend=False,
        marker=dict(size=22, color="rgba(0,0,0,0)", line=dict(color=C["highlight"], width=2.5)),
    ))
    keep = pd.concat([sel, df.nlargest(3, "Ecart_Moy5_pct"), df.nsmallest(2, "Ecart_Moy5_pct"),
                      df.nlargest(2, "Prix_Actuel")]).drop_duplicates("Province")
    fig.add_trace(go.Scatter(
        x=keep["Prix_Actuel"], y=keep["Ecart_Moy5_pct"], text=keep["Province"], mode="text",
        textposition="top center", textfont=dict(size=11, color=C["ink"]), hoverinfo="skip", showlegend=False,
    ))
    fig.add_vline(x=df["Prix_Actuel"].median(), line=dict(color=C["neutral"], dash="dot", width=1))
    fig.add_hline(y=0, line=dict(color=C["ink"], width=1))
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.99, showarrow=False, xanchor="right",
                       text="Prix élevés, au-dessus de la moyenne", font=dict(size=11, color=C["muted"]))
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.01, showarrow=False, xanchor="left",
                       text="Prix bas, sous la moyenne", font=dict(size=11, color=C["muted"]))
    _layout(fig, 460, legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"))
    _axes(fig, x=dict(tickformat=",.0f", title="Prix actuel (FCFA / kg)"),
          y=dict(ticksuffix=" %", title="Écart à la moyenne des 5 dernières années"))
    return fig


# --------------------------------------------------------------------------- #
# Carte de chaleur : écart à la moyenne 5 ans
# --------------------------------------------------------------------------- #
def heatmap_figure(matrix: pd.DataFrame, month_labels: list[str], n_hist: int, selected: str,
                   order: list[str]) -> go.Figure:
    order = [p for p in order if p in matrix.index]
    z = matrix.loc[order]
    amp = float(np.clip(np.nanpercentile(np.abs(z.to_numpy(float)), 95), 20, 60)) if z.notna().any().any() else 30.0
    fig = go.Figure(go.Heatmap(
        z=z.to_numpy(), x=month_labels, y=order, colorscale=cfg.DIVERGING_SCALE, zmid=0, zmin=-amp, zmax=amp,
        xgap=1, ygap=1, colorbar=dict(title=dict(text="Écart (%)", side="right"), thickness=11, len=0.8),
        hovertemplate="<b>%{y}</b> · %{x}<br>Écart à la moyenne 5 ans : %{z:+.1f} %<extra></extra>",
    ))
    fig.add_shape(type="line", x0=n_hist - 0.5, x1=n_hist - 0.5, y0=-0.5, y1=len(order) - 0.5,
                  line=dict(color=C["ink"], width=1.5, dash="dot"))
    fig.add_annotation(x=n_hist - 0.5, y=1, yref="paper", text="Projection", showarrow=False,
                       xanchor="left", xshift=4, yshift=10, font=dict(size=11, color=C["muted"]))
    if selected in order:
        i = order.index(selected)
        fig.add_shape(type="rect", x0=-0.5, x1=len(month_labels) - 0.5, y0=i - 0.5, y1=i + 0.5,
                      line=dict(color=C["highlight"], width=2.5))
    _layout(fig, max(380, 22 * len(order) + 90))
    fig.update_xaxes(type="category", side="top", showgrid=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
    return fig


# --------------------------------------------------------------------------- #
# Seuil d'alerte : graphiques « bullet » (écart à la moyenne 5 ans)
# --------------------------------------------------------------------------- #
def bullet_figure(actual: float, projected: float, seuil: float, suffix: str = " %", fmt: str = "+.1f",
                  lo: float | None = None, hi: float | None = None, labels: tuple[str, str] = ("Aujourd'hui",
                                                                                                "Projection")) -> go.Figure:
    """Deux graphiques « bullet » (actuel, projeté) avec le seuil en trait noir."""
    lo = lo if lo is not None else min(-30.0, actual - 10, projected - 10)
    hi = hi if hi is not None else max(60.0, seuil + 20, actual + 10, projected + 10)
    fig = go.Figure()
    rows = [(labels[0], actual, (0.55, 1.0)), (labels[1], projected, (0.0, 0.45))]
    for title, value, (y0, y1) in rows:
        over = value > seuil
        fig.add_trace(go.Indicator(
            mode="number+gauge", value=value, domain=dict(x=[0.25, 1], y=[y0, y1]),
            number=dict(suffix=suffix, valueformat=fmt, font=dict(size=15)),
            title=dict(text=title, font=dict(size=13)),
            gauge=dict(
                shape="bullet", axis=dict(range=[lo, hi], ticksuffix=suffix if suffix.strip() == "%" else ""),
                bar=dict(color=C["danger"] if over else C["primary"], thickness=0.45),
                steps=[dict(range=[lo, seuil], color="#e4eedf"), dict(range=[seuil, hi], color="#f8e0e0")],
                threshold=dict(line=dict(color=C["ink"], width=3), thickness=0.85, value=seuil),
            ),
        ))
    return _layout(fig, 210, margin=dict(l=8, r=24, t=16, b=16))


# --------------------------------------------------------------------------- #
# Marchés d'une province
# --------------------------------------------------------------------------- #
def markets_trend_figure(dates_hist: list[pd.Timestamp], series: dict[str, list[float]], province: str,
                         province_hist: list[float]) -> go.Figure:
    x = [month_label(d) for d in dates_hist]
    fig = go.Figure()
    palette = ["#4e79a7", "#59a14f", "#b07aa1", "#76b7b2", "#edc948", "#9c755f", "#ff9da7", "#bab0ac"]
    for i, (name, values) in enumerate(series.items()):
        fig.add_trace(go.Scatter(
            x=x, y=values, mode="lines", name=name, connectgaps=False,
            line=dict(color=palette[i % len(palette)], width=1.6),
            hovertemplate="%{y:,.0f} FCFA/kg<extra>" + name + "</extra>",
        ))
    fig.add_trace(go.Scatter(
        x=x, y=province_hist, mode="lines+markers", name=f"{province} (médiane)", connectgaps=False,
        line=dict(color=C["ink"], width=3), marker=dict(size=5),
        hovertemplate="%{y:,.0f} FCFA/kg<extra>Médiane provinciale</extra>",
    ))
    _layout(fig, 360, hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0, yanchor="bottom"))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x)
    _axes(fig, y=dict(tickformat=",.0f", title="FCFA / kg"))
    return fig


# --------------------------------------------------------------------------- #
# Départements
# --------------------------------------------------------------------------- #
def department_map(
    scope: pd.DataFrame,
    geojson_scope: dict,
    selected_id: str,
    dept_xy: pd.DataFrame,
    amplitude: float,
    center: dict,
    zoom: float,
    all_provinces: bool,
    markets: pd.DataFrame | None = None,
    offline: bool = False,
) -> go.Figure:
    custom = scope[["Département", "Province", "Prix_Projete", "Ecart_Parent_pct", "Signal_Local",
                    "Source_Prix"]].to_numpy().astype(object)
    main = go.Choroplethmap(
        geojson=geojson_scope, locations=scope["Code_ID"], z=scope["Ecart_Parent_pct"],
        featureidkey="properties.shapeID", colorscale=cfg.DIVERGING_SCALE, zmid=0, zmin=-amplitude, zmax=amplitude,
        marker_opacity=0.9, marker_line_width=0.5, marker_line_color="#ffffff", customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
            "Prix projeté : %{customdata[2]:,.0f} FCFA/kg<br>"
            "Écart vs province : %{customdata[3]:+.1f} %<br>%{customdata[4]}<br>"
            "Source du prix : %{customdata[5]}<extra></extra>"
        ),
        colorbar=dict(title=dict(text="Écart (%)", side="right"), thickness=11, len=0.7),
    )
    _no_dim(main, 0.9)
    fig = go.Figure(main)
    fig.add_trace(_outline(geojson_scope, selected_id, "shapeID"))
    if markets is not None and len(markets):
        fig.add_trace(markets_trace(markets))

    if all_provinces:
        priority = set(scope.nlargest(3, "Ecart_Parent_pct")["Code_ID"]) | set(scope.nsmallest(3, "Ecart_Parent_pct")["Code_ID"])
        priority.add(selected_id)
        size = 9
    else:
        priority, size = set(scope["Code_ID"]), 11
    lab = dept_xy[dept_xy["Code_ID"].isin(priority)]
    for trace in _halo_labels(lab["lon"], lab["lat"], lab["Département"], size):
        fig.add_trace(trace)
    return _map_layout(fig, center, zoom, cfg.MAP_HEIGHT_DEPARTMENTS, offline)


def gap_bar_figure(scope: pd.DataFrame, selected_id: str, top_n: int = 10) -> go.Figure:
    """Plus forts écarts (en valeur absolue) à la province parente, barres divergentes."""
    d = scope.reindex(scope["Ecart_Parent_pct"].abs().sort_values(ascending=False).index).head(top_n)
    d = d.sort_values("Ecart_Parent_pct")
    labels = [f"{n} ({p})" for n, p in zip(d["Département"], d["Province"], strict=True)]
    fig = go.Figure(go.Bar(
        x=d["Ecart_Parent_pct"], y=labels, orientation="h",
        marker=dict(
            color=[C["danger"] if v >= 0 else C["primary"] for v in d["Ecart_Parent_pct"]],
            line=dict(color=[C["highlight"] if i == selected_id else "rgba(0,0,0,0)" for i in d["Code_ID"]], width=2.5),
        ),
        text=[f"{v:+.1f} %".replace(".", ",") for v in d["Ecart_Parent_pct"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Écart : %{x:+.1f} %<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=C["ink"], width=1))
    _layout(fig, max(300, 34 * len(d) + 70))
    _axes(fig, x=dict(ticksuffix=" %", showgrid=True, gridcolor=GRID), y=dict(showgrid=False))
    return fig


def comparison_trend_figure(
    parent_name: str, dept_name: str,
    dates_hist: list[pd.Timestamp], dates_proj: list[pd.Timestamp],
    parent_hist: list[float], parent_proj: list[float],
    dept_hist: list[float], dept_proj: list[float],
) -> go.Figure:
    x_h = [month_label(d) for d in dates_hist]
    x_p = [x_h[-1]] + [month_label(d) for d in dates_proj]

    def _last(values):
        return next((v for v in reversed(values) if pd.notna(v)), np.nan)

    fig = go.Figure()
    series = [
        (f"{parent_name} · observé", x_h, parent_hist, C["primary"], "solid"),
        (f"{parent_name} · projection", x_p, [_last(parent_hist), *parent_proj], C["primary"], "dash"),
        (f"{dept_name} · observé", x_h, dept_hist, C["positive"], "solid"),
        (f"{dept_name} · projection", x_p, [_last(dept_hist), *dept_proj], C["warning"], "dash"),
    ]
    for name, x, y, color, dash in series:
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=name, connectgaps=False,
            line=dict(color=color, width=2.5 if dash == "solid" else 2, dash=dash),
            marker=dict(size=5), hovertemplate="%{y:,.0f} FCFA/kg<extra>" + name + "</extra>",
        ))
    _today_marker(fig, x_h[-1])
    _layout(fig, 390, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="left", x=0))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x_h + x_p[1:])
    _axes(fig, y=dict(tickformat=",.0f", title="FCFA / kg"))
    return fig


# --------------------------------------------------------------------------- #
# MEB (composante céréales)
# --------------------------------------------------------------------------- #
def meb_figure(table: pd.DataFrame, threshold: float, selected: str) -> go.Figure:
    """Coût de la ration par province, actuel → projeté, avec le seuil (FCFA/ménage/mois)."""
    df = table.sort_values("Cout_Projete").reset_index(drop=True)
    xs, ys = [], []
    for r in df.itertuples():
        xs += [r.Cout_Actuel, r.Cout_Projete, None]
        ys += [r.Province, r.Province, None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#c8cdd3", width=3), hoverinfo="skip",
                             showlegend=False))
    fig.add_trace(go.Scatter(x=df["Cout_Actuel"], y=df["Province"], mode="markers", name="Actuel",
                             marker=dict(color=C["neutral"], size=9),
                             hovertemplate="<b>%{y}</b><br>Actuel : %{x:,.0f} FCFA/ménage/mois<extra></extra>"))
    over = df["Cout_Projete"] > threshold
    fig.add_trace(go.Scatter(
        x=df["Cout_Projete"], y=df["Province"], mode="markers", name="Projeté",
        marker=dict(color=[C["danger"] if o else C["primary"] for o in over], size=11, symbol="diamond"),
        customdata=df[["Variation_pct"]].to_numpy(),
        hovertemplate="<b>%{y}</b><br>Projeté : %{x:,.0f} FCFA/ménage/mois<br>Variation : %{customdata[0]:+.1f} %<extra></extra>",
    ))
    sel = df[df["Province"] == selected]
    fig.add_trace(go.Scatter(x=sel["Cout_Projete"], y=sel["Province"], mode="markers", hoverinfo="skip",
                             showlegend=False,
                             marker=dict(size=20, color="rgba(0,0,0,0)", line=dict(color=C["highlight"], width=2.5))))
    fig.add_vline(x=threshold, line=dict(color=C["ink"], width=2),
                  annotation_text="Seuil (non validé)", annotation_position="top")
    _layout(fig, max(380, 24 * len(df) + 90), legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"))
    _axes(fig, x=dict(tickformat=",.0f", showgrid=True, gridcolor=GRID, title="FCFA / ménage / mois"),
          y=dict(showgrid=False, categoryorder="array", categoryarray=df["Province"].tolist()))
    return fig


# --------------------------------------------------------------------------- #
# Fiabilité : rétro-test et couverture
# --------------------------------------------------------------------------- #
def backtest_figure(bt: pd.DataFrame) -> go.Figure:
    from plotly.subplots import make_subplots

    x = [f"M+{h}" for h in bt["Horizon"]]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Erreur moyenne de prévision (%)",
                                                        "Hausses de 10 % ou plus : signalées (%)"))
    fig.add_trace(go.Bar(x=x, y=bt["Erreur_prix_inchange_pct"], name="Prix inchangé", marker_color=C["neutral"],
                         text=bt["Erreur_prix_inchange_pct"], textposition="outside"), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=bt["Erreur_saisonnier_pct"], name="Référence saisonnière (niveau 1)",
                         marker_color=C["primary"], text=bt["Erreur_saisonnier_pct"], textposition="outside"),
                  row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=bt["Hausses_detectees_pct"], name="Hausses détectées", marker_color=C["positive"],
                         text=bt["Hausses_detectees_pct"], textposition="outside"), row=1, col=2)
    fig.add_trace(go.Bar(x=x, y=bt["Precision_signal_pct"], name="Précision du signal", marker_color=C["warning"],
                         text=bt["Precision_signal_pct"], textposition="outside"), row=1, col=2)
    _layout(fig, 340, barmode="group", legend=dict(orientation="h", y=-0.15, x=0))
    fig.update_yaxes(gridcolor=GRID, rangemode="tozero")
    fig.update_xaxes(showgrid=False)
    return fig


RELIABILITY_COLORS = {"Bonne": C["positive"], "Moyenne": C["warning"], "Faible": C["danger"], "Inactif": "#9aa3ad"}


def coverage_map(markets: pd.DataFrame, geojson: dict, center: dict, zoom: float, offline: bool = False) -> go.Figure:
    """Tous les marchés géolocalisés, colorés par fiabilité des relevés (complétude sur 24 mois)."""
    fig = go.Figure(go.Choroplethmap(
        geojson=geojson, locations=[f["properties"]["shapeISO"] for f in geojson["features"]],
        z=[0] * len(geojson["features"]), featureidkey="properties.shapeISO",
        colorscale=[[0, "#eef0f3"], [1, "#eef0f3"]], showscale=False, marker_line_width=0.6,
        marker_line_color="#ffffff", hoverinfo="skip",
    ))
    for level in ("Bonne", "Moyenne", "Faible", "Inactif"):
        d = markets[markets["Fiabilite"] == level]
        if d.empty:
            continue
        fig.add_trace(go.Scattermap(
            lon=d["lon"], lat=d["lat"], mode="markers", name=f"{level} ({len(d)})",
            marker=dict(size=9 if level != "Inactif" else 6, color=RELIABILITY_COLORS[level], opacity=0.9),
            customdata=d[["Marché", "Province", "Completude_pct"]].to_numpy().astype(object),
            hovertemplate=("<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                           "Relevés sur 24 mois : %{customdata[2]:.0f} %<extra></extra>"),
        ))
    _map_layout(fig, center, zoom, cfg.MAP_HEIGHT_PROVINCES, offline)
    fig.update_layout(legend=dict(orientation="h", y=0.01, x=0.01, bgcolor="rgba(255,255,255,0.85)"))
    return fig
