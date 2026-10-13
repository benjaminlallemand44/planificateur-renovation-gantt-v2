from datetime import date

import pytest

from renovation_gantt.export import Scenario, planning_vers_ics
from renovation_gantt.phases import EtatProjet, FenetreTravaux
from renovation_gantt.planning import TYPE_PHASE, prochain_ete

DEBUT = date(2026, 10, 13)


@pytest.mark.parametrize(
    ("jour", "attendu"),
    [
        (date(2027, 3, 1), date(2027, 7, 6)),
        (date(2027, 7, 20), date(2027, 7, 20)),  # encore plus de deux semaines de vacances
        (date(2027, 8, 25), date(2028, 7, 6)),  # trop tard : été suivant
        (date(2027, 10, 1), date(2028, 7, 6)),
    ],
)
def test_prochain_ete(jour, attendu):
    assert prochain_ete(jour) == attendu


def _travaux(planning):
    t = planning.taches
    return t[(t["Id"] == "DET") & (t["Type"] == TYPE_PHASE)]


def test_les_travaux_demarrent_a_l_ete():
    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE, DEBUT, 12, batiment_scolaire=True, fenetre_travaux=FenetreTravaux.DEBUT_ETE
    )
    p = sc.planning()
    travaux = _travaux(p)
    assert len(travaux) == 1
    debut = travaux.iloc[0]["Debut"]
    assert (debut.month, debut.day) == (7, 6)
    assert any(a.motif == "début des vacances d'été" for a in p.attentes)
    assert p.gain_pour_ete_precedent_jours > 0


def test_travaux_uniquement_l_ete_sur_plusieurs_etes():
    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE, DEBUT, 12, batiment_scolaire=True, fenetre_travaux=FenetreTravaux.ETE_UNIQUEMENT
    )
    travaux = _travaux(sc.planning())
    assert len(travaux) == 3  # 24 semaines à raison d'environ 8 semaines par été
    for t in travaux.itertuples():
        assert t.Debut.month in (7, 8) and t.Fin <= date(t.Debut.year, 9, 1)
    assert travaux["Semaines"].sum() == pytest.approx(24)


def test_sans_batiment_scolaire_la_fenetre_est_ignoree():
    sc = Scenario(
        EtatProjet.MOE_SELECTIONNEE, DEBUT, 12, batiment_scolaire=False, fenetre_travaux=FenetreTravaux.DEBUT_ETE
    )
    assert sc.planning().date_fin == Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12).planning().date_fin


def test_scenario_scolaire_aller_retour():
    sc = Scenario(
        EtatProjet.SANS_AUDIT, DEBUT, 12, batiment_scolaire=True, fenetre_travaux=FenetreTravaux.ETE_UNIQUEMENT
    )
    assert Scenario.depuis_json(sc.vers_json()) == sc


def test_export_ics():
    p = Scenario(EtatProjet.MOE_SELECTIONNEE, DEBUT, 12).planning()
    texte = planning_vers_ics(p, "École Jules Ferry").decode()
    assert texte.startswith("BEGIN:VCALENDAR\r\n") and texte.endswith("END:VCALENDAR\r\n")
    assert texte.count("BEGIN:VEVENT") == len(p.jalons)
    fin = next(j.date for j in p.jalons if j.nom == "Fin du projet")
    assert f"DTSTART;VALUE=DATE:{fin:%Y%m%d}" in texte
    assert "SUMMARY:École Jules Ferry – Fin du projet" in texte
