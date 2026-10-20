"""Référentiel métier : états du projet, phases, durées par défaut et glossaire.

Ce module ne dépend ni de Streamlit ni de Plotly : il peut être testé et
réutilisé indépendamment de l'interface.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class EtatProjet(str, Enum):
    """Avancement du projet de rénovation, tel que déclaré par l'utilisateur."""

    SANS_AUDIT = "Nous n'avons pas encore effectué d'audit énergétique"
    AUDIT_RECU = "Nous venons de recevoir les comptes rendus des études préalables (dont l'audit énergétique)"
    AMO_PROGRAMMISTE = "Nous souhaitons faire intervenir un AMO Programmiste"
    RECRUTEMENT_MOE = "Nous voulons lancer notre marché de recrutement de maîtrise d'oeuvre"
    MOE_SELECTIONNEE = "Nous venons de sélectionner notre équipe de maitrise d'oeuvre"

    @property
    def libelle_court(self) -> str:
        """Libellé tenant sur une ligne d'écran de smartphone."""
        return LIBELLES_COURTS_ETATS[self]


LIBELLES_COURTS_ETATS = {
    EtatProjet.SANS_AUDIT: "Pas encore d'audit énergétique",
    EtatProjet.AUDIT_RECU: "Études préalables reçues (audit)",
    EtatProjet.AMO_PROGRAMMISTE: "Recours à un AMO programmiste",
    EtatProjet.RECRUTEMENT_MOE: "Lancement du marché de MOE",
    EtatProjet.MOE_SELECTIONNEE: "Équipe de MOE sélectionnée",
}


class Groupe(str, Enum):
    """Grandes catégories d'étapes, affichées en bandeau au-dessus du Gantt."""

    ETUDES = "Études préalables"
    AMO = "AMO Programmiste"
    SELECTION_MOE = "Sélection MOE"
    MOE = "MOE (Loi MOP)"
    FINANCEMENT = "Financement"


COULEURS_GROUPES: dict[Groupe, str] = {
    Groupe.ETUDES: "#cfe3ff",
    Groupe.AMO: "#d6f0e0",
    Groupe.SELECTION_MOE: "#ffe5cc",
    Groupe.MOE: "#e6ccff",
    Groupe.FINANCEMENT: "#d6f5d6",
}


@dataclass(frozen=True)
class Phase:
    """Une phase du projet.

    ``duree`` et ``delai_mo`` sont exprimés en semaines. ``delai_mo`` est le
    temps de validation par le maître d'ouvrage qui suit la phase.
    """

    id: str
    nom: str
    groupe: Groupe
    duree: int
    delai_mo: int = 0
    duree_min: int = 1
    modifiable: bool = True
    afficher_gantt: bool = True
    icone: str = "📝"
    jalon_fin: str | None = None
    # L'instruction de l'autorisation d'urbanisme démarre à la fin de cette phase.
    debut_instruction: bool = False
    # Phase menée en parallèle : elle démarre avec la phase suivante sans la retarder.
    parallele: bool = False
    # Identifiants de ce qui doit être terminé avant que la phase démarre
    # (une phase, ou "AUTORISATION" / "FINANCEMENT").
    prerequis: tuple[str, ...] = ()
    # Identifiants de ce qui doit être terminé avant la fin de la phase (signature).
    prerequis_signature: tuple[str, ...] = ()

    @property
    def libelle(self) -> str:
        return f"{self.icone} {self.nom}"

    def avec(self, **changements) -> Phase:
        return replace(self, **changements)


# --------------------------------------------------------------------------
# Glossaire (clé = identifiant de phase)

GLOSSAIRE_COURT: dict[str, str] = {
    "DIAG": "Analyse fonctionnelle, urbanistique et technique du bâti existant, estimation financière et faisabilité.",
    "ESQ": "Proposer des solutions d'ensemble, vérifier faisabilité et compatibilité financière (n'apparaît pas sur le Gantt).",
    "APS": "Proposer des solutions traduisant le programme fonctionnel, dispositions techniques générales et estimation du coût (min. 3 semaines).",
    "APD": "Déterminer surfaces détaillées, plans, façades, principes constructifs et cohérence technique et économique (min. 6 semaines).",
    "AUTORISATIONS": "Rédaction des documents nécessaires aux autorisations (Permis de Construire / Déclaration Préalable).",
    "PRO": "Préciser les éléments conceptuels, établir le coût prévisionnel et le délai global de réalisation (min. 4 semaines).",
    "DCE": "Dossier de Consultation des Entreprises fourni par la maîtrise d'œuvre pour consulter les entreprises.",
    "ACT": "Consultation des entreprises (publication : 35 jours minimum en appel d'offres ouvert), analyse des offres, attribution et signature (délai d'attente de 11 jours en procédure formalisée).",
    "VISA": "Période de préparation du chantier : études d'exécution des entreprises, visas de la MOE, approvisionnements (menuiseries : souvent 8 à 12 semaines).",
    "CT_CSPS": "Recrutement du contrôleur technique et du coordonnateur sécurité et protection de la santé, à mener en parallèle pour qu'ils interviennent dès l'APS.",
    "DET": "Diriger l'exécution des travaux, organiser les réunions de chantier, contrôler la qualité et les paiements.",
    "AOR": "Assistance aux opérations de réception : suivi des réserves, validation des DOE et gestion des désordres en GPA.",
}

