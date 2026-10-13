import io
from datetime import date

import pandas as pd
import pytest

from renovation_gantt.export import Scenario, planning_vers_csv, planning_vers_excel
from renovation_gantt.phases import EtatProjet
from renovation_gantt.planning import calculer_planning


@pytest.fixture
def scenario():
    return Scenario(
        EtatProjet.AUDIT_RECU,
        date(2026, 2, 2),
        financement_semaines=8,
        durees={"APD": 10, "PRO": 1},
        delais_mo={"APS": 0},
    )


def test_scenario_aller_retour_json(scenario):
    recharge = Scenario.depuis_json(scenario.vers_json())
    assert recharge == scenario


def test_scenario_applique_durees_et_minimums(scenario):
    phases = {p.id: p for p in scenario.phases()}
    assert phases["APD"].duree == 10
    assert phases["PRO"].duree == 4  # minimum réglementaire
    assert phases["APS"].delai_mo == 0
    assert phases["DECISION_ELUS"].duree == 0  # non modifiable


@pytest.mark.parametrize(
    "contenu", ["pas du json", "{}", '{"version": 99}', '{"version": 1, "etat": "INCONNU", "date_debut": "2026-01-01"}']
)
def test_scenario_invalide(contenu):
    with pytest.raises(ValueError, match="Fichier de scénario invalide"):
        Scenario.depuis_json(contenu)


def test_export_excel(scenario):
    planning = calculer_planning(scenario.phases(), scenario.date_debut, scenario.financement_semaines)
    classeur = pd.read_excel(io.BytesIO(planning_vers_excel(planning)), sheet_name=None)
    assert list(classeur) == ["Résumé", "Planning", "Jalons"]
    assert len(classeur["Planning"]) == len(planning.taches)
    assert "Durée (semaines)" in classeur["Planning"].columns


def test_export_csv(scenario):
    planning = calculer_planning(scenario.phases(), scenario.date_debut)
    texte = planning_vers_csv(planning).decode("utf-8-sig")
    assert texte.splitlines()[0].startswith("Tâche;Début;Fin")
    assert len(texte.splitlines()) == len(planning.taches) + 1


def test_scenario_complet_aller_retour():
    from renovation_gantt.phases import Autorisation, TypeAutorisation

    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE,
        date(2026, 2, 2),
        None,
        autorisation=Autorisation(TypeAutorisation.PC_ERP, abf=True, purge_recours=True),
        treve_semaines=3,
    )
    assert Scenario.depuis_json(sc.vers_json()) == sc


def test_ancien_scenario_sans_autorisation_ni_treve():
    ancien = '{"version": 1, "etat": "SANS_AUDIT", "date_debut": "2026-01-05", "financement_semaines": 6}'
    sc = Scenario.depuis_json(ancien)
    assert sc.autorisation.type.name == "DP"
    assert sc.treve_semaines == 2


def test_export_pdf(scenario):
    from renovation_gantt.pdf import planning_vers_pdf

    contenu = planning_vers_pdf(scenario.planning(), scenario.etat, edition=date(2026, 2, 2))
    assert contenu.startswith(b"%PDF")
    assert contenu.count(b"/Type /Page\n") >= 2 or contenu.count(b"/Type /Page") >= 2


def test_texte_sans_emoji():
    from renovation_gantt.pdf import texte_sans_emoji

    assert texte_sans_emoji("👷‍♂️👷‍♀️ AOR - Réception") == "AOR - Réception"
    assert texte_sans_emoji("🏛️ Instruction PC (3 mois)") == "Instruction PC (3 mois)"
