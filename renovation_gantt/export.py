"""Export du planning (Excel, CSV) et sauvegarde / chargement de scénarios (JSON)."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .phases import EtatProjet, Phase, phases_pour_etat
from .planning import Planning

VERSION_SCENARIO = 1


def planning_vers_dataframe(planning: Planning) -> pd.DataFrame:
    df = planning.taches.copy()
    return df.rename(
        columns={"Tache": "Tâche", "Debut": "Début", "Definition": "Définition", "Semaines": "Durée (semaines)"}
    ).drop(columns=["Id"])


def planning_vers_csv(planning: Planning) -> bytes:
    # Séparateur « ; » et BOM UTF-8 pour une ouverture directe dans Excel en français.
    return planning_vers_dataframe(planning).to_csv(index=False, sep=";").encode("utf-8-sig")


def planning_vers_excel(planning: Planning) -> bytes:
    tampon = io.BytesIO()
    resume = pd.DataFrame(
        {
            "Indicateur": [
                "Date de début",
                "Date de fin",
                "Durée totale (semaines)",
                "Durée totale (mois)",
                "Dont délais de validation MO (semaines)",
            ],
            "Valeur": [
                planning.date_debut.strftime("%d/%m/%Y"),
                planning.date_fin.strftime("%d/%m/%Y"),
                round(planning.duree_totale_semaines, 1),
                round(planning.duree_totale_mois, 1),
                round(planning.semaines_delai_mo(), 1),
            ],
        }
    )
    jalons = pd.DataFrame(
        {"Jalon": [j.nom for j in planning.jalons], "Date": [j.date.strftime("%d/%m/%Y") for j in planning.jalons]}
    )
    with pd.ExcelWriter(tampon, engine="openpyxl") as writer:
        resume.to_excel(writer, sheet_name="Résumé", index=False)
        planning_vers_dataframe(planning).to_excel(writer, sheet_name="Planning", index=False)
        jalons.to_excel(writer, sheet_name="Jalons", index=False)
        for feuille in writer.sheets.values():
            for colonne in feuille.columns:
                largeur = max(len(str(c.value or "")) for c in colonne)
                feuille.column_dimensions[colonne[0].column_letter].width = min(max(12, largeur + 2), 80)
    return tampon.getvalue()


@dataclass
class Scenario:
    """Paramètres saisis par l'utilisateur, sérialisables en JSON."""

    etat: EtatProjet
    date_debut: date
    financement_semaines: int | None = 6
    durees: dict[str, int] = field(default_factory=dict)
    delais_mo: dict[str, int] = field(default_factory=dict)

    def appliquer(self, phases: list[Phase]) -> list[Phase]:
        """Applique les durées personnalisées en respectant les minimums réglementaires."""
        resultat = []
        for p in phases:
            duree = p.duree
            if p.modifiable and p.id in self.durees:
                duree = max(p.duree_min, int(self.durees[p.id]))
            delai = max(0, int(self.delais_mo.get(p.id, p.delai_mo)))
            resultat.append(p.avec(duree=duree, delai_mo=delai))
        return resultat

    def phases(self) -> list[Phase]:
        return self.appliquer(phases_pour_etat(self.etat))

    def vers_json(self) -> str:
        return json.dumps(
            {
                "version": VERSION_SCENARIO,
                "etat": self.etat.name,
                "date_debut": self.date_debut.isoformat(),
                "financement_semaines": self.financement_semaines,
                "durees": self.durees,
                "delais_mo": self.delais_mo,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def depuis_json(cls, texte: str | bytes) -> Scenario:
        try:
            donnees = json.loads(texte)
            if donnees.get("version") != VERSION_SCENARIO:
                raise ValueError(f"version de scénario non prise en charge : {donnees.get('version')}")
            return cls(
                etat=EtatProjet[donnees["etat"]],
                date_debut=date.fromisoformat(donnees["date_debut"]),
                financement_semaines=donnees.get("financement_semaines"),
                durees={k: int(v) for k, v in donnees.get("durees", {}).items()},
                delais_mo={k: int(v) for k, v in donnees.get("delais_mo", {}).items()},
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Fichier de scénario invalide : {exc}") from exc
