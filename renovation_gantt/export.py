"""Export du planning (Excel, CSV) et sauvegarde / chargement de scénarios (JSON)."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from .phases import (
    FINANCEMENT_APRES_DEFAUT,
    TREVE_SEMAINES_DEFAUT,
    Autorisation,
    EtatProjet,
    FenetreTravaux,
    Phase,
    TypeAutorisation,
    phases_pour_etat,
)
from .planning import Planning, calculer_planning

VERSION_SCENARIO = 1


def planning_vers_dataframe(planning: Planning) -> pd.DataFrame:
    df = planning.taches.copy()
    return df.rename(
        columns={"Tache": "Tâche", "Debut": "Début", "Definition": "Définition", "Semaines": "Durée (semaines)"}
    ).drop(columns=["Id"])


def planning_vers_csv(planning: Planning) -> bytes:
    # Séparateur « ; » et BOM UTF-8 pour une ouverture directe dans Excel en français.
    return planning_vers_dataframe(planning).to_csv(index=False, sep=";").encode("utf-8-sig")


def indicateurs(planning: Planning) -> list[tuple[str, str]]:
    """Résumé du planning, partagé par les exports Excel et PDF."""
    lignes = [
        ("Date de début", planning.date_debut.strftime("%d/%m/%Y")),
        ("Date de fin estimée", planning.date_fin.strftime("%d/%m/%Y")),
        (
            "Durée totale",
            f"{planning.duree_totale_mois:.1f} mois ({planning.duree_totale_semaines:.0f} semaines)",
        ),
        ("Dont délais de validation MO", f"{planning.semaines_delai_mo():.0f} semaines"),
    ]
    if planning.autorisation is not None:
        a = planning.autorisation
        texte = a.type.value
        if a.requise:
            texte += f" — instruction {a.mois_instruction} mois"
            if a.abf:
                texte += " (avis ABF)"
            if a.purge_recours:
                texte += ", purge du recours des tiers"
        lignes.append(("Autorisation d'urbanisme", texte))
    for attente in planning.attentes:
        lignes.append((f"Attente avant « {attente.phase} »", f"{attente.jours / 7:.0f} semaines ({attente.motif})"))
    if planning.fenetre_travaux is not FenetreTravaux.AUCUNE:
        lignes.append(("Bâtiment scolaire", planning.fenetre_travaux.value))
    lignes.append(
        (
            "Trêve de fin d'année",
            f"{planning.treve_semaines} semaine(s) non travaillée(s)"
            if planning.treve_semaines
            else "Non prise en compte",
        )
    )
    return lignes


def _echapper_ics(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def planning_vers_ics(planning: Planning, nom_projet: str = "Projet de rénovation") -> bytes:
    """Jalons du planning au format iCalendar (Outlook, Google Agenda…), en événements d'une journée."""
    horodatage = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Planificateur renovation//FR",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_echapper_ics(nom_projet)}",
    ]
    for jalon in planning.jalons:
        uid = hashlib.sha1(f"{nom_projet}|{jalon.nom}".encode()).hexdigest()
        lignes += [
            "BEGIN:VEVENT",
            f"UID:{uid}@planificateur-renovation",
            f"DTSTAMP:{horodatage}",
            f"DTSTART;VALUE=DATE:{jalon.date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{jalon.date + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_echapper_ics(f'{nom_projet} – {jalon.nom}')}",
            "DESCRIPTION:Jalon prévisionnel issu du planificateur de rénovation.",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lignes.append("END:VCALENDAR")
    return ("\r\n".join(lignes) + "\r\n").encode("utf-8")


def planning_vers_excel(planning: Planning) -> bytes:
    tampon = io.BytesIO()
    resume = pd.DataFrame(indicateurs(planning), columns=["Indicateur", "Valeur"])
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
    autorisation: Autorisation = field(default_factory=Autorisation)
    treve_semaines: int = TREVE_SEMAINES_DEFAUT
    # Phase après laquelle démarre le montage des dossiers de financement (None : dès le début).
    financement_apres: str | None = FINANCEMENT_APRES_DEFAUT
    batiment_scolaire: bool = False
    fenetre_travaux: FenetreTravaux = FenetreTravaux.AUCUNE

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

    def planning(self) -> Planning:
        return calculer_planning(
            self.phases(),
            self.date_debut,
            self.financement_semaines,
            self.autorisation,
            self.treve_semaines,
            self.financement_apres,
            fenetre_travaux=self.fenetre_travaux if self.batiment_scolaire else FenetreTravaux.AUCUNE,
        )

    def vers_json(self) -> str:
        return json.dumps(
            {
                "version": VERSION_SCENARIO,
                "etat": self.etat.name,
                "date_debut": self.date_debut.isoformat(),
                "financement_semaines": self.financement_semaines,
                "durees": self.durees,
                "delais_mo": self.delais_mo,
                "autorisation": {
                    "type": self.autorisation.type.name,
                    "abf": self.autorisation.abf,
                    "purge_recours": self.autorisation.purge_recours,
                },
                "treve_semaines": self.treve_semaines,
                "financement_apres": self.financement_apres,
                "batiment_scolaire": self.batiment_scolaire,
                "fenetre_travaux": self.fenetre_travaux.name,
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
            # Clés absentes des scénarios enregistrés avant l'ajout de l'instruction et de la trêve.
            autorisation = donnees.get("autorisation") or {}
            return cls(
                etat=EtatProjet[donnees["etat"]],
                date_debut=date.fromisoformat(donnees["date_debut"]),
                financement_semaines=donnees.get("financement_semaines"),
                durees={k: int(v) for k, v in donnees.get("durees", {}).items()},
                delais_mo={k: int(v) for k, v in donnees.get("delais_mo", {}).items()},
                autorisation=Autorisation(
                    type=TypeAutorisation[autorisation.get("type", "DP")],
                    abf=bool(autorisation.get("abf", False)),
                    purge_recours=bool(autorisation.get("purge_recours", False)),
                ),
                treve_semaines=int(donnees.get("treve_semaines", TREVE_SEMAINES_DEFAUT)),
                # Avant cette option, le financement démarrait toujours avec le projet.
                financement_apres=donnees.get("financement_apres"),
                batiment_scolaire=bool(donnees.get("batiment_scolaire", False)),
                fenetre_travaux=FenetreTravaux[donnees.get("fenetre_travaux", "AUCUNE")],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Fichier de scénario invalide : {exc}") from exc