GLOSSAIRE_COMPLET: dict[str, str] = {
    "DIAG": "Cette étape de la mission de conception a pour objet d'établir un état des lieux, de fournir une analyse fonctionnelle, urbanistique, architecturale et technique du bâti existant et ainsi de permettre d'établir un programme fonctionnel d'utilisation du bâtiment ainsi qu'une estimation financière et d'en déduire la faisabilité de l'opération.",
    "ESQ": "Cette étape de la mission de conception a pour objet de proposer une ou plusieurs solutions d'ensemble, traduisant les éléments majeurs du programme, d'en indiquer les délais de réalisation, d'examiner leur compatibilité avec la partie de l'enveloppe financière prévisionnelle retenue par le maître d'ouvrage et affectée aux travaux, ainsi que de vérifier la faisabilité de l'opération au regard des différentes contraintes du programme et du site. Elle n'apparaît pas sur le Gantt.",
    "APS": "Cette étape de la mission de conception a pour objet de proposer des solutions traduisant le programme fonctionnel, d'en présenter les dispositions générales techniques, d'indiquer des durées prévisionnelles et d'établir une estimation provisoire du coût prévisionnel des travaux.",
    "APD": "Déterminer les surfaces détaillées de tous les éléments du programme, arrêter plans, coupes et façades, définir les principes constructifs, matériaux et installations et vérifier la cohérence technique et économique.",
    "AUTORISATIONS": "Lorsque l'APD est validé, rédiger les documents nécessaires à l'obtention des autorisations administratives (permis de construire, déclaration préalable) et suivre l'instruction auprès des services administratifs.",
    "PRO": "Préciser, déterminer et décrire les éléments de conception des phases précédentes, établir un coût prévisionnel et un délai global de réalisation.",
    "DCE": "Fournir le dossier de consultation des entreprises comportant les pièces nécessaires à la consultation et traduisant les choix du maître d'ouvrage.",
    "ACT": "Assister le maître d'ouvrage pour la passation des marchés de travaux : préparer et publier la consultation (35 jours minimum de délai de réponse en appel d'offres ouvert, délai raisonnable en procédure adaptée), analyser les offres et vérifier leur conformité technique et financière, préparer l'attribution (commission d'appel d'offres ou décision de l'exécutif) puis la signature, après le délai d'attente de 11 jours imposé en procédure formalisée.",
    "VISA": "Examiner la conformité au projet des études d'exécution et de synthèse faites par les entreprises, et délivrer le visa correspondant. Dans le planning, cette phase couvre la période de préparation du chantier qui suit l'ordre de service : études d'exécution, visas, commandes et approvisionnements (les menuiseries demandent souvent 8 à 12 semaines de fabrication).",
    "DET": "Diriger l'exécution des travaux : s'assurer que l'ouvrage est réalisé conformément aux marchés, organiser les réunions de chantier, actualiser le calendrier et vérifier les situations de travaux.",
    "AOR": "Assister le maître d'ouvrage lors de la réception, assurer le suivi des réserves jusqu'à leur levée, valider les DOE et examiner les désordres pendant la période de garantie de parfait achèvement (GPA).",
}

LIBELLES_GLOSSAIRE: dict[str, str] = {
    "DIAG": "DIAG — Diagnostic",
    "ESQ": "ESQ — Esquisse",
    "APS": "APS — Avant-Projet Sommaire",
    "APD": "APD — Avant-Projet Définitif",
    "AUTORISATIONS": "Autorisations administratives",
    "PRO": "PRO — Études de projet",
    "DCE": "DCE — Dossier de Consultation des Entreprises",
    "ACT": "ACT — Assistance aux Contrats de Travaux",
    "VISA": "VISA — Visa des études d'exécution (période de préparation)",
    "DET": "DET — Direction de l'Exécution des Travaux",
    "AOR": "AOR — Assistance aux Opérations de Réception",
}

