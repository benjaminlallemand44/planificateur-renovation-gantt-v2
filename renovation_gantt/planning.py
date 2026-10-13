"""Calcul du planning à partir d'une séquence de phases.

Les phases s'enchaînent : chaque phase démarre à la fin de la précédente
(délai de validation du maître d'ouvrage inclus). En parallèle :

- la recherche de financement, à partir de la date de début ;
- l'instruction de l'autorisation d'urbanisme, à partir du dépôt du dossier,
  pendant que la maîtrise d'œuvre poursuit ses études (PRO, DCE, ACT).
  Les travaux (VISA puis DET) ne démarrent qu'une fois l'autorisation obtenue.

Les durées des phases sont des semaines travaillées : la trêve de fin d'année
les prolonge d'autant. Les délais réglementaires (instruction, recours des
tiers) courent en mois calendaires, trêve comprise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .phases import (
    ARTICLES_INSTRUCTION,
    DEFINITION_FINANCEMENT,
    MOIS_RECOURS_TIERS,
    Autorisation,
    Groupe,
    Phase,
    definition_courte,
)

TYPE_PHASE = "Phase"
TYPE_DELAI_MO = "Délai MO"
TYPE_FINANCEMENT = "Financement"
TYPE_INSTRUCTION = "Instruction réglementaire"
TYPE_RECOURS = "Recours des tiers"

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
    periodes_treve: list[tuple[date, date]] = field(default_factory=list)
    # Nombre de jours pendant lesquels les travaux attendent l'autorisation d'urbanisme.
    attente_autorisation_jours: int = 0
    autorisation: Autorisation | None = None
    treve_semaines: int = 0

    @property
    def duree_totale_semaines(self) -> float:
        return (self.date_fin - self.date_debut).days / 7

    @property
    def duree_totale_mois(self) -> float:
        return (self.date_fin - self.date_debut).days / 30.4375

    def semaines_par_groupe(self) -> dict[str, float]:
        df = self.taches[self.taches["Type"].isin([TYPE_PHASE, TYPE_DELAI_MO])]
        return df.groupby("Groupe", sort=False)["Semaines"].sum().to_dict()

    def semaines_delai_mo(self) -> float:
        return float(self.taches.loc[self.taches["Type"] == TYPE_DELAI_MO, "Semaines"].sum())


def calculer_planning(
    phases: list[Phase],
    date_debut: date,
    financement_semaines: int | None = None,
    autorisation: Autorisation | None = None,
    treve_semaines: int = 0,
) -> Planning:
    """Calcule les dates de chaque phase.

    ``financement_semaines`` à ``None`` (ou 0) désactive la recherche de financement.
    ``autorisation`` à ``None`` désactive la modélisation de l'instruction réglementaire.
    ``treve_semaines`` : nombre de semaines non travaillées se terminant le 1er janvier (0 = aucune).
    """
    if isinstance(date_debut, pd.Timestamp):
        date_debut = date_debut.date()
    ferme = _fermeture(treve_semaines)

    lignes: list[dict] = []
    jalons: list[Jalon] = []

    if financement_semaines:
        debut, fin = _etaler(date_debut, financement_semaines, ferme)
        lignes.append(
            _ligne(
                "FINANCEMENT",
                "💶 Recherche de financement",
                debut,
                fin,
                TYPE_FINANCEMENT,
                Groupe.FINANCEMENT,
                DEFINITION_FINANCEMENT,
                financement_semaines,
            )
        )

    courant = date_debut
    fin_autorisation: date | None = None
    attente = 0
    for phase in phases:
        if not phase.afficher_gantt:
            continue
        if phase.debut_instruction and autorisation is not None and not autorisation.requise:
            continue
        if phase.attend_autorisation and fin_autorisation and fin_autorisation > courant:
            attente = (fin_autorisation - courant).days
            courant = fin_autorisation

        debut, fin_phase = _etaler(courant, phase.duree, ferme)
        if phase.duree > 0:
            lignes.append(
                _ligne(
                    phase.id,
                    phase.libelle,
                    debut,
                    fin_phase,
                    TYPE_PHASE,
                    phase.groupe,
                    definition_courte(phase),
                    phase.duree,
                )
            )
        fin = fin_phase
        if phase.delai_mo > 0:
            debut_delai, fin = _etaler(fin_phase, phase.delai_mo, ferme)
            lignes.append(
                _ligne(
                    phase.id,
                    phase.libelle,
                    debut_delai,
                    fin,
                    TYPE_DELAI_MO,
                    phase.groupe,
                    "Délai de validation par le maître d'ouvrage.",
                    phase.delai_mo,
                )
            )
        if phase.jalon_fin:
            jalons.append(Jalon(phase.jalon_fin, fin))
        if phase.debut_instruction and autorisation is not None and autorisation.requise:
            fin_autorisation = _instruction(fin, autorisation, lignes, jalons)
        courant = fin

    taches = pd.DataFrame(lignes, columns=COLONNES)
    date_fin = max([courant, *taches["Fin"]]) if not taches.empty else courant
    jalons.append(Jalon("Fin du projet", date_fin))
    jalons.sort(key=lambda j: j.date)
    return Planning(
        taches=taches,
        jalons=jalons,
        date_debut=date_debut,
        date_fin=date_fin,
        periodes_treve=periodes_treve(date_debut, date_fin, treve_semaines),
        attente_autorisation_jours=attente,
        autorisation=autorisation,
        treve_semaines=treve_semaines,
    )


def _instruction(depot: date, autorisation: Autorisation, lignes: list[dict], jalons: list[Jalon]) -> date:
    """Ajoute l'instruction (et la purge du recours des tiers) ; renvoie la date à partir de laquelle
    les travaux peuvent démarrer."""
    mois = autorisation.mois_instruction
    obtention = _ajouter_mois(depot, mois)
    detail = f"Délai d'instruction de droit commun : {mois} mois ({ARTICLES_INSTRUCTION[autorisation.type]})"
    if autorisation.abf and mois > 0:
        detail += ", majoré pour avis de l'Architecte des Bâtiments de France"
    lignes.append(
        _ligne(
            "INSTRUCTION",
            f"🏛️ Instruction {autorisation.sigle} ({mois} mois)",
            depot,
            obtention,
            TYPE_INSTRUCTION,
            Groupe.MOE,
            detail + ". Délai indicatif, à confirmer avec le service instructeur.",
            (obtention - depot).days / 7,
        )
    )
    jalons.append(Jalon("Autorisation obtenue", obtention))
    if not autorisation.purge_recours:
        return obtention

    purge = _ajouter_mois(obtention, MOIS_RECOURS_TIERS)
    lignes.append(
        _ligne(
            "RECOURS",
            f"⚖️ Recours des tiers ({MOIS_RECOURS_TIERS} mois)",
            obtention,
            purge,
            TYPE_RECOURS,
            Groupe.MOE,
            "Délai de recours des tiers à compter de l'affichage sur le terrain (art. R600-2 du code de l'urbanisme).",
            (purge - obtention).days / 7,
        )
    )
    jalons.append(Jalon("Recours purgé", purge))
    return purge


# --------------------------------------------------------------------------
# Calendrier


def _fermeture(treve_semaines: int) -> Callable[[date], bool]:
    """Renvoie une fonction indiquant si un jour tombe pendant la trêve de fin d'année."""
    jours = 7 * max(0, treve_semaines)

    def ferme(jour: date) -> bool:
        if jours == 0:
            return False
        if jour.month == 1 and jour.day == 1:
            return True
        return jour.month == 12 and (date(jour.year + 1, 1, 1) - jour).days < jours

    return ferme


