"""Vue « Al Aswak » : brouillon de rubrique « Projections de prix », à relire et valider."""

from __future__ import annotations

import streamlit as st

import config as cfg
from services import bulletin as builder
from services import cached
from ui.context import Ctx
from ui.formatting import month_label_long
from ui.views.alerts import validated_alerts


def render(ctx: Ctx) -> None:
    c = ctx
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    table = cached.get_province_table(c.commodity, c.scenario, c.as_of, c.horizon, c.dk)
    if table.empty:
        st.info("Pas de données de prix récentes pour ce produit.")
        return
    has_sel = c.province in set(table["Province"])
    series = cached.get_province_series(c.commodity, c.province, c.scenario, c.as_of, c.dk) if has_sel else None
    data = builder.BulletinData(
        commodity=c.commodity, scenario=c.scenario, horizon=c.horizon, last_obs=model.last_obs,
        dates_hist=model.dates_hist, dates_proj=model.dates_proj, table=table, province=c.province, series=series,
        validated=validated_alerts(c), meb_table=cached.get_meb_table(c.scenario, c.as_of, c.horizon, c.dk),
        meb_seuil=c.meb_seuil, seuil_pct=c.seuil_pct, replay=model.is_replay,
    )

    st.caption("Brouillon généré automatiquement à partir des tables de l'application : **les analystes gardent la "
               "décision finale**. Rien n'est publiable sans relecture. Le graphique de tendance porte sur la province "
               "sélectionnée dans la barre de filtres.")
    st.warning(f"BROUILLON À VALIDER · {cfg.DEMO_BANNER}")
    st.subheader(f"Al Aswak · Projections de prix · {c.commodity} · {month_label_long(model.last_obs)}")
    for title, paragraphs in builder.sections(data).items():
        st.markdown(f"**{title}**")
        for text in paragraphs:
            st.write(text)

    st.divider()
    b1, b2, b3 = st.columns([1, 1, 2])
    key = f"docx_{c.commodity}_{c.scenario}_{c.horizon}_{c.as_of}_{c.province}_{c.seuil_pct}_{c.meb_seuil}"
    if b1.button("Préparer le fichier Word", type="primary", key="btn_docx"):
        with st.spinner("Mise en page du brouillon…"):
            st.session_state["docx"] = (key, builder.build_docx(data))
    ready = st.session_state.get("docx")
    if ready and ready[0] == key:
        b2.download_button("Télécharger le brouillon (.docx)", ready[1], key="dl_docx",
                           file_name=f"al_aswak_brouillon_{c.commodity}_{model.last_obs:%Y-%m}.docx".replace(" ", "_"),
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    else:
        b2.caption("Cliquez d'abord sur « Préparer le fichier Word ».")
    b3.download_button("Texte seul (.txt)", builder.build_text(data).encode("utf-8"),
                       file_name=f"al_aswak_brouillon_{c.commodity}_{model.last_obs:%Y-%m}.txt".replace(" ", "_"),
                       mime="text/plain", key="dl_txt")
