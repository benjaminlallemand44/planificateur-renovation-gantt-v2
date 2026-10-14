import io
from datetime import date

import pandas as pd
import pytest

from renovation_gantt.budget import (
    Budget,
    Financeur,
    RegimeFCTVA,
    StatutAide,
    _repartir,
    budget_vers_excel,
    postes_par_defaut,
)
from renovation_gantt.export import Scenario
from renovation_gantt.phases import EtatProjet

DEBUT = date(2026, 10, 14)


def _budget(**kw):
    return Budget(travaux_ht=1_000_000, postes={"ETUDES": 0, "AMO": 0}, **kw)


def test_cout_de_l_operation():
    b = _budget()
    couts = b.couts().set_index("Id")
    assert couts.loc["TRAVAUX", "TTC"] == 1_200_000
    assert couts.loc["MOE", "HT"] == 110_000  # 11 % par défaut
    assert couts.loc["DO", "TVA"] == 0  # assurance sans TVA
    assert b.total_ht == pytest.approx(1_000_000 * (1 + (11 + 1 + 0.8 + 1.2 + 1 + 7 + 3) / 100))
    assert b.total_ttc == pytest.approx(b.total_ht + b.total_tva)


def test_postes_par_defaut_selon_les_phases():
    assert postes_par_defaut({"DIAG"})["ETUDES"] == 0
    assert postes_par_defaut({"DIAG"})["AMO"] == 0
    assert postes_par_defaut({"AUDIT", "AMO_MISSION"})["ETUDES"] > 0
    assert postes_par_defaut({"AUDIT", "AMO_MISSION"})["AMO"] > 0


def test_aides_taux_montant_public_prive():
    b = _budget(
        financeurs=[
            Financeur("DETR", taux=30),
            Financeur("Région", taux=50, montant=100_000),  # le montant prime sur le taux
            Financeur("CEE", montant=40_000, public=False),
        ]
    )
    assert b.aides_publiques == pytest.approx(0.30 * b.total_ht + 100_000)
    assert b.aides_privees == 40_000
    assert not b.depasse_plafond
    assert b.reste_a_charge == pytest.approx(b.total_ttc - b.aides - b.fctva)


def test_plafond_de_80_pour_cent_d_aides_publiques():
    assert _budget(financeurs=[Financeur("A", 50), Financeur("B", 31)]).depasse_plafond
    assert not _budget(financeurs=[Financeur("A", 50), Financeur("B", 30)]).depasse_plafond
    # Les aides privées (CEE) ne comptent pas dans le plafond.
    assert not _budget(financeurs=[Financeur("A", 80), Financeur("CEE", 15, public=False)]).depasse_plafond


def test_fctva_hors_assurance():
    b = _budget()
    couts = b.couts()
    eligible = couts.loc[couts["Id"] != "DO", "TTC"].sum()
    assert b.fctva == pytest.approx(eligible * 0.16404)


def test_repartir_au_prorata_des_jours():
    parts = _repartir(1000, [(date(2026, 11, 1), date(2027, 3, 1), 1.0)])
    assert parts[2026] == pytest.approx(1000 * 61 / 120)
    assert parts[2027] == pytest.approx(1000 * 59 / 120)
    assert _repartir(500, [(date(2027, 5, 1), date(2027, 5, 1), 1.0)]) == {2027: 500}


@pytest.mark.parametrize("etat", list(EtatProjet))
def test_echeancier_coherent(etat):
    sc = Scenario(etat, DEBUT, 12)
    planning = sc.planning()
    b = Budget(travaux_ht=600_000, financeurs=[Financeur("DETR", 30), Financeur("CEE", montant=20_000, public=False)])
    e = b.echeancier(planning)
    assert e["Dépenses TTC"].sum() == pytest.approx(b.total_ttc, abs=1)
    assert e["Aides"].sum() == pytest.approx(b.aides, abs=1)
    assert e["FCTVA"].sum() == pytest.approx(b.fctva, abs=1)
    assert e["Cumul"].iloc[-1] == pytest.approx(-b.reste_a_charge, abs=2)
    assert list(e["Année"]) == list(range(e["Année"].min(), e["Année"].max() + 1))


def test_regime_fctva_decale_la_recette():
    planning = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12).planning()
    n = Budget(travaux_ht=500_000, regime_fctva=RegimeFCTVA.N).echeancier(planning)
    n2 = Budget(travaux_ht=500_000, regime_fctva=RegimeFCTVA.N2).echeancier(planning)
    premiere = lambda e: int(e.loc[e["FCTVA"] > 0, "Année"].min())  # noqa: E731
    assert premiere(n2) == premiere(n) + 2


def test_scenario_avec_budget_aller_retour():
    b = Budget(
        travaux_ht=750_000,
        postes={"MOE": 12.5},
        financeurs=[Financeur("DSIL", 25, statut=StatutAide.DEPOSEE), Financeur("CEE", 0, 30_000, False)],
        regime_fctva=RegimeFCTVA.N2,
        acompte_aides=20,
    )
    sc = Scenario(EtatProjet.SANS_AUDIT, DEBUT, 12, budget=b)
    assert Scenario.depuis_json(sc.vers_json()) == sc
    ancien = '{"version": 1, "etat": "SANS_AUDIT", "date_debut": "2026-01-05"}'
    assert Scenario.depuis_json(ancien).budget == Budget()


def test_export_excel_budget():
    planning = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12).planning()
    contenu = budget_vers_excel(Budget(travaux_ht=400_000, financeurs=[Financeur("DETR", 30)]), planning)
    feuilles = pd.read_excel(io.BytesIO(contenu), sheet_name=None)
    assert list(feuilles) == ["Synthèse", "Coût de l'opération", "Plan de financement", "Échéancier"]
