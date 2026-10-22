"""Tests de bout en bout : l'application complète s'exécute et le parcours de démonstration fonctionne."""
import pytest
from streamlit.testing.v1 import AppTest

import config as cfg

APP = str(cfg.BASE_DIR / "app.py")
VIEWS = {"Provinces": "Alerte provinciale", "Départements": "Carte des écarts", "MEB": "Coût de la ration par province",
         "Alertes": "Détail de l'alerte", "Al Aswak": "Al Aswak", "Fiabilité & données": None}


@pytest.fixture(scope="module")
def _warm():
    """Un premier lancement chauffe les caches (modèles) pour tous les tests du module."""
    AppTest.from_file(APP, default_timeout=300).run()


@pytest.fixture
def app(_warm):
    return AppTest.from_file(APP, default_timeout=300).run()


def test_initial_render(app):
    assert not app.exception and not app.error
    assert any(label.startswith("Prix actuel") for label in (m.label for m in app.metric))
    assert any(cfg.DEMO_BANNER in m.value for m in app.markdown)  # bandeau « démonstration » toujours visible


@pytest.mark.parametrize("view,heading", VIEWS.items())
def test_every_view_renders_its_own_content(app, view, heading):
    app.session_state["view"] = view
    app.run()
    assert not app.exception
    if heading:
        assert any(heading in h.value for h in app.subheader)
    else:
        assert [t.label for t in app.tabs][:3] == ["Performance des prévisions", "Niveaux de méthode",
                                                    "Qualité et couverture des données"]


def test_selections_survive_views_that_hide_their_widget(app):
    app.session_state["province"] = "Lac"
    app.session_state["view"] = "Départements"
    app.run()
    app.session_state["view"] = "Provinces"
    app.run()
    assert app.session_state["province"] == "Lac"


@pytest.mark.parametrize("horizon", cfg.HORIZONS)
def test_horizon_changes_the_projection_label(app, horizon):
    app.session_state["horizon"] = horizon
    app.run()
    assert not app.exception
    assert any(f"M+{horizon}" in m.label for m in app.metric)


@pytest.mark.parametrize("commodity", list(cfg.COMMODITIES))
@pytest.mark.parametrize("province", ["Kanem", "Tibesti", "Borkou"])
def test_products_and_provinces_without_data(app, commodity, province):
    app.session_state["commodity"] = commodity
    app.session_state["province"] = province
    app.run()
    assert not app.exception


def test_province_without_price_shows_explanation(app):
    app.session_state["province"] = "Tibesti"
    app.run()
    assert any("Aucun prix récent" in i.value for i in app.info)


def test_drill_down_and_fallback(app):
    app.session_state["province"] = "Guéra"
    app.run()
    next(b for b in app.button if b.key == "btn_drill").click().run()
    assert not app.exception and app.session_state["view"] == "Départements"
    assert app.session_state["dept_scope"] == "Guéra"
    app.session_state["view"] = "Provinces"
    app.session_state["province"] = "Tibesti"
    app.run()
    next(b for b in app.button if b.key == "btn_drill").click().run()
    assert not app.exception and app.session_state["dept_scope"] == cfg.ALL_PROVINCES


def test_replay_episode_end_to_end(app):
    """Le parcours central : épisode → relecture → alertes → validation → message au Cluster → bulletin."""
    app.selectbox(key="episode").select(0).run()
    ep = cfg.REPLAY_EPISODES[0]
    assert (app.session_state["commodity"], app.session_state["province"], app.session_state["as_of"]) == (
        ep["commodity"], ep["province"], ep["as_of"])
    assert any("Mode relecture" in m.value for m in app.markdown) and not app.exception
    cmp = next(d.value for d in app.dataframe if "Prévu" in d.value.columns)  # prévu vs réalisé
    assert len(cmp) == cfg.HORIZON and (cmp["Réalisé"] > cmp["Prévu"]).all()

    app.session_state["view"] = "Alertes"
    app.run()
    assert not app.exception and any("Relecture : qu'est-il arrivé ensuite" in s.value for s in app.success)
    key = f"Seuil de prix|{ep['commodity']}|{ep['province']}|{ep['as_of']}"
    app.selectbox(key="alert_sel").select(key).run()
    app.text_input(key="alert_comment").input("Confirmé avec la DPSA").run()
    next(b for b in app.button if b.key == "btn_validate").click().run()
    counters = {m.label: m.value for m in app.metric}
    assert str(counters["🟢 Validée"]) == "1"
    assert any("Validée par Analyste SISAAP" in c.value and ep["province"] in c.value for c in app.code)

    app.session_state["view"] = "Al Aswak"
    app.run()
    assert any("validée par Analyste SISAAP" in m.value for m in app.markdown)
    next(b for b in app.button if b.key == "btn_docx").click().run()
    assert len(app.session_state["docx"][1]) > 20_000


def test_reader_role_sees_only_validated_alerts(app):
    app.session_state["view"] = "Alertes"
    app.session_state["scenario"] = "Pression accrue"
    app.session_state["role"] = "Lecteur"
    app.run()
    assert not app.exception and not [b for b in app.button if b.key == "btn_validate"]
    assert any("Profil « Lecteur »" in i.value for i in app.info) or any("Aucune alerte" in i.value for i in app.info)


def test_offline_toggle_and_stress(app):
    app.session_state["offline"] = True
    for view in ("Provinces", "Départements", "Fiabilité & données"):
        app.session_state["view"] = view
        app.run()
        assert not app.exception, view


def test_validations_are_private_to_each_visitor(app):
    """Démo publique : la validation d'un visiteur ne doit pas apparaître chez un autre, ni être effacée par lui."""
    app.session_state["scenario"] = "Pression accrue"
    app.session_state["view"] = "Alertes"
    app.run()
    next(b for b in app.button if b.key == "btn_validate").click().run()
    assert str({m.label: m.value for m in app.metric}["🟢 Validée"]) == "1"

    other = AppTest.from_file(APP, default_timeout=300).run()
    other.session_state["scenario"] = "Pression accrue"
    other.session_state["view"] = "Alertes"
    other.run()
    assert str({m.label: m.value for m in other.metric}["🟢 Validée"]) == "0"
    next(b for b in other.button if b.key == "btn_reset_demo").click().run()  # le « reset » de l'un n'efface pas l'autre
    app.run()
    assert str({m.label: m.value for m in app.metric}["🟢 Validée"]) == "1"
