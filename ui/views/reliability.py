"""Vue « Fiabilité & données » : performance des prévisions, niveaux de méthode, qualité et couverture des données."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config as cfg
from services import cached, evaluation
from ui.context import Ctx
from ui.formatting import month_label_long
from ui.views.common import CHART_CONFIG

LEVELS = pd.DataFrame(
    [
        ("Niveau 1 — référence saisonnière", "Prix actuel × rapport saisonnier par province (+ dérive du scénario)",
         "Prix publics WFP", "✅ Actif dans cette démonstration", "Méthode simple à battre"),
        ("Niveau 2 — liens entre marchés et facteurs", "Corrections selon les marchés voisins, le carburant, la pluie, "
         "le conflit, les marchés frontaliers", "Pluviométrie (CHIRPS), carburant, événements, prix transfrontaliers",
         "⏳ Non connecté (phase 2, après l'audit des données)", "Retenu seulement s'il bat le niveau 1"),
        ("Niveau 3 — apprentissage automatique", "Modèles statistiques / ML calibrés sur les séries SIMPA",
         "Séries SIMPA/DPSA validées", "⏳ Non activé (phase 2)", "Retenu seulement s'il bat le niveau 2"),
    ],
    columns=["Niveau", "Principe", "Données", "Statut", "Règle de décision"],
)


def render(ctx: Ctx) -> None:
    c = ctx
    tab_perf, tab_levels, tab_data = st.tabs(["Performance des prévisions", "Niveaux de méthode",
                                              "Qualité et couverture des données"])
    with tab_perf:
        _performance(c)
    with tab_levels:
        st.caption("Le projet avance « du plus simple au plus sophistiqué » : un modèle plus complexe n'est retenu que "
                   "s'il fait mieux que la méthode simple.")
        st.dataframe(LEVELS, hide_index=True, width="stretch")
    with tab_data:
        _data_quality(c)


def _performance(c: Ctx) -> None:
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    bt = cached.get_backtest(c.commodity, c.as_of, c.dk)
    start = model.last_obs - pd.DateOffset(months=cfg.BACKTEST_TEST_MONTHS)
    st.subheader(f"Rétro-test · {c.commodity}")
    st.caption(f"Hors échantillon : prévisions refaites chaque mois de {month_label_long(start)} à "
               f"{month_label_long(model.last_obs)}, la saisonnalité n'étant estimée que sur les données antérieures. "
               "Données publiques WFP : à recalculer sur les séries SIMPA après l'audit.")
    st.info(evaluation.verdict(bt))
    st.plotly_chart(cached.fig_backtest(c.commodity, c.as_of, c.dk), config=CHART_CONFIG, width="stretch")

    last = bt.iloc[-1]
    k = st.columns(4)
    k[0].metric("Cas testés (M+3)", f"{int(last['Cas_testes']):,}".replace(",", "\u202f"))
    k[1].metric("Hausses ≥ 10 % à 3 mois", int(last["Hausses_importantes"]),
                f"{last['Part_hausses_reelles_pct']:.0f} % des cas", delta_color="off", delta_arrow="off")
    k[2].metric("Avance moyenne d'une alerte à M+3", f"{last['Avance_semaines']:.0f} semaines",
                help="Horizon de la prévision convertie en semaines : indicatif.")
    k[3].metric("Biais à M+3", f"{last['Biais_saisonnier_pct']:+.1f} %".replace(".", ","),
                help="Erreur moyenne signée de la prévision (positif = prévoit trop haut).")
    st.dataframe(
        bt.rename(columns={
            "Horizon": "Horizon (mois)", "Cas_testes": "Cas testés",
            "Erreur_prix_inchange_pct": "Erreur « prix inchangé » (%)", "Erreur_saisonnier_pct": "Erreur saisonnier (%)",
            "Biais_saisonnier_pct": "Biais saisonnier (%)", "Hausses_importantes": "Hausses ≥ 10 %",
            "Hausses_detectees_pct": "Détectées (%)", "Precision_signal_pct": "Précision du signal (%)",
            "Part_hausses_reelles_pct": "Hausses réelles (% des cas)",
            "Part_hausses_annoncees_pct": "Hausses annoncées (% des cas)", "Avance_semaines": "Avance (semaines)",
        }), hide_index=True, width="stretch")
    st.caption("Lecture : si les hausses annoncées sont bien moins fréquentes que les hausses réelles, la méthode "
               "tend à prévoir « stable » et à rater les détériorations rares, un biais connu des modèles de "
               "prévision en sécurité alimentaire. Il est mesuré ici pour être corrigé explicitement aux niveaux 2 et 3. "
               "Aucun objectif de précision n'est annoncé avant l'audit des séries du SISAAP.")


def _data_quality(c: Ctx) -> None:
    model = cached.get_model(c.commodity, c.as_of, c.dk)
    mk = cached.get_all_markets(c.commodity, c.as_of, c.dk)
    active = mk[mk["Actif"]]
    st.subheader(f"Couverture et qualité · {c.commodity}")
    st.caption("Ce que l'audit de la phase 1 produira sur les séries SIMPA, montré ici sur les données publiques WFP.")
    k = st.columns(5)
    k[0].metric("Marchés géolocalisés", len(mk))
    k[1].metric("Avec un prix récent", len(active))
    k[2].metric("Fiabilité bonne", int((mk["Fiabilite"] == "Bonne").sum()),
                help=f"≥ {cfg.RELIABILITY_GOOD:.0f} % des 24 derniers mois réellement relevés.")
    k[3].metric("Relevés isolés écartés", model.n_outliers)
    k[4].metric("Mois synchronisés écartés", len(model.sync_months),
                help="Mois où tous les marchés bougent ensemble puis reviennent : probable artefact de collecte.")
    if model.sync_months:
        st.warning("**Anomalies synchronisées détectées** (à confirmer avec le SISAAP) : " + " · ".join(
            f"{month_label_long(d)} (écart médian ×{v:.2f})".replace(".", ",") for d, v in model.sync_months.items()))

    col_map, col_tbl = st.columns([1.3, 1], gap="large")
    with col_map:
        st.caption("Marchés colorés par fiabilité des relevés (part des 24 derniers mois réellement relevés)")
        st.plotly_chart(cached.fig_coverage(c.commodity, c.as_of, c.dk, c.offline), config=CHART_CONFIG,
                        width="stretch")
    with col_tbl:
        prov = (mk.groupby("Province").agg(Marchés=("market_id", "count"), Actifs=("Actif", "sum"),
                                           Complétude=("Completude_pct", "mean"), Dernier=("Derniere_Obs", "max"))
                .reset_index())
        prov["Dernier"] = prov["Dernier"].map(lambda d: month_label_long(d) if pd.notna(d) else "—")
        st.caption("Par province")
        st.dataframe(prov, hide_index=True, width="stretch", height=420, column_config={
            "Complétude": st.column_config.NumberColumn("Relevés / 24 mois", format="%.0f %%"),
            "Dernier": st.column_config.TextColumn("Dernier relevé"),
        })

    st.subheader("Marchés pilotes proposés")
    st.caption(f"Les {cfg.PILOT_MARKETS_N} marchés les plus fiables, au plus un par province : proposition de départ "
               "pour la phase 1, à discuter avec le SISAAP.")
    pilots = evaluation.pilot_markets(mk)
    out = pilots[["Marché", "Province", "Département", "Completude_pct", "Fiabilite", "Derniere_Obs"]].assign(
        Derniere_Obs=pilots["Derniere_Obs"].map(month_label_long))
    st.dataframe(out, hide_index=True, width="stretch", column_config={
        "Completude_pct": st.column_config.NumberColumn("Relevés / 24 mois", format="%.0f %%"),
        "Fiabilite": st.column_config.TextColumn("Fiabilité"),
        "Derniere_Obs": st.column_config.TextColumn("Dernier relevé"),
    })
    st.download_button("Exporter la liste (CSV)", out.to_csv(index=False).encode("utf-8-sig"),
                       file_name="marches_pilotes_proposes.csv", mime="text/csv", key="dl_pilots")
