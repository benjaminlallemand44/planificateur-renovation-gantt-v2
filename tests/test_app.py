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


def test_onglet_budget():
    from renovation_gantt.budget import Financeur

    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["financeurs_base"] = [Financeur("DETR", 50), Financeur("Région", 40)]
    at.run()
    at.selectbox(key="etat").set_value(EtatProjet.SANS_AUDIT).run()
    at.number_input(key="travaux_ht").set_value(800_000).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Coût de l'opération TTC" in labels and "Reste à charge net" in labels
    assert any("participation minimale de 20 %" in e.value for e in at.error)


def test_rechargement_du_package_apres_mise_a_jour():
    """Après une mise à jour du dépôt, un package resté en mémoire avec l'ancien code est rechargé."""
    import sys

    import renovation_gantt

    # Les modules d'origine sont remis en place ensuite, pour ne pas mélanger les classes dans les autres tests.
    originaux = {n: m for n, m in sys.modules.items() if n.split(".")[0] == "renovation_gantt"}
    empreinte = renovation_gantt._empreinte
    try:
        renovation_gantt._empreinte = "ancienne-version"
        at = AppTest.from_file(APP, default_timeout=30).run()
        assert not at.exception
        assert sys.modules["renovation_gantt"] is not renovation_gantt
        assert sys.modules["renovation_gantt"]._empreinte == renovation_gantt.empreinte_sources()
    finally:
        renovation_gantt._empreinte = empreinte
        for nom in [n for n in sys.modules if n.split(".")[0] == "renovation_gantt"]:
            del sys.modules[nom]
        sys.modules.update(originaux)


def test_forfaits_suivent_l_etat_du_projet_sauf_saisie():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="etat").set_value(EtatProjet.SANS_AUDIT).run()
    assert at.number_input(key="poste_ETUDES").value == 15_000
    assert at.number_input(key="poste_AMO").value == 0
    at.selectbox(key="etat").set_value(EtatProjet.AUDIT_RECU).run()
    assert at.number_input(key="poste_AMO").value == 20_000  # l'AMO entre au planning
    at.number_input(key="poste_AMO").set_value(35_000).run()
    at.selectbox(key="etat").set_value(EtatProjet.MOE_SELECTIONNEE).run()
    assert at.number_input(key="poste_ETUDES").value == 0  # plus d'études préalables au planning
    assert at.number_input(key="poste_AMO").value == 35_000  # saisie conservée


def test_region_departement_et_financeurs():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="region").set_value("Pays de la Loire").run()
    at.selectbox(key="departement").set_value("44").run()
    at.selectbox(key="etat").set_value(EtatProjet.MOE_SELECTIONNEE).run()
    assert not at.exception
    noms = [f.nom for f in at.session_state["financeurs"]]
    assert "Région : Pays de la Loire" in noms
    assert "Département : Loire-Atlantique (44)" in noms


def test_informations_rgpd_et_mentions_legales():
    from renovation_gantt.mentions import CONTACT, EDITEUR

    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.checkbox(key="memoriser").value is False  # consentement non présumé
    textes = " ".join(e.value for e in at.markdown) + " ".join(e.body for e in at.info)
    assert "Vos données restent chez vous" in textes
    assert EDITEUR in textes and CONTACT in textes
