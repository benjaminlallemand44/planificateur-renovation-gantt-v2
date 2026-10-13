from datetime import date, timedelta

import pytest

from renovation_gantt.phases import Autorisation, EtatProjet, Groupe, Phase, TypeAutorisation, phases_pour_etat
from renovation_gantt.planning import TYPE_INSTRUCTION, TYPE_PHASE, TYPE_RECOURS, calculer_planning, periodes_treve

# --------------------------------------------------------------------------
# Trêve de fin d'année


def test_une_phase_qui_traverse_la_treve_est_prolongee():
    phases = [Phase("A", "A", Groupe.MOE, 4)]
    # 4 semaines à partir du 1er décembre : 18 jours en décembre avant la trêve (19/12 → 01/01), puis 10 jours.
    t = calculer_planning(phases, date(2025, 12, 1), treve_semaines=2).taches.iloc[0]
    assert t["Fin"] == date(2026, 1, 12)
    assert t["Semaines"] == 4


def test_sans_treve_la_duree_est_inchangee():
    phases = [Phase("A", "A", Groupe.MOE, 4)]
    t = calculer_planning(phases, date(2025, 12, 1), treve_semaines=0).taches.iloc[0]
    assert t["Fin"] == date(2025, 12, 29)


def test_une_phase_ne_demarre_pas_pendant_la_treve():
    phases = [Phase("A", "A", Groupe.MOE, 1)]
    t = calculer_planning(phases, date(2025, 12, 24), treve_semaines=2).taches.iloc[0]
    assert t["Debut"] == date(2026, 1, 2)
    assert t["Fin"] == date(2026, 1, 9)


def test_periodes_treve():
    assert periodes_treve(date(2026, 1, 15), date(2027, 6, 1), 2) == [(date(2026, 12, 19), date(2027, 1, 2))]
    assert periodes_treve(date(2026, 1, 15), date(2027, 6, 1), 0) == []


# --------------------------------------------------------------------------
# Autorisation d'urbanisme


@pytest.mark.parametrize(
    ("type_", "abf", "mois"),
    [
        (TypeAutorisation.DP, False, 1),
        (TypeAutorisation.DP, True, 2),
        (TypeAutorisation.PC, False, 3),
        (TypeAutorisation.PC, True, 4),
        (TypeAutorisation.AT_ERP, False, 4),
        (TypeAutorisation.PC_ERP, False, 5),
        (TypeAutorisation.PC_ERP, True, 5),
        (TypeAutorisation.AUCUNE, True, 0),
    ],
)
def test_delais_d_instruction(type_, abf, mois):
    assert Autorisation(type_, abf=abf).mois_instruction == mois


def _planning(autorisation, **kw):
    return calculer_planning(phases_pour_etat(EtatProjet.MOE_SELECTIONNEE), date(2026, 3, 2), None, autorisation, **kw)


def test_instruction_en_parallele_des_etudes():
    p = _planning(Autorisation(TypeAutorisation.DP))
    t = p.taches.set_index(["Id", "Type"])
    depot = t.loc[("INSTRUCTION", TYPE_INSTRUCTION), "Debut"]
    assert t.loc[("INSTRUCTION", TYPE_INSTRUCTION), "Fin"] == date(depot.year, depot.month + 1, depot.day)
    # Le PRO démarre au dépôt, sans attendre la fin de l'instruction.
    assert t.loc[("PRO", TYPE_PHASE), "Debut"] == depot
    assert "Autorisation obtenue" in [j.nom for j in p.jalons]


def test_les_travaux_attendent_l_autorisation():
    p = _planning(Autorisation(TypeAutorisation.PC_ERP, purge_recours=True))
    t = p.taches.set_index(["Id", "Type"])
    purge = t.loc[("RECOURS", TYPE_RECOURS), "Fin"]
    assert t.loc[("VISA", TYPE_PHASE), "Debut"] == purge
    fin_act = max(t.loc["ACT"]["Fin"])
    assert p.attente_autorisation_jours == (purge - fin_act).days > 0


def test_pas_d_attente_quand_l_autorisation_arrive_a_temps():
    p = _planning(Autorisation(TypeAutorisation.DP))
    assert p.attente_autorisation_jours == 0


def test_sans_autorisation_pas_de_dossier_ni_d_instruction():
    p = _planning(Autorisation(TypeAutorisation.AUCUNE))
    ids = set(p.taches["Id"])
    assert "AUTORISATIONS" not in ids and "INSTRUCTION" not in ids
    assert _planning(Autorisation(TypeAutorisation.AUCUNE)).date_fin < _planning(None).date_fin


def test_les_delais_reglementaires_ignorent_la_treve():
    # Dépôt le 15/11 environ : l'instruction d'un PC (3 mois) traverse la trêve sans être prolongée.
    p = _planning(Autorisation(TypeAutorisation.PC), treve_semaines=2)
    instr = p.taches[p.taches["Id"] == "INSTRUCTION"].iloc[0]
    debut, fin = instr["Debut"], instr["Fin"]
    assert fin.day == debut.day and (fin.month - debut.month) % 12 == 3
    assert fin - debut < timedelta(days=95)
