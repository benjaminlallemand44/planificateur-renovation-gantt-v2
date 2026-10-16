from datetime import date

from renovation_gantt.territoires import DEPARTEMENTS, REGIONS, CalendrierEte, departements_de


def test_tous_les_departements():
    assert len(DEPARTEMENTS) == 101
    assert len(REGIONS) == 18
    assert {d.zone for d in DEPARTEMENTS.values()} == {"A", "B", "C", "Corse", "Outre-mer"}


def test_zones_de_quelques_departements():
    assert DEPARTEMENTS["44"].zone == "B"  # Nantes
    assert DEPARTEMENTS["69"].zone == "A"  # Lyon
    assert DEPARTEMENTS["75"].zone == "C"  # Paris
    assert DEPARTEMENTS["2A"].calendrier_specifique
    assert DEPARTEMENTS["974"].calendrier_specifique
    assert not DEPARTEMENTS["33"].calendrier_specifique


def test_departements_d_une_region():
    assert [d.code for d in departements_de("Pays de la Loire")] == ["44", "49", "53", "72", "85"]


def test_calendrier_national():
    cal = CalendrierEte()
    assert cal.vacances(2026) == (date(2026, 7, 4), date(2026, 9, 1))
    assert cal.vacances(2027) == (date(2027, 7, 3), date(2027, 9, 2))
    assert cal.en_vacances(date(2027, 9, 1)) and not cal.en_vacances(date(2027, 9, 2))
    debut, rentree = cal.vacances(2035)  # année non publiée : dates habituelles
    assert (debut.month, rentree.month) == (7, 9)


def test_calendrier_personnalise_ete_austral():
    # Grandes vacances de décembre à janvier (La Réunion, Mayotte) : dates à saisir par l'utilisateur.
    cal = CalendrierEte(personnalise=((12, 19), (1, 26)))
    assert cal.vacances(2026) == (date(2026, 12, 19), date(2027, 1, 26))
    assert cal.en_vacances(date(2027, 1, 10))
    assert cal.prochain_demarrage(date(2027, 3, 1), 14) == date(2027, 12, 19)
