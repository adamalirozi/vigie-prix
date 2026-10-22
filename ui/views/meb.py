"""Vue « MEB » : coût de la ration céréalière du panier de dépenses minimum, projeté, et seuil."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config as cfg
from services import cached, meb
from ui.context import Ctx
from ui.formatting import fcfa, month_label, pct, pct_delta
from ui.views.common import CHART_CONFIG


def render(ctx: Ctx) -> None:
    c = ctx
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    basket = cached.get_basket()
    table = cached.get_meb_table(c.scenario, c.as_of, c.horizon, c.dk)
    h_label = f"M+{c.horizon} ({month_label(model.dates_proj[c.horizon - 1])})"

    st.caption("Composante **céréales** du MEB uniquement : composition provisoire, à remplacer par celle validée "
               "par le Cluster Sécurité Alimentaire (fichier `data/meb_composition.csv`). Seuil non validé.")
    if table.empty:
        st.info("Aucune province ne dispose d'un prix récent pour tous les produits du panier.")
        return

    over = table[table["Cout_Projete"] > c.meb_seuil]
    has_sel = c.province in set(table["Province"])
    row = table.set_index("Province").loc[c.province] if has_sel else None

    with st.container(key="kpi-alert" if len(over) else "kpi-ok"):
        k = st.columns(4)
        k[0].metric("Coût médian actuel", fcfa(table["Cout_Actuel"].median()), help="FCFA par ménage et par mois.")
        k[1].metric(f"Coût médian projeté · {h_label}", fcfa(table["Cout_Projete"].median()),
                    pct_delta((table["Cout_Projete"].median() / table["Cout_Actuel"].median() - 1) * 100),
                    delta_color="inverse")
        k[2].metric("Provinces au-dessus du seuil", f"{len(over)} / {len(table)}",
                    f"seuil : {fcfa(c.meb_seuil)}", delta_color="off", delta_arrow="off",
                    help="Coût projeté supérieur au seuil réglé dans la barre de filtres (non validé).")
        k[3].metric("Écart médian à la moyenne 5 ans", pct(table["Ecart_Moy5_pct"].median()),
                    help="Coût actuel comparé au coût moyen du même mois sur les 5 années précédentes.")

    col_fig, col_detail = st.columns([1.25, 1], gap="large")
    with col_fig:
        st.subheader("Coût de la ration par province")
        st.caption("Actuel (gris) → projeté (rouge s'il dépasse le seuil) · FCFA par ménage et par mois")
        st.plotly_chart(cached.fig_meb(c.scenario, c.as_of, c.horizon, c.dk, c.meb_seuil, c.province),
                        config=CHART_CONFIG, width="stretch")
    with col_detail:
        st.subheader(f"Détail · {c.province}")
        if not has_sel:
            st.info("Pas de prix récent pour tous les produits du panier dans cette province.")
        else:
            st.plotly_chart(cached.fig_bullet(float(row["Cout_Actuel"]), float(row["Cout_Projete"]),
                                              float(c.meb_seuil), "meb"), config=CHART_CONFIG, width="stretch")
            if row["Cout_Projete"] > c.meb_seuil:
                st.warning(f"**{c.province}** : coût projeté {fcfa(row['Cout_Projete'])}, soit "
                           f"{fcfa(row['Cout_Projete'] - c.meb_seuil)} au-dessus du seuil.")
            else:
                st.success(f"**{c.province}** : coût projeté {fcfa(row['Cout_Projete'])}, sous le seuil de "
                           f"{fcfa(c.meb_seuil)}.")
            kgm = meb.kg_per_household_month(basket)
            detail = pd.DataFrame([{
                "Produit": p, "kg / ménage / mois": q, "Prix actuel": row[f"a_{p}"], "Prix projeté": row[f"p_{p}"],
                "Coût actuel": q * row[f"a_{p}"], "Coût projeté": q * row[f"p_{p}"],
            } for p, q in kgm.items()])
            st.dataframe(detail, hide_index=True, width="stretch", column_config={
                "kg / ménage / mois": st.column_config.NumberColumn(format="%.1f"),
                "Prix actuel": st.column_config.NumberColumn("Prix actuel (FCFA/kg)", format="%.0f"),
                "Prix projeté": st.column_config.NumberColumn("Prix projeté (FCFA/kg)", format="%.0f"),
                "Coût actuel": st.column_config.NumberColumn(format="%.0f"),
                "Coût projeté": st.column_config.NumberColumn(format="%.0f"),
            })

    with st.expander("Composition du panier utilisée (provisoire)"):
        st.dataframe(basket, hide_index=True, width="stretch")
        st.caption(f"Ménage de {cfg.HOUSEHOLD_SIZE} personnes, {cfg.DAYS_PER_MONTH} jours par mois. Les produits "
                   "complémentaires du MEB (viande séchée, légumineuses, huile, sel) et la part non alimentaire "
                   "s'ajouteront dès réception de la composition validée.")

    out = table[["Province", "Cout_Actuel", "Cout_Projete", "Variation_pct", "Ref_5ans", "Ecart_Moy5_pct"]].rename(
        columns={"Cout_Actuel": "Coût actuel (FCFA/ménage/mois)", "Cout_Projete": f"Coût projeté M+{c.horizon}",
                 "Variation_pct": "Variation (%)", "Ref_5ans": "Coût moyen 5 ans", "Ecart_Moy5_pct": "Écart moy. 5 ans (%)"})
    st.download_button("Exporter le coût du MEB (CSV)", out.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"vigie_prix_meb_cereales_m{c.horizon}.csv", mime="text/csv", key="dl_meb",
                       type="primary")
