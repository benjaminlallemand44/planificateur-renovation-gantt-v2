from datetime import date

import pytest

from renovation_gantt.charts import figure_gantt, libelle_compact
from renovation_gantt.phases import EtatProjet, phases_pour_etat
from renovation_gantt.planning import calculer_planning

DEBUT = date(2026, 1, 5)


@pytest.mark.parametrize("etat", list(EtatProjet))
def test_figure_pour_chaque_etat(etat):
    planning = calculer_planning(phases_pour_etat(etat), DEBUT, financement_semaines=6)
    fig = figure_gantt(planning)
    bandeaux = {a.hovertext for a in fig.layout.annotations}
    for groupe in {p.groupe.value for p in phases_pour_etat(etat)}:
        assert groupe in bandeaux
    assert "◆ Fin du projet" in {a.text for a in fig.layout.annotations}


def test_bandeau_amo_present():
    fig = figure_gantt(calculer_planning(phases_pour_etat(EtatProjet.AMO_PROGRAMMISTE), DEBUT))
    assert "AMO Programmiste" in {a.hovertext for a in fig.layout.annotations}


def test_libelle_bandeau_abrege_si_etroit():
    from renovation_gantt.charts import libelle_bandeau
    from renovation_gantt.phases import Groupe

    assert libelle_bandeau(Groupe.SELECTION_MOE, 0.5) == "Sélection MOE"
    assert libelle_bandeau(Groupe.SELECTION_MOE, 0.07) == "Sél. MOE"
    assert libelle_bandeau(Groupe.SELECTION_MOE, 0.01) == ""


def test_ligne_aujourd_hui():
    planning = calculer_planning(phases_pour_etat(EtatProjet.SANS_AUDIT), DEBUT)
    textes = {a.text for a in figure_gantt(planning, aujourd_hui=date(2026, 3, 1)).layout.annotations}
    assert "Aujourd'hui" in textes
    textes = {a.text for a in figure_gantt(planning, aujourd_hui=date(2020, 1, 1)).layout.annotations}
    assert "Aujourd'hui" not in textes


def test_planning_vide_leve_une_erreur():
    with pytest.raises(ValueError):
        figure_gantt(calculer_planning([], DEBUT))


def test_etiquettes_de_jalons_proches_alternent():
    from renovation_gantt.charts import etiquettes_a_droite
    from renovation_gantt.phases import Groupe, Phase

    phases = [Phase(c, c, Groupe.MOE, 1, jalon_fin=f"Jalon {c}") for c in "ABC"] + [
        Phase("D", "D", Groupe.MOE, 20, jalon_fin="Jalon D")
    ]
    planning = calculer_planning(phases, DEBUT)
    # A, B et C sont espacés d'une semaine : leurs étiquettes alternent ; D est isolé.
    assert etiquettes_a_droite(planning)[:4] == [False, True, False, False]


def test_bandes_de_treve():
    planning = calculer_planning(phases_pour_etat(EtatProjet.SANS_AUDIT), DEBUT, treve_semaines=2)
    fig = figure_gantt(planning)
    assert "Trêve de fin d'année" in {t.name for t in fig.data}


def test_gantt_compact_pour_smartphone():
    assert libelle_compact("📝 APD - Avant-Projet Définitif") == "📝 APD"
    assert len(libelle_compact("🦺 Recrutement du contrôleur technique et du CSPS")) <= 18
    planning = calculer_planning(phases_pour_etat(EtatProjet.MOE_SELECTIONNEE), DEBUT, financement_semaines=6)
    fig = figure_gantt(planning, compact=True)
    libelles = {y for trace in fig.data for y in (trace.y if trace.y is not None else []) if y}
    assert "📝 APD" in libelles
    # Jalons sans texte (détaillés dans le tableau) mais toujours tracés.
    assert not any("◆" in (a.text or "") for a in fig.layout.annotations)
    assert len(fig.layout.shapes) == len(figure_gantt(planning).layout.shapes)


def test_libelles_courts_des_etats():
    assert all(len(e.libelle_court) <= 40 for e in EtatProjet)
