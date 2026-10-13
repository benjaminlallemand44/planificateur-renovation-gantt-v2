"""Avancement réel saisi par l'utilisateur, phase par phase."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Statut(str, Enum):
    A_VENIR = "À venir"
    EN_COURS = "En cours"
    TERMINEE = "Terminée"


@dataclass(frozen=True)
class Avancement:
    """Avancement d'un élément du planning (phase, dossiers de financement, instruction).

    - ``Terminée`` : ``debut`` et ``fin`` sont les dates réelles (validation du maître d'ouvrage comprise).
    - ``En cours`` : ``debut`` est la date réelle de démarrage, ``fin`` la nouvelle date de fin prévue
      (facultative : à défaut, la durée prévue s'applique).
    - ``À venir`` : les dates sont ignorées ; la phase ne peut pas démarrer avant aujourd'hui.
    """

    statut: Statut = Statut.A_VENIR
    debut: date | None = None
    fin: date | None = None
    commentaire: str = ""

    def vers_dict(self) -> dict:
        return {
            "statut": self.statut.name,
            "debut": self.debut.isoformat() if self.debut else None,
            "fin": self.fin.isoformat() if self.fin else None,
            "commentaire": self.commentaire,
        }

    @classmethod
    def depuis_dict(cls, donnees: dict) -> Avancement:
        return cls(
            statut=Statut[donnees.get("statut", "A_VENIR")],
            debut=date.fromisoformat(donnees["debut"]) if donnees.get("debut") else None,
            fin=date.fromisoformat(donnees["fin"]) if donnees.get("fin") else None,
            commentaire=donnees.get("commentaire") or "",
        )
