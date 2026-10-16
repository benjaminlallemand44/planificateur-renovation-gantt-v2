"""Régions, départements, zones de vacances scolaires et dates des vacances d'été."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Departement:
    code: str
    nom: str
    region: str
    zone: str  # "A", "B", "C", "Corse" ou "Outre-mer"

    @property
    def libelle(self) -> str:
        return f"{self.code} – {self.nom}"

    @property
    def calendrier_specifique(self) -> bool:
        """Corse et outre-mer ont un calendrier scolaire propre, hors zonage A/B/C."""
        return self.zone in ("Corse", "Outre-mer")


# Zone de vacances par académie (A : Besançon, Bordeaux, Clermont-Ferrand, Dijon, Grenoble, Limoges, Lyon,
# Poitiers ; B : Aix-Marseille, Amiens, Lille, Nancy-Metz, Nantes, Nice, Normandie, Orléans-Tours, Reims,
# Rennes, Strasbourg ; C : Créteil, Montpellier, Paris, Toulouse, Versailles).
_DONNEES = """
01|Ain|Auvergne-Rhône-Alpes|A
02|Aisne|Hauts-de-France|B
03|Allier|Auvergne-Rhône-Alpes|A
04|Alpes-de-Haute-Provence|Provence-Alpes-Côte d'Azur|B
05|Hautes-Alpes|Provence-Alpes-Côte d'Azur|B
06|Alpes-Maritimes|Provence-Alpes-Côte d'Azur|B
07|Ardèche|Auvergne-Rhône-Alpes|A
08|Ardennes|Grand Est|B
09|Ariège|Occitanie|C
10|Aube|Grand Est|B
11|Aude|Occitanie|C
12|Aveyron|Occitanie|C
13|Bouches-du-Rhône|Provence-Alpes-Côte d'Azur|B
14|Calvados|Normandie|B
15|Cantal|Auvergne-Rhône-Alpes|A
16|Charente|Nouvelle-Aquitaine|A
17|Charente-Maritime|Nouvelle-Aquitaine|A
18|Cher|Centre-Val de Loire|B
19|Corrèze|Nouvelle-Aquitaine|A
2A|Corse-du-Sud|Corse|Corse
2B|Haute-Corse|Corse|Corse
21|Côte-d'Or|Bourgogne-Franche-Comté|A
22|Côtes-d'Armor|Bretagne|B
23|Creuse|Nouvelle-Aquitaine|A
24|Dordogne|Nouvelle-Aquitaine|A
25|Doubs|Bourgogne-Franche-Comté|A
26|Drôme|Auvergne-Rhône-Alpes|A
27|Eure|Normandie|B
28|Eure-et-Loir|Centre-Val de Loire|B
29|Finistère|Bretagne|B
30|Gard|Occitanie|C
31|Haute-Garonne|Occitanie|C
32|Gers|Occitanie|C
33|Gironde|Nouvelle-Aquitaine|A
34|Hérault|Occitanie|C
35|Ille-et-Vilaine|Bretagne|B
36|Indre|Centre-Val de Loire|B
37|Indre-et-Loire|Centre-Val de Loire|B
38|Isère|Auvergne-Rhône-Alpes|A
39|Jura|Bourgogne-Franche-Comté|A
40|Landes|Nouvelle-Aquitaine|A
41|Loir-et-Cher|Centre-Val de Loire|B
42|Loire|Auvergne-Rhône-Alpes|A
43|Haute-Loire|Auvergne-Rhône-Alpes|A
44|Loire-Atlantique|Pays de la Loire|B
45|Loiret|Centre-Val de Loire|B
46|Lot|Occitanie|C
47|Lot-et-Garonne|Nouvelle-Aquitaine|A
48|Lozère|Occitanie|C
49|Maine-et-Loire|Pays de la Loire|B
50|Manche|Normandie|B
51|Marne|Grand Est|B
52|Haute-Marne|Grand Est|B
53|Mayenne|Pays de la Loire|B
54|Meurthe-et-Moselle|Grand Est|B
55|Meuse|Grand Est|B
56|Morbihan|Bretagne|B
57|Moselle|Grand Est|B
58|Nièvre|Bourgogne-Franche-Comté|A
59|Nord|Hauts-de-France|B
60|Oise|Hauts-de-France|B
61|Orne|Normandie|B
62|Pas-de-Calais|Hauts-de-France|B
63|Puy-de-Dôme|Auvergne-Rhône-Alpes|A
64|Pyrénées-Atlantiques|Nouvelle-Aquitaine|A
65|Hautes-Pyrénées|Occitanie|C
66|Pyrénées-Orientales|Occitanie|C
67|Bas-Rhin|Grand Est|B
68|Haut-Rhin|Grand Est|B
69|Rhône|Auvergne-Rhône-Alpes|A
70|Haute-Saône|Bourgogne-Franche-Comté|A
71|Saône-et-Loire|Bourgogne-Franche-Comté|A
72|Sarthe|Pays de la Loire|B
73|Savoie|Auvergne-Rhône-Alpes|A
74|Haute-Savoie|Auvergne-Rhône-Alpes|A
75|Paris|Île-de-France|C
76|Seine-Maritime|Normandie|B
77|Seine-et-Marne|Île-de-France|C
78|Yvelines|Île-de-France|C
79|Deux-Sèvres|Nouvelle-Aquitaine|A
80|Somme|Hauts-de-France|B
81|Tarn|Occitanie|C
82|Tarn-et-Garonne|Occitanie|C
83|Var|Provence-Alpes-Côte d'Azur|B
84|Vaucluse|Provence-Alpes-Côte d'Azur|B
85|Vendée|Pays de la Loire|B
86|Vienne|Nouvelle-Aquitaine|A
87|Haute-Vienne|Nouvelle-Aquitaine|A
88|Vosges|Grand Est|B
89|Yonne|Bourgogne-Franche-Comté|A
90|Territoire de Belfort|Bourgogne-Franche-Comté|A
91|Essonne|Île-de-France|C
92|Hauts-de-Seine|Île-de-France|C
93|Seine-Saint-Denis|Île-de-France|C
94|Val-de-Marne|Île-de-France|C
95|Val-d'Oise|Île-de-France|C
971|Guadeloupe|Guadeloupe|Outre-mer
972|Martinique|Martinique|Outre-mer
973|Guyane|Guyane|Outre-mer
974|La Réunion|La Réunion|Outre-mer
976|Mayotte|Mayotte|Outre-mer
"""

DEPARTEMENTS: dict[str, Departement] = {
    code: Departement(code, nom, region, zone)
    for code, nom, region, zone in (ligne.split("|") for ligne in _DONNEES.strip().splitlines())
}
REGIONS: list[str] = sorted({d.region for d in DEPARTEMENTS.values()})


def departements_de(region: str) -> list[Departement]:
    return [d for d in DEPARTEMENTS.values() if d.region == region]


# --------------------------------------------------------------------------
# Vacances d'été (métropole : mêmes dates pour les zones A, B et C)

# Début des vacances (inclus) et jour de la rentrée (exclu), d'après les calendriers scolaires publiés.
# Années absentes : valeurs habituelles (VACANCES_ETE_HABITUELLES), à vérifier.
VACANCES_ETE_METROPOLE: dict[int, tuple[date, date]] = {
    2026: (date(2026, 7, 4), date(2026, 9, 1)),
    2027: (date(2027, 7, 3), date(2027, 9, 2)),
    2028: (date(2028, 7, 4), date(2028, 9, 1)),
}
VACANCES_ETE_HABITUELLES = ((7, 4), (9, 1))  # (mois, jour) du début et de la rentrée


@dataclass(frozen=True)
class CalendrierEte:
    """Dates des vacances d'été retenues pour caler les travaux d'un bâtiment scolaire.

    ``personnalise`` : (mois, jour) du début et de la rentrée, appliqués chaque année à la place du
    calendrier national (utile pour la Corse et l'outre-mer, ou un calendrier local).
    """

    personnalise: tuple[tuple[int, int], tuple[int, int]] | None = None

    def vacances(self, annee: int) -> tuple[date, date]:
        """(début inclus, rentrée exclue) des vacances d'été de l'année."""
        if self.personnalise is not None:
            (m1, j1), (m2, j2) = self.personnalise
            debut, rentree = date(annee, m1, j1), date(annee, m2, j2)
            # Vacances à cheval sur deux années (été austral : décembre à janvier).
            return (debut, rentree) if rentree > debut else (debut, date(annee + 1, m2, j2))
        if annee in VACANCES_ETE_METROPOLE:
            return VACANCES_ETE_METROPOLE[annee]
        (m1, j1), (m2, j2) = VACANCES_ETE_HABITUELLES
        return date(annee, m1, j1), date(annee, m2, j2)

    def en_vacances(self, jour: date) -> bool:
        return any(debut <= jour < fin for debut, fin in (self.vacances(jour.year - 1), self.vacances(jour.year)))

    def prochain_demarrage(self, jour: date, marge_jours: int) -> date:
        """Première date de démarrage possible : début des prochaines vacances, ou dès maintenant s'il en
        reste au moins ``marge_jours``."""
        for annee in (jour.year - 1, jour.year, jour.year + 1):
            debut, fin = self.vacances(annee)
            if jour <= debut:
                return debut
            if debut <= jour <= fin - timedelta(days=marge_jours):
                return jour
        return self.vacances(jour.year + 1)[0]
