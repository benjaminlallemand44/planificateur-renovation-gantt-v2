"""Suivi du projet : planning de référence, écarts et points d'attention."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .avancement import Avancement, Statut
from .planning import TYPE_ATTENTE, TYPE_GPA, TYPE_RECOURS, Jalon, Planning

# Types de lignes qui ne se suivent pas (elles découlent d'autres éléments).
TYPES_NON_SUIVIS = (TYPE_ATTENTE, TYPE_GPA, TYPE_RECOURS)

SEUIL_VERT_JOURS = 14
SEUIL_ORANGE_JOURS = 56


@dataclass(frozen=True)
class Reference:
    """Planning figé à une date (par exemple lors d'une délibération), pour mesurer les écarts."""

    nom: str
    cree_le: date
    date_fin: date
    # Pour chaque élément suivi : (début, fin) prévus.
    elements: dict[str, tuple[date, date]] = field(default_factory=dict)
    jalons: list[Jalon] = field(default_factory=list)

    @classmethod
    def depuis_planning(cls, planning: Planning, nom: str, cree_le: date) -> Reference:
        return cls(nom, cree_le, planning.date_fin, etendues(planning), list(planning.jalons))

    def vers_dict(self) -> dict:
        return {
            "nom": self.nom,
            "cree_le": self.cree_le.isoformat(),
            "date_fin": self.date_fin.isoformat(),
            "elements": {k: [d.isoformat(), f.isoformat()] for k, (d, f) in self.elements.items()},
            "jalons": [[j.nom, j.date.isoformat()] for j in self.jalons],
        }

    @classmethod
    def depuis_dict(cls, donnees: dict) -> Reference:
        return cls(
            nom=donnees["nom"],
            cree_le=date.fromisoformat(donnees["cree_le"]),
            date_fin=date.fromisoformat(donnees["date_fin"]),
            elements={
                k: (date.fromisoformat(d), date.fromisoformat(f)) for k, (d, f) in donnees.get("elements", {}).items()
            },
            jalons=[Jalon(n, date.fromisoformat(d)) for n, d in donnees.get("jalons", [])],
        )


def etendues(planning: Planning) -> dict[str, tuple[date, date]]:
    """Début et fin (validation comprise) de chaque élément suivi du planning."""
    df = planning.taches[~planning.taches["Type"].isin(TYPES_NON_SUIVIS)]
    groupes = df.groupby("Id", sort=False).agg(Debut=("Debut", "min"), Fin=("Fin", "max"))
    return {i: (r.Debut, r.Fin) for i, r in groupes.iterrows()}


def elements_suivis(planning: Planning) -> list[tuple[str, str]]:
    """(identifiant, libellé) des éléments dont on peut saisir l'avancement, dans l'ordre du planning."""
    df = planning.taches[~planning.taches["Type"].isin(TYPES_NON_SUIVIS)]
    return list(dict.fromkeys(zip(df["Id"], df["Tache"], strict=True)))


def ecart_fin_jours(planning: Planning, reference: Reference | None) -> int | None:
    return None if reference is None else (planning.date_fin - reference.date_fin).days


def meteo(ecart_jours: int | None) -> tuple[str, str]:
    """(niveau, libellé) : niveau « vert », « orange » ou « rouge »."""
    if ecart_jours is None:
        return "gris", "Pas de planning de référence"
    if ecart_jours <= SEUIL_VERT_JOURS:
        return "vert", "Dans les temps" if ecart_jours <= 0 else f"Léger décalage ({_semaines(ecart_jours)})"
    if ecart_jours <= SEUIL_ORANGE_JOURS:
        return "orange", f"Glissement de {_semaines(ecart_jours)}"
    return "rouge", f"Glissement important de {_semaines(ecart_jours)}"


def comparer(planning: Planning, reference: Reference | None) -> pd.DataFrame:
    """Tableau de suivi : statut, dates actuelles, dates de référence et écart sur la fin."""
    actuel = etendues(planning)
    lignes = []
    for id_, libelle in elements_suivis(planning):
        debut, fin = actuel[id_]
        av = planning.avancement.get(id_, Avancement())
        ref = reference.elements.get(id_) if reference else None
        lignes.append(
            {
                "Id": id_,
                "Élément": libelle,
                "Statut": av.statut.value,
                "Début": debut,
                "Fin": fin,
                "Fin (référence)": ref[1] if ref else None,
                "Écart (sem.)": round((fin - ref[1]).days / 7) if ref else None,
                "Commentaire": av.commentaire,
            }
        )
    return pd.DataFrame(lignes)


def prochains_jalons(planning: Planning, aujourd_hui: date, nombre: int = 5) -> list[Jalon]:
    return [j for j in planning.jalons if j.date >= aujourd_hui][:nombre]


def points_attention(planning: Planning, reference: Reference | None, aujourd_hui: date) -> list[str]:
    """Messages à destination du pilote du projet et des élus."""
    points: list[str] = []
    ecart = ecart_fin_jours(planning, reference)
    if ecart is not None and ecart > SEUIL_VERT_JOURS:
        points.append(
            f"La fin du projet est prévue le {planning.date_fin:%d/%m/%Y}, soit {_semaines(ecart)} plus tard "
            f"que la référence « {reference.nom} » ({reference.date_fin:%d/%m/%Y})."
        )
    elif ecart is not None and ecart < -SEUIL_VERT_JOURS:
        points.append(f"Le projet est en avance de {_semaines(-ecart)} sur la référence « {reference.nom} ».")

    for nom in planning.depassements:
        points.append(f"« {nom} » dépasse sa date de fin prévue : indiquez une nouvelle date de fin.")

    if reference is not None:
        actuel = etendues(planning)
        en_retard = [
            libelle
            for id_, libelle in elements_suivis(planning)
            if id_ in reference.elements
            and reference.elements[id_][0] < aujourd_hui
            and planning.avancement.get(id_, Avancement()).statut is Statut.A_VENIR
            and actuel[id_][0] > reference.elements[id_][0]
        ]
        if en_retard:
            points.append(
                "Non démarré alors que prévu dans la référence : " + ", ".join(_sans_icone(n) for n in en_retard) + "."
            )

    for attente in planning.attentes:
        if attente.fin > aujourd_hui:
            points.append(f"« {attente.phase} » attendra {_semaines(attente.jours)} : {attente.motif}.")

    limite = aujourd_hui + timedelta(weeks=8)
    for jalon in planning.jalons:
        if aujourd_hui <= jalon.date <= limite and "Fin" not in jalon.nom:
            points.append(f"Échéance proche : {jalon.nom} le {jalon.date:%d/%m/%Y}.")
    return points


def _semaines(jours: int) -> str:
    semaines = max(1, round(jours / 7))
    return f"{semaines} semaine{'s' if semaines > 1 else ''}"


def _sans_icone(libelle: str) -> str:
    return libelle.split(" ", 1)[1] if " " in libelle and not libelle[0].isalnum() else libelle
