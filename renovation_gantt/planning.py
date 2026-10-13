"""Calcul du planning à partir d'une séquence de phases.

Les phases s'enchaînent : chaque phase démarre à la fin de la précédente
(délai de validation du maître d'ouvrage inclus). La recherche de financement
se déroule en parallèle, à partir de la date de début.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .phases import DEFINITION_FINANCEMENT, Groupe, Phase, definition_courte

TYPE_PHASE = "Phase"
TYPE_DELAI_MO = "Délai MO"
TYPE_FINANCEMENT = "Financement"

COLONNES = ["Id", "Tache", "Debut", "Fin", "Type", "Groupe", "Definition", "Semaines"]


@dataclass(frozen=True)
class Jalon:
    nom: str
    date: date


@dataclass(frozen=True)
class Planning:
    taches: pd.DataFrame
    jalons: list[Jalon]
    date_debut: date
    date_fin: date

    @property
    def duree_totale_semaines(self) -> float:
        return (self.date_fin - self.date_debut).days / 7

    @property
    def duree_totale_mois(self) -> float:
        return (self.date_fin - self.date_debut).days / 30.4375

    def semaines_par_groupe(self) -> dict[str, float]:
        df = self.taches[self.taches["Type"] != TYPE_FINANCEMENT]
        return df.groupby("Groupe", sort=False)["Semaines"].sum().to_dict()

    def semaines_delai_mo(self) -> float:
        return float(self.taches.loc[self.taches["Type"] == TYPE_DELAI_MO, "Semaines"].sum())


def calculer_planning(
    phases: list[Phase],
    date_debut: date,
    financement_semaines: int | None = None,
) -> Planning:
    """Calcule les dates de chaque phase.

    ``financement_semaines`` à ``None`` (ou 0) désactive la recherche de financement.
    """
    if isinstance(date_debut, pd.Timestamp):
        date_debut = date_debut.date()

    lignes: list[dict] = []
    jalons: list[Jalon] = []

    if financement_semaines:
        lignes.append(
            _ligne(
                "FINANCEMENT",
                "💶 Recherche de financement",
                date_debut,
                date_debut + timedelta(weeks=financement_semaines),
                TYPE_FINANCEMENT,
                Groupe.FINANCEMENT,
                DEFINITION_FINANCEMENT,
            )
        )

    courant = date_debut
    for phase in phases:
        if not phase.afficher_gantt:
            continue
        fin_phase = courant + timedelta(weeks=phase.duree)
        if phase.duree > 0:
            lignes.append(
                _ligne(phase.id, phase.libelle, courant, fin_phase, TYPE_PHASE, phase.groupe, definition_courte(phase))
            )
        fin = fin_phase
        if phase.delai_mo > 0:
            fin = fin_phase + timedelta(weeks=phase.delai_mo)
            lignes.append(
                _ligne(
                    phase.id,
                    phase.libelle,
                    fin_phase,
                    fin,
                    TYPE_DELAI_MO,
                    phase.groupe,
                    "Délai de validation par le maître d'ouvrage.",
                )
            )
        if phase.jalon_fin:
            jalons.append(Jalon(phase.jalon_fin, fin))
        courant = fin

    taches = pd.DataFrame(lignes, columns=COLONNES)
    date_fin = max([courant] + [t for t in taches["Fin"]]) if not taches.empty else courant
    jalons.append(Jalon("Fin du projet", date_fin))
    return Planning(taches=taches, jalons=jalons, date_debut=date_debut, date_fin=date_fin)


def _ligne(id_, tache, debut, fin, type_, groupe, definition) -> dict:
    return {
        "Id": id_,
        "Tache": tache,
        "Debut": debut,
        "Fin": fin,
        "Type": type_,
        "Groupe": Groupe(groupe).value,
        "Definition": definition,
        "Semaines": (fin - debut).days / 7,
    }
