"""Vue « Provinces » : situation, prévisions à M+1/M+2/M+3, carte, marchés."""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

import config as cfg
from services import cached, export
from ui import components as ui
from ui.context import Ctx
from ui.formatting import kg, month_label, month_label_long, pct, pct_delta
from ui.views.common import CHART_CONFIG, METRIC_CHOICES, XLSX_MIME, highlight_rows


def render(ctx: Ctx, geo, on_province_click, go_to_departments) -> None:
    c = ctx
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    table = cached.get_province_table(c.commodity, c.scenario, c.as_of, c.horizon, c.dk)
    missing = cached.get_missing_provinces(c.commodity, c.as_of, c.dk)
    has_sel = c.province in set(table["Province"])
    row = table.set_index("Province").loc[c.province] if has_sel else None
    series = cached.get_province_series(c.commodity, c.province, c.scenario, c.as_of, c.dk) if has_sel else None
    proj_dev = row["Ecart_Moy5_Projete_pct"] if has_sel else float("nan")
    over = bool(has_sel and pd.notna(proj_dev) and proj_dev > c.seuil_pct)
    h_label = f"M+{c.horizon} ({month_label(model.dates_proj[c.horizon - 1])})"

    # -- Indicateurs clés ------------------------------------------------- #
    with st.container(key="kpi-alert" if over else "kpi-ok" if has_sel else "kpi-none"):
        k = st.columns(5)
        k[0].metric(
            f"Variation médiane projetée · {h_label}", pct(table["Variation_pct"].median()),
            f"{int((table['Vigilance'] == 'Élevé').sum())} provinces en vigilance élevée",
            delta_color="off", delta_arrow="off",
            help="Médiane des variations projetées. Seuils de vigilance proportionnels à l'horizon "
                 f"(élevée ≥ {cfg.ALERT_HIGH * c.horizon / cfg.HORIZON:.0f} %, modérée ≥ "
                 f"{cfg.ALERT_MID * c.horizon / cfg.HORIZON:.0f} % à M+{c.horizon}).",
        )
        k[1].metric(
            "Écart médian à la moyenne 5 ans", pct(table["Ecart_Moy5_pct"].median()),
            f"{pct_delta(table['YoY_pct'].median())} sur 1 an (médiane)", delta_color="inverse",
            help="Prix actuel comparé à la moyenne du même mois sur les 5 années précédentes, médiane des provinces.",
        )
        if has_sel:
            k[2].metric(
                f"Prix actuel · {c.province}", kg(row["Prix_Actuel"]),
                f"{pct_delta(row['YoY_pct'])} sur 1 an" if pd.notna(row["YoY_pct"]) else None, delta_color="inverse",
                chart_data=pd.Series(series["hist"]).ffill().bfill().tolist() + series["proj"], chart_type="line",
                help=f"Médiane de {int(row['Nb_Marches'])} marché(s) actif(s). La courbe montre {cfg.HISTORY_MONTHS} "
                     "mois observés puis la projection.",
            )
            k[3].metric(f"Projection · {h_label}", kg(row["Prix_Projete"]), pct_delta(row["Variation_pct"]),
                        delta_color="inverse", help="Saisonnalité de la province et dérive du scénario.")
            k[4].metric("Écart projeté à la moyenne 5 ans", pct(proj_dev) if pd.notna(proj_dev) else "n.d.",
                        f"seuil d'alerte (non validé) : +{c.seuil_pct} %", delta_color="off", delta_arrow="off",
                        help="Prix projeté comparé à la moyenne 5 ans du mois correspondant.")
        else:
            for card, label in zip(k[2:], ("Prix actuel", "Projection", "Écart projeté à la moyenne 5 ans"), strict=True):
                card.metric(f"{label} · {c.province}", "n.d.", help="Aucun prix récent pour cette province.")
    gaps = ", ".join(f"{r.Province} (dernier relevé : {r.Dernier_Releve})" for r in missing.itertuples())
    st.caption(f"{c.commodity} · scénario {c.scenario} · prix en {cfg.UNIT} · {len(table)} provinces sur "
               f"{len(geo.provinces)}" + (f" · sans prix récent : {gaps}" if gaps else ""))

    # -- Carte + tendance -------------------------------------------------- #
    col_map, col_trend = st.columns([1.55, 1.0], gap="large")
    with col_map:
        st.subheader("Alerte provinciale")
        c_metric, c_markets = st.columns([2.2, 1])
        with c_metric:
            st.segmented_control("Colorier par", list(METRIC_CHOICES), key="map_metric", label_visibility="collapsed")
        with c_markets:
            st.toggle("Afficher les marchés", key="show_markets")
        metric = METRIC_CHOICES[st.session_state.get("map_metric") or "Prix projeté"]
        st.caption("Cliquez sur une province pour la sélectionner · points noirs : marchés suivis")
        code = geo.provinces.set_index("Province").loc[c.province, "Code_ID"]
        st.plotly_chart(
            cached.fig_province_map(c.commodity, c.scenario, c.as_of, c.horizon, c.dk, code, metric,
                                    bool(st.session_state["show_markets"]), c.offline),
            key="map_provinces", on_select=on_province_click, selection_mode="points",
            config=CHART_CONFIG, width="stretch",
        )
    with col_trend:
        st.subheader(f"Tendance · {c.province}")
        if has_sel:
            st.caption("Observé, projection avec intervalle à 80 %, moyenne 5 ans, seuil d'alerte et soudure"
                       + (" · en vert : prix réalisés" if model.is_replay else ""))
            st.plotly_chart(cached.fig_trend(c.commodity, c.province, c.scenario, c.as_of, c.horizon, c.dk,
                                             c.seuil_pct), config=CHART_CONFIG, width="stretch")
            if model.is_replay and series["actual"]:
                cmp = pd.DataFrame({
                    "Mois": [month_label_long(d) for d in model.dates_proj],
                    "Prévu": series["proj"], "Réalisé": series["actual"],
                })
                cmp["Écart"] = (cmp["Prévu"] / cmp["Réalisé"] - 1) * 100
                st.dataframe(cmp, hide_index=True, width="stretch", column_config={
                    "Prévu": st.column_config.NumberColumn("Prévu (FCFA/kg)", format="%.0f"),
                    "Réalisé": st.column_config.NumberColumn("Réalisé (FCFA/kg)", format="%.0f"),
                    "Écart": st.column_config.NumberColumn("Prévu vs réalisé", format="%+.0f %%"),
                })
        else:
            last = missing.set_index("Province").loc[c.province, "Dernier_Releve"]
            st.info(f"Aucun prix récent pour {c.province} (dernier relevé : {last}). "
                    "La province est affichée en gris sur la carte.")
        st.button(f"Voir les départements de {c.province}", on_click=go_to_departments, key="btn_drill")

    # -- Comparaisons ------------------------------------------------------ #
    st.divider()
    col_dumb, col_quad = st.columns([1, 1], gap="large")
    with col_dumb:
        st.subheader("Classement des provinces")
        st.caption(f"Prix actuel (gris) et prix projeté à M+{c.horizon} (couleur = niveau de vigilance)")
        st.plotly_chart(cached.fig_dumbbell(c.commodity, c.province, c.scenario, c.as_of, c.horizon, c.dk),
                        config=CHART_CONFIG, width="stretch")
    with col_quad:
        st.subheader("Niveau de prix et écart à la moyenne")
        st.caption("Au-dessus de la ligne noire : prix supérieur à la moyenne des 5 dernières années")
        st.plotly_chart(cached.fig_quadrant(c.commodity, c.province, c.scenario, c.as_of, c.horizon, c.dk),
                        config=CHART_CONFIG, width="stretch")

    st.subheader("Écart à la moyenne 5 ans, mois par mois")
    st.caption("Rouge : au-dessus de la moyenne du même mois · bleu : en dessous · à droite du pointillé : projection")
    st.plotly_chart(cached.fig_heatmap(c.commodity, c.province, c.scenario, c.as_of, c.horizon, c.dk),
                    config=CHART_CONFIG, width="stretch")

    # -- Tableau ------------------------------------------------------------ #
    st.subheader("Comparaison provinciale")
    st.caption(f"Triée par variation projetée à M+{c.horizon} · colonnes triables")
    view_df = ui.with_level_icon(table).assign(Pic=table["Mois_Pic"].map(month_label)).sort_values(
        "Variation_pct", ascending=False)[
        ["Province", "Prix_Actuel", "Prix_Projete", "Variation_pct", "Ecart_Moy5_pct", "YoY_pct", "Niveau", "Pic",
         "Nb_Marches", "Completude_pct", "Sparkline"]]
    vmax = max(10.0, math.ceil(view_df["Variation_pct"].max()))
    vmin = min(0.0, math.floor(view_df["Variation_pct"].min()))
    st.dataframe(
        view_df.style.apply(highlight_rows("Province", c.province), axis=1),
        hide_index=True, width="stretch", height=520,
        column_config={
            "Province": st.column_config.TextColumn("Province", pinned=True),
            "Prix_Actuel": st.column_config.NumberColumn("Prix actuel (FCFA/kg)", format="%.0f"),
            "Prix_Projete": st.column_config.NumberColumn(f"Prix projeté M+{c.horizon}", format="%.0f"),
            "Variation_pct": st.column_config.ProgressColumn("Variation projetée", format="%+.1f %%",
                                                             min_value=vmin, max_value=vmax),
            "Ecart_Moy5_pct": st.column_config.NumberColumn("Écart moy. 5 ans", format="%+.1f %%"),
            "YoY_pct": st.column_config.NumberColumn("Sur 1 an", format="%+.1f %%"),
            "Niveau": st.column_config.TextColumn("Vigilance"),
            "Pic": st.column_config.TextColumn("Pic prévu", help="Mois du prix le plus élevé sur l'horizon de 3 mois."),
            "Nb_Marches": st.column_config.NumberColumn("Marchés", format="%d"),
            "Completude_pct": st.column_config.NumberColumn("Relevés / 24 mois", format="%.0f %%",
                                                            help="Fiabilité : part des mois réellement relevés."),
            "Sparkline": st.column_config.LineChartColumn(f"Tendance ({cfg.HISTORY_MONTHS} mois + projection)"),
        },
    )

    # -- Marchés -------------------------------------------------------------- #
    st.divider()
    mt = cached.get_market_table(c.commodity, c.scenario, c.as_of, c.horizon, c.dk)
    st.subheader(f"Marchés · {c.province}")
    in_prov = mt[mt["Province"] == c.province].sort_values("Marché")
    if in_prov.empty:
        st.info(f"Aucun marché avec un prix récent pour {c.commodity.lower()} dans cette province.")
    else:
        col_chart, col_tbl = st.columns([1.3, 1], gap="large")
        with col_chart:
            st.caption("Prix par marché (traits fins) et médiane provinciale (trait épais)")
            st.plotly_chart(cached.fig_markets_trend(c.commodity, c.province, c.as_of, c.dk),
                            config=CHART_CONFIG, width="stretch")
        with col_tbl:
            st.caption(f"{len(in_prov)} marché(s) actif(s) · prévision par marché à M+{c.horizon}")
            st.dataframe(
                in_prov[["Marché", "Département", "Prix_Actuel", "Prix_Projete", "Variation_pct", "Fiabilite",
                         "Completude_pct"]],
                hide_index=True, width="stretch", height=min(360, 38 * (len(in_prov) + 1) + 8),
                column_config={
                    "Prix_Actuel": st.column_config.NumberColumn("Prix actuel", format="%.0f"),
                    "Prix_Projete": st.column_config.NumberColumn(f"Prévu M+{c.horizon}", format="%.0f"),
                    "Variation_pct": st.column_config.NumberColumn("Variation", format="%+.1f %%"),
                    "Fiabilite": st.column_config.TextColumn("Fiabilité"),
                    "Completude_pct": st.column_config.NumberColumn("Relevés / 24 mois", format="%.0f %%"),
                },
            )
    st.subheader("Marchés les plus exposés")
    st.caption(f"Écart du prix projeté à M+{c.horizon} à la moyenne 5 ans, tous marchés · la fiabilité des relevés est "
               "affichée, jamais masquée : une exposition sur un marché peu fiable est à vérifier")
    top = mt.dropna(subset=["Ecart_Moy5_Projete_pct"]).sort_values("Ecart_Moy5_Projete_pct", ascending=False).head(10)
    st.dataframe(
        top[["Marché", "Province", "Prix_Actuel", "Prix_Projete", "Ecart_Moy5_Projete_pct", "Fiabilite",
             "Completude_pct"]],
        hide_index=True, width="stretch",
        column_config={
            "Prix_Actuel": st.column_config.NumberColumn("Prix actuel", format="%.0f"),
            "Prix_Projete": st.column_config.NumberColumn(f"Prévu M+{c.horizon}", format="%.0f"),
            "Ecart_Moy5_Projete_pct": st.column_config.NumberColumn("Écart moy. 5 ans (prévu)", format="%+.1f %%"),
            "Fiabilite": st.column_config.TextColumn("Fiabilité"),
            "Completude_pct": st.column_config.NumberColumn("Relevés / 24 mois", format="%.0f %%"),
        },
    )

    # -- Seuil d'alerte ------------------------------------------------------ #
    st.divider()
    st.subheader("Seuil d'alerte de prix")
    st.caption(f"Écart à la moyenne des 5 dernières années · seuil +{c.seuil_pct} % (non validé par le SISAAP)")
    if has_sel and pd.notna(row["Ecart_Moy5_pct"]) and pd.notna(proj_dev):
        col_bullet, col_status = st.columns([1.7, 1], gap="large")
        with col_bullet:
            st.plotly_chart(cached.fig_bullet(float(row["Ecart_Moy5_pct"]), float(proj_dev), float(c.seuil_pct), "pct"),
                            config=CHART_CONFIG, width="stretch")
        with col_status:
            if over:
                st.warning(f"**{c.province}** : le prix projeté ({kg(row['Prix_Projete'])}) dépasse la moyenne 5 ans de "
                           f"{pct(proj_dev, signed=False)}, soit {proj_dev - c.seuil_pct:.1f} points au-dessus du seuil.")
            else:
                st.success(f"**{c.province}** : le prix projeté ({kg(row['Prix_Projete'])}) reste sous le seuil "
                           f"({pct(proj_dev)} vs moyenne 5 ans, seuil +{c.seuil_pct} %).")
    else:
        st.info("Comparaison indisponible : pas de prix récent ou moyenne 5 ans non calculable.")

    # -- Exports -------------------------------------------------------------- #
    note = (f"Source : {cfg.DATA_SOURCE}, dernier relevé {month_label_long(model.last_obs)}. "
            "Projections et scénarios illustratifs ; non validé par le SISAAP.")
    e1, e2, _ = st.columns([1, 1, 2])
    base = f"vigie_prix_{c.commodity}_provinces_m{c.horizon}"
    e1.download_button("Exporter en CSV", export.to_csv_bytes(table, export.PROVINCE_COLUMNS),
                       file_name=export.export_filename(base, c.scenario, "csv"), mime="text/csv",
                       key="dl_prov_csv", type="primary")
    e2.download_button("Exporter en Excel", export.to_excel_bytes(table, export.PROVINCE_COLUMNS, "Provinces", note),
                       file_name=export.export_filename(base, c.scenario, "xlsx"), mime=XLSX_MIME, key="dl_prov_xlsx")
