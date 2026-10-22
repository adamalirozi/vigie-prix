"""Vue « Départements » : écarts à la province parente, prix estimés depuis le marché le plus proche."""

from __future__ import annotations

import streamlit as st

import config as cfg
from services import cached, export
from ui.context import Ctx
from ui.formatting import kg, month_label_long, pct, pct_delta
from ui.views.common import CHART_CONFIG, XLSX_MIME, highlight_rows


@st.fragment
def render(ctx: Ctx, geo, on_department_click) -> None:
    """Fragment : les filtres de cette vue ne relancent pas toute la page."""
    c = ctx
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    table = cached.get_department_table(c.commodity, c.scenario, c.as_of, c.horizon, c.dk)
    scopes = [cfg.ALL_PROVINCES] + sorted(table["Province"].unique(), key=str.casefold)
    if st.session_state.get("dept_scope") not in scopes:
        st.session_state["dept_scope"] = cfg.ALL_PROVINCES

    f1, f2 = st.columns(2, gap="medium")
    scope = f1.selectbox("Province", scopes, key="dept_scope")
    df = cached.filter_scope(table, scope)
    if df.empty:
        st.info("Aucun département avec un prix dans ce périmètre.")
        return

    labels = {r["Code_ID"]: f"{r['Département']} · {r['Province']}" for r in df.to_dict("records")}
    ids = sorted(labels, key=lambda i: labels[i].casefold())
    if st.session_state.get("dept_sel") not in ids:
        st.session_state["dept_sel"] = ids[0]
    sel_id = f2.selectbox("Département sélectionné", ids, format_func=labels.get, key="dept_sel",
                          help="Vous pouvez aussi cliquer sur un département de la carte.")
    sel = table.set_index("Code_ID").loc[sel_id]

    n_up = int((df["Ecart_Parent_pct"] >= cfg.GAP_THRESHOLD).sum())
    n_down = int((df["Ecart_Parent_pct"] <= -cfg.GAP_THRESHOLD).sum())
    n_local = int((df["Distance_km"] == 0).sum())
    top, bottom = df.loc[df["Ecart_Parent_pct"].idxmax()], df.loc[df["Ecart_Parent_pct"].idxmin()]

    with st.container(key="kpi-dept"):
        k = st.columns(5)
        k[0].metric("Départements", f"{len(df)} / {len(geo.departments)}",
                    help=f"Départements du périmètre disposant d'un prix, sur {len(geo.departments)} au total.")
        k[1].metric("Avec marché local", f"{n_local} / {len(df)}",
                    help="Les autres départements prennent le prix du marché actif le plus proche (estimation).")
        k[2].metric(f"Écarts > +{int(cfg.GAP_THRESHOLD)} %", str(n_up),
                    help=f"Prix supérieur d'au moins {int(cfg.GAP_THRESHOLD)} % à celui de la province parente.")
        k[3].metric(f"Écarts < −{int(cfg.GAP_THRESHOLD)} %", str(n_down),
                    help=f"Prix inférieur d'au moins {int(cfg.GAP_THRESHOLD)} % à celui de la province parente.")
        k[4].metric(f"Projection M+{c.horizon} · {sel['Département']}", kg(sel["Prix_Projete"]),
                    f"{pct_delta(sel['Ecart_Parent_pct'])} vs province", delta_color="inverse",
                    help="Prix projeté pour le département sélectionné.")

    st.info(f"**Lecture du périmètre.** {top['Département']} ({top['Province']}) présente l'écart positif le plus "
            f"élevé ({pct(top['Ecart_Parent_pct'])}). {bottom['Département']} ({bottom['Province']}) présente "
            f"l'écart négatif le plus marqué ({pct(bottom['Ecart_Parent_pct'])}).")

    col_map, col_table = st.columns([1.35, 1.0], gap="large")
    with col_map:
        st.subheader("Carte des écarts")
        c_cap, c_tog = st.columns([2.2, 1])
        c_cap.caption(f"{len(df)} départements · {'Tchad' if scope == cfg.ALL_PROVINCES else scope} · "
                      "cliquez sur un département")
        c_tog.toggle("Afficher les marchés", key="show_markets_dept")
        st.plotly_chart(
            cached.fig_department_map(c.commodity, c.scenario, c.as_of, c.horizon, c.dk, scope, sel_id,
                                      bool(st.session_state["show_markets_dept"]), c.offline),
            key="map_departments", on_select=on_department_click, selection_mode="points",
            config=CHART_CONFIG, width="stretch",
        )
    with col_table:
        st.subheader("Classement")
        st.caption(f"Départements triés par écart absolu · scénario {c.scenario}")
        tbl = df.assign(_abs=df["Ecart_Parent_pct"].abs()).sort_values("_abs", ascending=False)[
            ["Département", "Province", "Prix_Projete", "Ecart_Parent_pct", "Source_Prix", "Signal_Local"]]
        st.dataframe(
            tbl.style.apply(highlight_rows("Département", sel["Département"]), axis=1),
            hide_index=True, width="stretch", height=max(220, min(540, 38 * (len(tbl) + 1) + 8)),
            column_config={
                "Département": st.column_config.TextColumn(pinned=True),
                "Prix_Projete": st.column_config.NumberColumn(f"Prévu M+{c.horizon} (FCFA/kg)", format="%.0f"),
                "Ecart_Parent_pct": st.column_config.NumberColumn("Écart vs province", format="%+.1f %%"),
                "Source_Prix": st.column_config.TextColumn("Source du prix"),
                "Signal_Local": st.column_config.TextColumn("Signal local"),
            },
        )
        gap = sel["Ecart_Parent_pct"]
        if gap >= cfg.GAP_THRESHOLD:
            st.warning(f"{sel['Département']} est {pct(gap)} au-dessus de sa province parente.")
        elif gap <= -cfg.GAP_THRESHOLD:
            st.info(f"{sel['Département']} est {pct(abs(gap), signed=False)} sous sa province parente.")
        else:
            st.success(f"{sel['Département']} reste à moins de {int(cfg.GAP_THRESHOLD)} % du niveau projeté "
                       "de sa province parente.")
        if sel["Distance_km"] > 0:
            st.caption(f"Prix estimé : {sel['Source_Prix']}.")

    col_bar, col_traj = st.columns([1, 1.25], gap="large")
    with col_bar:
        st.subheader("Plus forts écarts")
        st.caption("Dix départements les plus éloignés de leur province (contour = sélection)")
        st.plotly_chart(cached.fig_gap_bar(c.commodity, c.scenario, c.as_of, c.horizon, c.dk, scope, sel_id),
                        config=CHART_CONFIG, width="stretch")
    with col_traj:
        st.subheader(f"Trajectoire comparative · {sel['Département']} / {sel['Province']}")
        st.caption(f"{cfg.HISTORY_MONTHS} mois observés jusqu'à {month_label_long(model.last_obs)} ; "
                   f"projection jusqu'à {month_label_long(model.dates_proj[-1])}")
        st.plotly_chart(cached.fig_comparison(c.commodity, sel_id, c.scenario, c.as_of, c.horizon, c.dk),
                        config=CHART_CONFIG, width="stretch")

    note = (f"Source : {cfg.DATA_SOURCE}, dernier relevé {month_label_long(model.last_obs)}. Prix départementaux parfois "
            "estimés depuis le marché le plus proche (voir « Source du prix »). Non validé par le SISAAP.")
    e1, e2, _ = st.columns([1, 1, 2])
    base = f"vigie_prix_{c.commodity}_departements_m{c.horizon}"
    e1.download_button("Exporter en CSV", export.to_csv_bytes(df, export.DEPARTMENT_COLUMNS),
                       file_name=export.export_filename(base, c.scenario, "csv"), mime="text/csv",
                       key="dl_dept_csv", type="primary")
    e2.download_button("Exporter en Excel", export.to_excel_bytes(df, export.DEPARTMENT_COLUMNS, "Départements", note),
                       file_name=export.export_filename(base, c.scenario, "xlsx"), mime=XLSX_MIME, key="dl_dept_xlsx")
