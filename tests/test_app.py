"""Test de bout en bout de l'interface avec le banc de test officiel de Streamlit."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from renovation_gantt.phases import EtatProjet

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_demarrage_sans_etat():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Sélectionnez" in i.value for i in at.info)


def test_generation_du_planning_pour_chaque_etat():
    at = AppTest.from_file(APP, default_timeout=30).run()
    for etat in EtatProjet:
        at.selectbox(key="etat").set_value(etat).run()
        assert not at.exception, etat
        assert at.metric[0].label == "Date de fin estimée"


def test_modifier_une_duree_decale_la_fin():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="etat").set_value(EtatProjet.MOE_SELECTIONNEE).run()
    fin_avant = at.metric[1].value
    at.number_input(key="duree_DET").set_value(30).run()
    assert not at.exception
    assert at.metric[1].value != fin_avant


def test_autorisation_et_pdf():
    from renovation_gantt.phases import TypeAutorisation

    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="etat").set_value(EtatProjet.MOE_SELECTIONNEE).run()
    fin_dp = at.metric[0].value
    at.selectbox(key="type_autorisation").set_value(TypeAutorisation.PC_ERP).run()
    at.checkbox(key="purge_recours").check().run()
    assert not at.exception
    assert at.metric[0].value != fin_dp
    assert at.metric[3].label == "Temps d'attente"


def test_batiment_scolaire_et_agenda():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="etat").set_value(EtatProjet.MOE_SELECTIONNEE).run()
    fin = at.metric[0].value
    at.toggle(key="batiment_scolaire").set_value(True).run()
    assert not at.exception
    assert any("Les travaux démarrent" in i.value for i in at.info)
    assert at.metric[0].value != fin


def test_onglet_suivi_avec_avancement_et_reference():
    from datetime import date

    from renovation_gantt.avancement import Avancement, Statut

    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["avancement"] = {"CT_CSPS": Avancement(Statut.TERMINEE, date(2025, 1, 6), date(2025, 3, 3))}
    at.run()
    at.selectbox(key="etat").set_value(EtatProjet.MOE_SELECTIONNEE).run()
    assert not at.exception
    assert any("Planning actualisé" in c.value for c in at.caption)
    figer = next(b for b in at.button if "Figer" in b.label)
    figer.click().run()
    assert not at.exception
    assert len(at.session_state["references"]) == 1
    assert any("Météo du projet : Dans les temps" in s.value for s in at.success)