DEFINITION_FINANCEMENT = (
    "Montage et dépôt des dossiers de subvention (DETR, DSIL, Fonds vert, CEE…) jusqu'à l'accusé de dossier complet. "
    "Les marchés de travaux ne doivent pas être signés avant : la signature vaut commencement d'exécution."
)
DEFINITION_GPA = "Garantie de parfait achèvement : un an à compter de la réception, pendant lequel les entreprises reprennent les désordres signalés."
# Phase à l'issue de laquelle démarre, par défaut, le montage des dossiers de subvention
# (le coût prévisionnel des travaux est alors connu).
FINANCEMENT_APRES_DEFAUT = "APD"


# --------------------------------------------------------------------------
# Autorisations d'urbanisme et délais d'instruction réglementaires


class TypeAutorisation(str, Enum):
    AUCUNE = "Aucune autorisation d'urbanisme"
    DP = "Déclaration préalable (DP)"
    PC = "Permis de construire (PC)"
    AT_ERP = "Autorisation de travaux ERP (sans permis)"
    PC_ERP = "Permis de construire d'un ERP"


# Délais de droit commun, en mois calendaires.
MOIS_INSTRUCTION: dict[TypeAutorisation, int] = {
    TypeAutorisation.AUCUNE: 0,
    TypeAutorisation.DP: 1,  # C. urb. R423-23 a)
    TypeAutorisation.PC: 3,  # C. urb. R423-23 c) (hors maison individuelle)
    TypeAutorisation.AT_ERP: 4,  # CCH, autorisation de travaux au titre des ERP
    TypeAutorisation.PC_ERP: 5,  # C. urb. R423-28 (PC valant autorisation ERP)
}
ARTICLES_INSTRUCTION: dict[TypeAutorisation, str] = {
    TypeAutorisation.DP: "art. R423-23 du code de l'urbanisme",
    TypeAutorisation.PC: "art. R423-23 du code de l'urbanisme",
    TypeAutorisation.AT_ERP: "code de la construction et de l'habitation",
    TypeAutorisation.PC_ERP: "art. R423-28 du code de l'urbanisme",
}
# Majoration d'un mois lorsque l'avis de l'Architecte des Bâtiments de France est requis
# (abords de monument historique, site patrimonial remarquable) : C. urb. R423-24.
MAJORATION_ABF_MOIS = 1
TYPES_MAJORES_ABF = (TypeAutorisation.DP, TypeAutorisation.PC)
# Recours des tiers : deux mois à compter de l'affichage continu sur le terrain (C. urb. R600-2).
MOIS_RECOURS_TIERS = 2


@dataclass(frozen=True)
class Autorisation:
    type: TypeAutorisation = TypeAutorisation.DP
    abf: bool = False
    purge_recours: bool = False

    @property
    def requise(self) -> bool:
        return self.type is not TypeAutorisation.AUCUNE

    @property
    def mois_instruction(self) -> int:
        majoration = MAJORATION_ABF_MOIS if self.abf and self.type in TYPES_MAJORES_ABF else 0
        return MOIS_INSTRUCTION[self.type] + majoration

    @property
    def sigle(self) -> str:
        return {
            TypeAutorisation.DP: "DP",
            TypeAutorisation.PC: "PC",
            TypeAutorisation.AT_ERP: "AT ERP",
            TypeAutorisation.PC_ERP: "PC ERP",
        }.get(self.type, "")


# --------------------------------------------------------------------------
# Trêve de fin d'année : période non travaillée, se terminant le 1er janvier inclus.

TREVE_SEMAINES_DEFAUT = 2


# --------------------------------------------------------------------------
# Bâtiments scolaires : fenêtre de travaux pendant les vacances d'été


class FenetreTravaux(str, Enum):
    AUCUNE = "Pas de contrainte (travaux en site occupé)"
    DEBUT_ETE = "Démarrer les travaux au début des vacances d'été"
    ETE_UNIQUEMENT = "Travaux uniquement pendant les vacances d'été (sur plusieurs étés si nécessaire)"


# Les dates des vacances d'été sont dans territoires.py (calendrier national et dates personnalisées).
# Un chantier peut encore démarrer s'il reste au moins ce nombre de jours de vacances.
ETE_DEMARRAGE_TARDIF_JOURS = 14


# --------------------------------------------------------------------------
# Catalogue des phases

