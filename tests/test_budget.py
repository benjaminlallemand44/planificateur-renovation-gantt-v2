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


def _planning_moe():
    return Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12).planning()


def test_retenue_de_garantie_liberee_apres_la_gpa():
    planning = _planning_moe()
    sans = Budget(travaux_ht=1_000_000, retenue_garantie=0).echeancier(planning).set_index("Année")
    avec = Budget(travaux_ht=1_000_000, retenue_garantie=5).echeancier(planning).set_index("Année")
    reception = next(j.date for j in planning.jalons if j.nom == "Réception des travaux")
    annee_liberation = (reception.replace(year=reception.year + 1)).year
    assert avec["Dépenses TTC"].sum() == pytest.approx(sans["Dépenses TTC"].sum(), abs=1)
    assert avec.loc[annee_liberation, "Dépenses TTC"] > sans.loc[annee_liberation, "Dépenses TTC"]


def test_avance_aux_entreprises_versee_au_demarrage():
    # Date de départ choisie pour que les travaux soient à cheval sur deux années civiles.
    planning = next(
        p
        for mois in range(1, 13)
        if (p := Scenario(EtatProjet.MOE_SELECTIONNEE, date(2026, mois, 1), 12).planning())
        and len({d.year for d in p.taches.loc[p.taches["Id"] == "DET", ["Debut", "Fin"]].values.ravel()}) == 2
    )
    sans = Budget(travaux_ht=1_000_000, avance_entreprises=0, retenue_garantie=0).echeancier(planning)
    avec = Budget(travaux_ht=1_000_000, avance_entreprises=20, retenue_garantie=0).echeancier(planning)
    debut = planning.taches.loc[planning.taches["Id"] == "DET", "Debut"].min()
    s, a = sans.set_index("Année"), avec.set_index("Année")
    assert a.loc[debut.year, "Dépenses TTC"] > s.loc[debut.year, "Dépenses TTC"]
    assert a["Dépenses TTC"].sum() == pytest.approx(s["Dépenses TTC"].sum(), abs=1)


def test_aides_avance_acomptes_et_solde():
    planning = _planning_moe()
    b = Budget(travaux_ht=800_000, financeurs=[Financeur("DETR", 40)], acompte_aides=30, solde_aides=20)
    e = b.echeancier(planning)
    assert e["Aides"].sum() == pytest.approx(b.aides, abs=1)
    # Acomptes au fil des dépenses : des aides sont perçues au moins deux années différentes.
    assert (e["Aides"] > 0).sum() >= 2
    # Avance et solde à 100 % : plus d'acomptes intermédiaires.
    e2 = Budget(travaux_ht=800_000, financeurs=[Financeur("DETR", 40)], acompte_aides=60, solde_aides=60).echeancier(
        planning
    )
    assert e2["Aides"].sum() == pytest.approx(b.aides, abs=1)


def test_delai_de_paiement_decale_les_depenses():
    planning = _planning_moe()
    immediat = Budget(travaux_ht=500_000, delai_paiement_jours=0).echeancier(planning)
    a_30_jours = Budget(travaux_ht=500_000, delai_paiement_jours=30).echeancier(planning)
    assert immediat["Dépenses TTC"].sum() == pytest.approx(a_30_jours["Dépenses TTC"].sum(), abs=1)
    premiere = immediat["Année"].min()
    assert (
        a_30_jours.set_index("Année").loc[premiere, "Dépenses TTC"]
        < immediat.set_index("Année").loc[premiere, "Dépenses TTC"]
    )


def test_echeancier_sans_travaux():
    planning = Scenario(EtatProjet.SANS_AUDIT, DEBUT, 12).planning()
    b = Budget(travaux_ht=0, financeurs=[Financeur("ACTEE", montant=5_000)])
    e = b.echeancier(planning)
    assert e["Aides"].sum() == pytest.approx(5_000)
    assert e["Dépenses TTC"].sum() == pytest.approx(b.total_ttc, abs=1)


def test_pas_d_acompte_d_aide_avant_les_travaux():
    planning = Scenario(EtatProjet.SANS_AUDIT, DEBUT, 12).planning()
    debut_travaux = planning.taches.loc[planning.taches["Id"] == "DET", "Debut"].min()
    e = Budget(travaux_ht=600_000, financeurs=[Financeur("DETR", 30)]).echeancier(planning)
    assert (e.loc[e["Année"] < debut_travaux.year, "Aides"] == 0).all()