def periodes_treve(debut: date, fin: date, treve_semaines: int) -> list[tuple[date, date]]:
    """Périodes de trêve (début inclus, fin exclue) qui recoupent [debut, fin]."""
    if treve_semaines <= 0:
        return []
    periodes = []
    for annee in range(debut.year - 1, fin.year + 1):
        fin_treve = date(annee + 1, 1, 2)
        debut_treve = fin_treve - timedelta(days=7 * treve_semaines)
        if debut_treve < fin and fin_treve > debut:
            periodes.append((debut_treve, fin_treve))
    return periodes


def _etaler(debut: date, semaines: float, ferme: Callable[[date], bool]) -> tuple[date, date]:
    """Place ``semaines`` de travail à partir de ``debut`` en sautant les jours de trêve.

    Renvoie (début effectif, fin exclusive)."""
    jour = debut
    while ferme(jour):
        jour += timedelta(days=1)
    depart = jour
    restant = round(semaines * 7)
    while restant > 0:
        if not ferme(jour):
            restant -= 1
        jour += timedelta(days=1)
    return depart, jour


def _ajouter_mois(jour: date, mois: int) -> date:
    return (pd.Timestamp(jour) + pd.DateOffset(months=mois)).date()


def _ligne(id_, tache, debut, fin, type_, groupe, definition, semaines) -> dict:
    return {
        "Id": id_,
        "Tache": tache,
        "Debut": debut,
        "Fin": fin,
        "Type": type_,
        "Groupe": Groupe(groupe).value,
        "Definition": definition,
        "Semaines": float(semaines),
    }