_ETUDES_SANS_AUDIT = [
    Phase("PROG_INIT", "Rédaction du programme (si pas d'audit préalable)", Groupe.ETUDES, 3),
    Phase("AUDIT", "Consultation du bureau d'études, diagnostics et audit énergétique", Groupe.ETUDES, 20),
    Phase("RESTITUTION", "Restitution de l'audit énergétique", Groupe.ETUDES, 2),
]
_ETUDES_AUDIT_RECU = [
    Phase("ANALYSE_CR", "Analyse des comptes rendus d'audits", Groupe.ETUDES, 2),
]
_ETUDES_COMMUNES = [
    Phase(
        "DECISION_ELUS",
        "Prise de décision des élus",
        Groupe.ETUDES,
        0,
        delai_mo=6,
        duree_min=0,
        modifiable=False,
        icone="🏛️",
        jalon_fin="Décision des élus",
    ),
    Phase(
        "PROGRAMME",
        "Rédaction du programme de travaux et validation",
        Groupe.ETUDES,
        4,
        delai_mo=2,
        jalon_fin="Programme validé",
    ),
]
_AMO = [
    Phase("AMO_CHOIX", "Choix de l'AMO Programmiste", Groupe.AMO, 6, icone="🧠"),
    Phase("AMO_MISSION", "Déroulement de la mission AMO et analyse des CR", Groupe.AMO, 8, delai_mo=2, icone="🧠"),
]
_SELECTION_MOE = [
    Phase("MOE_CCTP", "Rédaction des cahiers des charges et lancement du marché", Groupe.SELECTION_MOE, 8),
    Phase("MOE_ANALYSE", "Publication, analyse du marché et sélection de la MOE", Groupe.SELECTION_MOE, 8),
    Phase("CAO", "Commission d'appel d'offres", Groupe.SELECTION_MOE, 2, icone="⚖️"),
    Phase(
        "SIGNATURE_MOE", "Signature des marchés de MOE", Groupe.SELECTION_MOE, 3, icone="✍️", jalon_fin="MOE recrutée"
    ),
]
_MOE = [
    Phase(
        "CT_CSPS",
        "Recrutement du contrôleur technique et du CSPS",
        Groupe.MOE,
        8,
        icone="🦺",
        parallele=True,
    ),
    Phase("DIAG", "DIAG - Diagnostic", Groupe.MOE, 6, delai_mo=2),
    Phase("ESQ", "ESQ - Esquisse", Groupe.MOE, 0, duree_min=0, modifiable=False, afficher_gantt=False),
    Phase("APS", "APS - Avant-Projet Sommaire", Groupe.MOE, 4, delai_mo=2, duree_min=3),
    Phase("APD", "APD - Avant-Projet Définitif", Groupe.MOE, 8, delai_mo=5, duree_min=6, jalon_fin="APD validé"),
    Phase(
        "AUTORISATIONS",
        "Constitution du dossier d'autorisation",
        Groupe.MOE,
        2,
        delai_mo=2,
        jalon_fin="Dépôt du dossier",
        debut_instruction=True,
        prerequis=("CT_CSPS",),
    ),
    Phase("PRO", "PRO - Études de Projet", Groupe.MOE, 5, delai_mo=3, duree_min=4),
    Phase("DCE", "DCE - Dossier de Consultation des Entreprises", Groupe.MOE, 4, delai_mo=2),
    Phase(
        "ACT",
        "ACT - Consultation des entreprises et passation des marchés",
        Groupe.MOE,
        10,
        delai_mo=2,
        jalon_fin="Marchés de travaux signés",
        prerequis_signature=("FINANCEMENT",),
    ),
    Phase(
        "VISA",
        "VISA - Période de préparation du chantier",
        Groupe.MOE,
        6,
        icone="🛠️",
        prerequis=("AUTORISATION",),
    ),
    Phase(
        "DET",
        "DET - Direction de l'exécution des travaux",
        Groupe.MOE,
        24,
        icone="🚧",
        jalon_fin="Réception des travaux",
    ),
    Phase("AOR", "AOR - Assistance aux opérations de réception", Groupe.MOE, 4, icone="👷"),
]


def phases_pour_etat(etat: EtatProjet) -> list[Phase]:
    """Renvoie la séquence de phases restant à réaliser pour un état donné."""
    etat = EtatProjet(etat)
    phases: list[Phase] = []

    if etat is EtatProjet.SANS_AUDIT:
        phases += _ETUDES_SANS_AUDIT + _ETUDES_COMMUNES
    elif etat is EtatProjet.AUDIT_RECU:
        phases += _ETUDES_AUDIT_RECU + _ETUDES_COMMUNES

    if etat in (EtatProjet.AUDIT_RECU, EtatProjet.AMO_PROGRAMMISTE):
        phases += _AMO

    if etat is not EtatProjet.MOE_SELECTIONNEE:
        phases += _SELECTION_MOE

    phases += _MOE
    return list(phases)


def definition_courte(phase: Phase) -> str:
    return GLOSSAIRE_COURT.get(phase.id, "")
