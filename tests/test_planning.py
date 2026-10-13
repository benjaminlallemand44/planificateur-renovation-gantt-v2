from datetime import date, timedelta

import pytest

from renovation_gantt.phases import EtatProjet, Groupe, Phase, phases_pour_etat
from renovation_gantt.planning import TYPE_DELAI_MO, TYPE_FINANCEMENT, TYPE_PHASE, calculer_planning

DEBUT = date(2026, 1, 5)


def test_enchainement_et_delais_mo():
    phases = [
        Phase("A", "A", Groupe.MOE, 2, delai_mo=1),
        Phase("B", "B", Groupe.MOE, 3),
    ]
    p = calculer_planning(phases, DEBUT)
    t = p.taches
    assert list(t["Type"]) == [TYPE_PHASE, TYPE_DELAI_MO, TYPE_PHASE]
    assert t.iloc[0]["Fin"] == DEBUT + timedelta(weeks=2)
    assert t.iloc[1]["Fin"] == DEBUT + timedelta(weeks=3)
    assert t.iloc[2]["Debut"] == DEBUT + timedelta(weeks=3)
    assert p.date_fin == DEBUT + timedelta(weeks=6)
    assert p.duree_totale_semaines == 6
    assert p.semaines_delai_mo() == 1


def test_phase_masquee_ignoree():
    p = calculer_planning(phases_pour_etat(EtatProjet.MOE_SELECTIONNEE), DEBUT)
    assert "ESQ" not in set(p.taches["Id"])


def test_phase_de_duree_nulle_garde_son_delai():
    phases = [Phase("D", "Décision", Groupe.ETUDES, 0, delai_mo=6, duree_min=0, modifiable=False)]
    t = calculer_planning(phases, DEBUT).taches
    assert list(t["Type"]) == [TYPE_DELAI_MO]
    assert t.iloc[0]["Semaines"] == 6


def test_les_definitions_sont_renseignees_au_survol():
    t = calculer_planning(phases_pour_etat(EtatProjet.MOE_SELECTIONNEE), DEBUT).taches
    phases_mop = t[(t["Type"] == TYPE_PHASE)]
    assert (phases_mop["Definition"] != "").all()


def test_financement_en_parallele():
    phases = phases_pour_etat(EtatProjet.SANS_AUDIT)
    sans = calculer_planning(phases, DEBUT)
    avec = calculer_planning(phases, DEBUT, financement_semaines=6)
    fin = avec.taches[avec.taches["Type"] == TYPE_FINANCEMENT].iloc[0]
    assert fin["Debut"] == DEBUT and fin["Fin"] == DEBUT + timedelta(weeks=6)
    assert sans.date_fin == avec.date_fin


def test_financement_plus_long_que_le_projet_repousse_la_fin():
    phases = [Phase("A", "A", Groupe.MOE, 2)]
    p = calculer_planning(phases, DEBUT, financement_semaines=10)
    assert p.date_fin == DEBUT + timedelta(weeks=10)


def test_jalons():
    p = calculer_planning(phases_pour_etat(EtatProjet.SANS_AUDIT), DEBUT)
    noms = [j.nom for j in p.jalons]
    assert noms[-1] == "Fin de la GPA"
    assert "Fin du projet" in noms
    assert "MOE recrutée" in noms and "Réception des travaux" in noms
    dates = [j.date for j in p.jalons]
    assert dates == sorted(dates)
    assert next(j for j in p.jalons if j.nom == "Fin du projet").date == p.date_fin


@pytest.mark.parametrize("etat", list(EtatProjet))
def test_tous_les_groupes_ont_des_semaines(etat):
    p = calculer_planning(phases_pour_etat(etat), DEBUT)
    groupes = {ph.groupe.value for ph in phases_pour_etat(etat)}
    assert set(p.semaines_par_groupe()) == groupes


def test_planning_vide():
    p = calculer_planning([], DEBUT)
    assert p.taches.empty
    assert p.date_fin == DEBUT
