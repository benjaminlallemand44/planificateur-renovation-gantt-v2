from datetime import date

import pytest

from renovation_gantt.charts import figure_gantt
from renovation_gantt.phases import EtatProjet, phases_pour_etat
from renovation_gantt.planning import calculer_planning

DEBUT = date(2026, 1, 5)


@pytest.mark.parametrize("etat", list(EtatProjet))
def test_figure_pour_chaque_etat(etat):
    planning = calculer_planning(phases_pour_etat(etat), DEBUT, financement_semaines=6)
    fig = figure_gantt(planning)
    textes = {a.text for a in fig.layout.annotations}
    for groupe in {p.groupe.value for p in phases_pour_etat(etat)}:
        assert f"<b>{groupe}</b>" in textes
    assert "◆ Fin du projet" in textes


def test_bandeau_amo_present():
    fig = figure_gantt(calculer_planning(phases_pour_etat(EtatProjet.AMO_PROGRAMMISTE), DEBUT))
    assert "<b>AMO Programmiste</b>" in {a.text for a in fig.layout.annotations}


def test_ligne_aujourd_hui():
    planning = calculer_planning(phases_pour_etat(EtatProjet.SANS_AUDIT), DEBUT)
    textes = {a.text for a in figure_gantt(planning, aujourd_hui=date(2026, 3, 1)).layout.annotations}
    assert "Aujourd'hui" in textes
    textes = {a.text for a in figure_gantt(planning, aujourd_hui=date(2020, 1, 1)).layout.annotations}
    assert "Aujourd'hui" not in textes


def test_planning_vide_leve_une_erreur():
    with pytest.raises(ValueError):
        figure_gantt(calculer_planning([], DEBUT))
