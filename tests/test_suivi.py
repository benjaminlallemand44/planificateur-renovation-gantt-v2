from datetime import date, timedelta

import pytest

from renovation_gantt.avancement import Avancement, Statut
from renovation_gantt.export import Scenario
from renovation_gantt.pdf import point_avancement_pdf
from renovation_gantt.phases import Autorisation, EtatProjet, Groupe, Phase, TypeAutorisation
from renovation_gantt.planning import TYPE_PHASE, TYPE_REALISE, calculer_planning
from renovation_gantt.suivi import (
    Reference,
    comparer,
    ecart_fin_jours,
    elements_suivis,
    etendues,
    meteo,
    points_attention,
)

DEBUT = date(2026, 1, 5)
AUJOURD_HUI = date(2026, 4, 6)
PHASES = [Phase("A", "A", Groupe.MOE, 4, delai_mo=1), Phase("B", "B", Groupe.MOE, 4), Phase("C", "C", Groupe.MOE, 4)]


def _plan(avancement=None, aujourd_hui=AUJOURD_HUI, phases=PHASES, **kw):
    return calculer_planning(phases, DEBUT, avancement=avancement, aujourd_hui=aujourd_hui, **kw)


def test_une_phase_terminee_en_retard_decale_la_suite():
    av = {"A": Avancement(Statut.TERMINEE, DEBUT, date(2026, 2, 23))}
    p = _plan(av)
    t = p.taches.set_index("Id")
    assert t.loc["A", "Type"] == TYPE_REALISE
    assert (t.loc["A", "Debut"], t.loc["A", "Fin"]) == (DEBUT, date(2026, 2, 23))
    # B est à venir : elle ne démarre pas dans le passé.
    assert t.loc["B", "Debut"] == AUJOURD_HUI


def test_phase_en_cours_avec_nouvelle_fin_prevue():
    av = {
        "A": Avancement(Statut.TERMINEE, DEBUT, date(2026, 2, 9)),
        "B": Avancement(Statut.EN_COURS, date(2026, 2, 9), date(2026, 5, 4)),
    }
    t = _plan(av).taches.set_index("Id")
    assert t.loc["B", "Type"] == TYPE_PHASE
    assert t.loc["B", "Fin"] == date(2026, 5, 4)
    assert t.loc["C", "Debut"] == date(2026, 5, 4)


def test_phase_en_cours_qui_depasse_sa_duree():
    av = {"A": Avancement(Statut.EN_COURS, DEBUT)}  # 5 semaines prévues, nous sommes 13 semaines après
    p = _plan(av)
    assert p.taches.set_index("Id").loc["A", "Fin"] == AUJOURD_HUI
    assert p.depassements == ["A"]
    assert any("dépasse sa date de fin prévue" in m for m in points_attention(p, None, AUJOURD_HUI))


def test_sans_avancement_la_date_du_jour_est_ignoree_par_le_scenario():
    sc = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12)
    assert sc.planning(aujourd_hui=date(2030, 1, 1)).date_fin == sc.planning().date_fin


def test_financement_et_instruction_suivis():
    phases = [
        Phase("APD", "APD", Groupe.MOE, 2),
        Phase("AUTORISATIONS", "Dossier", Groupe.MOE, 1, debut_instruction=True),
        Phase("ACT", "ACT", Groupe.MOE, 2, prerequis_signature=("FINANCEMENT",)),
        Phase("DET", "DET", Groupe.MOE, 4, prerequis=("AUTORISATION",)),
    ]
    av = {
        "APD": Avancement(Statut.TERMINEE, DEBUT, date(2026, 1, 19)),
        "FINANCEMENT": Avancement(Statut.TERMINEE, date(2026, 1, 19), date(2026, 3, 2)),
        "INSTRUCTION": Avancement(Statut.EN_COURS, date(2026, 1, 26), date(2026, 6, 1)),
    }
    p = calculer_planning(
        phases,
        DEBUT,
        financement_semaines=12,
        financement_apres="APD",
        autorisation=Autorisation(TypeAutorisation.PC),
        avancement=av,
        aujourd_hui=AUJOURD_HUI,
    )
    t = p.taches.set_index("Id")
    assert t.loc["FINANCEMENT", "Fin"] == date(2026, 3, 2)
    assert t.loc["FINANCEMENT", "Type"] == TYPE_REALISE
    assert t.loc["INSTRUCTION", "Fin"] == date(2026, 6, 1)
    assert t.loc["DET", "Debut"] == date(2026, 6, 1)


