from datetime import date, timedelta

from renovation_gantt.export import Scenario
from renovation_gantt.phases import Autorisation, EtatProjet, Groupe, Phase, TypeAutorisation, phases_pour_etat
from renovation_gantt.planning import TYPE_ATTENTE, TYPE_GPA, TYPE_PHASE, calculer_planning

DEBUT = date(2026, 3, 2)


def _par_id(planning):
    return planning.taches[planning.taches["Type"] == TYPE_PHASE].set_index("Id")


def test_phase_parallele_ne_retarde_pas_la_suite():
    phases = [
        Phase("P", "Parallèle", Groupe.MOE, 8, parallele=True),
        Phase("A", "A", Groupe.MOE, 2),
        Phase("B", "B", Groupe.MOE, 2),
    ]
    t = _par_id(calculer_planning(phases, DEBUT))
    assert t.loc["P", "Debut"] == t.loc["A", "Debut"] == DEBUT
    assert t.loc["B", "Debut"] == DEBUT + timedelta(weeks=2)


def test_prerequis_cree_une_attente_visible():
    phases = [
        Phase("P", "Parallèle", Groupe.MOE, 8, parallele=True),
        Phase("A", "A", Groupe.MOE, 2),
        Phase("B", "B", Groupe.MOE, 2, prerequis=("P",)),
    ]
    p = calculer_planning(phases, DEBUT)
    t = _par_id(p)
    assert t.loc["B", "Debut"] == DEBUT + timedelta(weeks=8)
    attente = p.taches[p.taches["Type"] == TYPE_ATTENTE].iloc[0]
    assert (attente["Debut"], attente["Fin"]) == (DEBUT + timedelta(weeks=2), DEBUT + timedelta(weeks=8))
    assert p.attente_totale_jours == 42


def test_la_signature_des_marches_attend_le_dossier_de_financement():
    phases = [
        Phase("A", "A", Groupe.MOE, 2),
        Phase("ACT", "ACT", Groupe.MOE, 2, delai_mo=1, prerequis_signature=("FINANCEMENT",)),
    ]
    p = calculer_planning(phases, DEBUT, financement_semaines=12, financement_apres="A")
    # Le financement démarre après A (semaine 2) et dure 12 semaines : la signature attend la semaine 14.
    attente = p.taches[p.taches["Type"] == TYPE_ATTENTE].iloc[0]
    assert attente["Fin"] == DEBUT + timedelta(weeks=14)
    assert p.date_fin == DEBUT + timedelta(weeks=15)
    assert p.attentes[0].motif == "dossier de financement complet"


def test_financement_apres_l_apd_par_defaut():
    sc = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, financement_semaines=12)
    p = sc.planning()
    fin_apd = next(j.date for j in p.jalons if j.nom == "APD validé")
    fin = p.taches[p.taches["Id"] == "FINANCEMENT"].iloc[0]
    assert fin["Debut"] == fin_apd


def test_financement_tres_long_retarde_la_signature():
    court = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, financement_semaines=12).planning()
    long = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, financement_semaines=60).planning()
    assert not any(a.motif == "dossier de financement complet" for a in court.attentes)
    assert any(a.motif == "dossier de financement complet" for a in long.attentes)
    assert long.date_fin > court.date_fin


def test_le_dossier_d_autorisation_attend_le_ct_et_le_csps():
    phases = phases_pour_etat(EtatProjet.MOE_SELECTIONNEE)
    phases = [p.avec(duree=1) if p.id in ("DIAG", "APS", "APD") else p for p in phases]
    phases = [p.avec(delai_mo=0) for p in phases]
    p = calculer_planning(phases, DEBUT, autorisation=Autorisation(TypeAutorisation.DP))
    t = _par_id(p)
    assert t.loc["AUTORISATIONS", "Debut"] >= t.loc["CT_CSPS", "Fin"]
    assert any(a.motif == "recrutement du CT et du CSPS" for a in p.attentes)


def test_gpa_un_an_apres_la_reception_hors_duree_du_projet():
    p = calculer_planning(phases_pour_etat(EtatProjet.MOE_SELECTIONNEE), DEBUT)
    gpa = p.taches[p.taches["Type"] == TYPE_GPA].iloc[0]
    reception = next(j.date for j in p.jalons if j.nom == "Réception des travaux")
    assert gpa["Debut"] == reception
    assert gpa["Fin"] == date(reception.year + 1, reception.month, reception.day)
    assert p.date_fin < gpa["Fin"] == p.date_fin_affichage
    assert TYPE_GPA not in set(
        calculer_planning(phases_pour_etat(EtatProjet.MOE_SELECTIONNEE), DEBUT, gpa=False).taches["Type"]
    )


def test_nouvelles_durees_par_defaut():
    phases = {p.id: p for p in phases_pour_etat(EtatProjet.SANS_AUDIT)}
    assert phases["DET"].duree == 24
    assert (phases["ACT"].duree, phases["ACT"].delai_mo) == (10, 2)
    assert phases["VISA"].duree == 6
    assert phases["SIGNATURE_MOE"].duree == 3
    assert phases["DIAG"].duree == 6
    assert phases["APD"].delai_mo == 5
