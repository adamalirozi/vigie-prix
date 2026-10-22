"""Vue « Alertes » : propositions, validation par un analyste, journal, message au Cluster."""

from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

import config as cfg
from services import alerts as engine
from services import cached
from ui.context import Ctx
from ui.formatting import month_label_long

STATUS_ICON = {"À valider": "🟡", "Validée": "🟢", "Suspendue": "⏸️", "Rejetée": "⚪"}
CONF_ICON = {"Élevée": "●●●", "Moyenne": "●●○", "Faible": "●○○"}


def get_store() -> engine.AlertStore:
    """Magasin des validations : propre à la session du visiteur en démonstration publique, partagé sinon."""
    if cfg.ISOLATE_SESSIONS:
        sid = st.session_state.setdefault("_sid", uuid.uuid4().hex[:12])
        return engine.AlertStore(cfg.STATE_DIR / "sessions" / sid)
    return engine.AlertStore()


def _decide(store: engine.AlertStore, key: str, status: str, user: str, label: str) -> None:
    comment = st.session_state.get("alert_comment", "")
    store.set_status(key, status, user, comment, label)
    st.session_state["alert_comment"] = ""


def render(ctx: Ctx) -> None:
    c = ctx
    store = get_store()
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    raw = cached.get_alerts(c.scenario, c.as_of, c.horizon, c.seuil_pct, c.meb_seuil, c.dk)

    st.caption("Les alertes sont des **propositions** calculées par la méthode de niveau 1. Seules celles **validées** "
               "par un analyste du SISAAP peuvent être transmises au Cluster. Seuils : non validés (démonstration).")
    if raw.empty:
        st.info("Aucune alerte proposée avec les réglages actuels (produit, scénario, horizon et seuils). "
                "Essayez le scénario « Pression accrue » ou rejouez un épisode de la soudure 2024.")
        return

    df = engine.with_status(raw, store)
    if not c.is_analyst:
        df = df[df["Statut"] == "Validée"]
        st.info("Profil « Lecteur » : seules les alertes validées sont visibles. Passez au profil « Analyste SISAAP » "
                "pour valider ou suspendre.")

    counts = engine.with_status(raw, store)["Statut"].value_counts()
    with st.container(key="kpi-alerts"):
        k = st.columns(5)
        for col, status in zip(k[:4], cfg.ALERT_STATUSES, strict=True):
            col.metric(f"{STATUS_ICON[status]} {status}", int(counts.get(status, 0)))
        k[4].metric("Alertes proposées", len(raw), help="Tous produits, province par province, pour l'horizon choisi.")

    if model.is_replay:
        done = raw[raw["Constate"].isin(["Confirmée", "Non confirmée"])]
        if len(done):
            by = done.groupby("Type")["Constate"].apply(lambda s: f"{(s == 'Confirmée').sum()} / {len(s)}")
            st.success("**Relecture : qu'est-il arrivé ensuite ?** Alertes confirmées par les prix réalisés — "
                       + " · ".join(f"{t} : {v}" for t, v in by.items()) +
                       ". Une alerte « seuil de prix » reste confirmée tant que le prix demeure au-dessus du seuil ; "
                       "une « hausse rapide » exige que la hausse de 10 % ou plus ait bien eu lieu.")

    f1, f2 = st.columns(2)
    status_filter = f1.segmented_control("Statut", ["Tous", *cfg.ALERT_STATUSES], key="alert_status_filter") or "Tous"
    type_filter = f2.segmented_control("Type", ["Tous", *engine.TYPES], key="alert_type_filter") or "Tous"
    view = df
    if status_filter != "Tous":
        view = view[view["Statut"] == status_filter]
    if type_filter != "Tous":
        view = view[view["Type"] == type_filter]
    if view.empty:
        st.info("Aucune alerte pour ce filtre.")
        return

    show = view.assign(
        Statut_txt=view["Statut"].map(lambda s: f"{STATUS_ICON[s]} {s}"),
        Premier=view["Premier_Mois"].map(month_label_long) + " (M+" + view["Premier_Mois_k"].astype(str) + ")",
        Conf=view["Confiance"].map(lambda x: f"{CONF_ICON[x]} {x}"),
    )
    cols = ["Statut_txt", "Type", "Produit", "Province", "Premier", "Valeur_Projetee", "Unite", "Seuil", "Conf"]
    if model.is_replay:
        cols += ["Constate_pct", "Constate"]
    st.dataframe(
        show[cols], hide_index=True, width="stretch", height=min(480, 38 * (len(show) + 1) + 8),
        column_config={
            "Statut_txt": st.column_config.TextColumn("Statut"),
            "Premier": st.column_config.TextColumn("Premier dépassement"),
            "Valeur_Projetee": st.column_config.NumberColumn("Valeur projetée", format="%.0f"),
            "Unite": st.column_config.TextColumn("Unité"),
            "Conf": st.column_config.TextColumn("Confiance"),
            "Constate_pct": st.column_config.NumberColumn("Évolution constatée", format="%+.0f %%"),
            "Constate": st.column_config.TextColumn("Constaté"),
        },
    )

    # -- Traitement par un analyste ---------------------------------------- #
    keys = view["Cle"].tolist()
    labels = {r.Cle: f"{r.Type} · {r.Produit} · {r.Province} · {r.Statut}" for r in view.itertuples()}
    if st.session_state.get("alert_sel") not in keys:
        st.session_state["alert_sel"] = keys[0]
    st.subheader("Détail de l'alerte")
    key = st.selectbox("Alerte", keys, format_func=labels.get, key="alert_sel")
    a = view.set_index("Cle").loc[key]
    d1, d2 = st.columns(2, gap="large")
    with d1:
        st.markdown(f"**{a['Type']} — {a['Produit']} — {a['Province']}**")
        st.write(f"Premier dépassement prévu : **{month_label_long(a['Premier_Mois'])}** (M+{a['Premier_Mois_k']}) · "
                 f"valeur projetée **{a['Valeur_Projetee']:,.0f} {a['Unite']}**".replace(",", "\u202f"))
        st.write(f"Seuil : {a['Seuil']}")
        st.write(f"Confiance **{a['Confiance'].lower()}** : " + " · ".join(a["Motifs_confiance"]))
        if a["Statut"] != "À valider":
            st.write(f"{STATUS_ICON[a['Statut']]} {a['Statut']} par {a['Valide_par']} le {a['Date_decision'][:10]}"
                     + (f" — « {a['Commentaire']} »" if a["Commentaire"] else ""))
    with d2:
        st.markdown("**Facteurs principaux**")
        for f in a["Facteurs"]:
            st.write(f"• {f}")
    if c.is_analyst:
        st.text_input("Commentaire de l'analyste (optionnel)", key="alert_comment")
        b1, b2, b3, b4 = st.columns(4)
        label = labels[key]
        b1.button("Valider", type="primary", on_click=_decide, args=(store, key, "Validée", c.role, label),
                  key="btn_validate")
        b2.button("Suspendre", on_click=_decide, args=(store, key, "Suspendue", c.role, label), key="btn_suspend")
        b3.button("Rejeter", on_click=_decide, args=(store, key, "Rejetée", c.role, label), key="btn_reject")
        b4.button("Remettre à valider", on_click=_decide, args=(store, key, "À valider", c.role, label),
                  key="btn_reset_one")

    export_df = view[["Statut", "Type", "Produit", "Province", "Premier_Mois", "Premier_Mois_k", "Valeur_Projetee", "Unite",
                      "Seuil", "Confiance", "Valide_par", "Date_decision", "Commentaire"]].assign(
        Premier_Mois=view["Premier_Mois"].dt.strftime("%Y-%m"))
    st.download_button("Exporter les alertes affichées (CSV)", export_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"vigie_prix_alertes_{model.last_obs:%Y-%m}_m{c.horizon}.csv", mime="text/csv",
                       key="dl_alerts")

    # -- Transmission au Cluster (analyste) ----------------------------------- #
    if c.is_analyst:
        st.divider()
        st.subheader("Message au Cluster Sécurité Alimentaire")
        validated = engine.with_status(raw, store)
        validated = validated[validated["Statut"] == "Validée"]
        msg = engine.cluster_message(validated, f"{model.last_obs:%Y-%m}", c.scenario, c.horizon)
        st.caption(f"{len(validated)} alerte(s) validée(s) incluse(s). Message à relire avant envoi : "
                   "l'application n'envoie rien.")
        st.code(msg, language=None, wrap_lines=True)
        st.download_button("Télécharger le message (.txt)", msg.encode("utf-8"),
                           file_name=f"message_cluster_{model.last_obs:%Y-%m}.txt", mime="text/plain",
                           key="dl_cluster")
        with st.expander("Journal des validations"):
            log = store.log()
            if log.empty:
                st.write("Aucune action enregistrée.")
            else:
                st.dataframe(log.rename(columns={"le": "Date", "par": "Par", "alerte": "Alerte", "statut": "Statut",
                                                 "commentaire": "Commentaire"}).drop(columns="cle"),
                             hide_index=True, width="stretch")
            st.button("Réinitialiser la démonstration (efface validations et journal)", on_click=store.reset,
                      key="btn_reset_demo")


def validated_alerts(ctx: Ctx) -> pd.DataFrame:
    """Alertes validées pour la période courante (utilisées par le bulletin)."""
    raw = cached.get_alerts(ctx.scenario, ctx.as_of, ctx.horizon, ctx.seuil_pct, ctx.meb_seuil, ctx.dk)
    if raw.empty:
        return raw.assign(Statut=[], Valide_par=[], Date_decision=[], Commentaire=[])
    df = engine.with_status(raw, get_store())
    return df[df["Statut"] == "Validée"]