def test_reference_et_ecarts():
    prevu = _plan(aujourd_hui=None)
    ref = Reference.depuis_planning(prevu, "Délibération", DEBUT)
    av = {"A": Avancement(Statut.TERMINEE, DEBUT, date(2026, 3, 16))}  # 5 semaines de retard
    actuel = _plan(av)
    assert ecart_fin_jours(actuel, ref) > 0
    tableau = comparer(actuel, ref).set_index("Id")
    assert tableau.loc["A", "Écart (sem.)"] == 5
    assert tableau.loc["A", "Statut"] == "Terminée"
    messages = points_attention(actuel, ref, AUJOURD_HUI)
    assert any("plus tard que la référence" in m for m in messages)


def test_reference_aller_retour():
    ref = Reference.depuis_planning(_plan(aujourd_hui=None), "APD validé", DEBUT)
    assert Reference.depuis_dict(ref.vers_dict()) == ref


@pytest.mark.parametrize(
    ("ecart", "niveau"),
    [(None, "gris"), (-30, "vert"), (0, "vert"), (14, "vert"), (21, "orange"), (56, "orange"), (90, "rouge")],
)
def test_meteo(ecart, niveau):
    assert meteo(ecart)[0] == niveau


def test_elements_suivis_exclut_attentes_gpa_et_recours():
    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE, DEBUT, 12, autorisation=Autorisation(TypeAutorisation.PC_ERP, purge_recours=True)
    )
    ids = [i for i, _ in elements_suivis(sc.planning())]
    assert "INSTRUCTION" in ids and "FINANCEMENT" in ids
    assert not {"GPA", "RECOURS"} & set(ids)
    assert not any(i.startswith("ATTENTE") for i in ids)


def test_scenario_avec_suivi_aller_retour():
    prevu = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12, nom_projet="École Jules Ferry")
    ref = Reference.depuis_planning(prevu.planning(), "Délibération", DEBUT)
    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE,
        DEBUT,
        12,
        nom_projet="École Jules Ferry",
        avancement={"DIAG": Avancement(Statut.EN_COURS, DEBUT + timedelta(weeks=1), None, "Relevés en cours")},
        references=[ref],
    )
    assert Scenario.depuis_json(sc.vers_json()) == sc


def test_point_avancement_pdf():
    prevu = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12)
    ref = Reference.depuis_planning(prevu.planning(), "Délibération", DEBUT)
    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE,
        DEBUT,
        12,
        avancement={"CT_CSPS": Avancement(Statut.TERMINEE, DEBUT, date(2026, 4, 1))},
    )
    contenu = point_avancement_pdf(sc.planning(AUJOURD_HUI), ref, AUJOURD_HUI, "École Jules Ferry")
    assert contenu.startswith(b"%PDF")
    assert etendues(sc.planning(AUJOURD_HUI))


def test_une_phase_terminee_sans_date_ne_finit_pas_dans_le_futur():
    av = {"A": Avancement(Statut.TERMINEE)}
    t = _plan(av, aujourd_hui=DEBUT + timedelta(weeks=2)).taches.set_index("Id")
    assert t.loc["A", "Fin"] == DEBUT + timedelta(weeks=2)
    assert t.loc["B", "Debut"] == DEBUT + timedelta(weeks=2)
