"""Budget de l'opération, plan de financement et échéancier budgétaire.

Les taux et forfaits par défaut sont des ordres de grandeur pour une rénovation énergétique
de bâtiment public ; ils sont tous modifiables dans l'interface.
"""

from __future__ import annotations

import io
import math
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import Enum
from functools import cached_property

import pandas as pd

from .excel import finaliser_classeur
from .planning import TYPE_DELAI_MO, TYPE_PHASE, Planning


class Mode(str, Enum):
    POURCENT = "% des travaux"
    FORFAIT = "Forfait (€ HT)"


@dataclass(frozen=True)
class Poste:
    """Poste de dépense de l'opération, hors travaux."""

    id: str
    libelle: str
    mode: Mode
    valeur: float
    # Taux de TVA applicable (l'assurance dommages-ouvrage n'est pas soumise à la TVA).
    tva: float = 0.20
    aide: str = ""


POSTES: list[Poste] = [
    Poste(
        "ETUDES",
        "Études préalables (audit énergétique, diagnostics, relevés)",
        Mode.FORFAIT,
        15_000,
        aide="Audit, repérages amiante et plomb, relevés de géomètre…",
    ),
    Poste("AMO", "Assistance à maîtrise d'ouvrage (programmiste)", Mode.FORFAIT, 20_000),
    Poste(
        "MOE",
        "Maîtrise d'œuvre (mission de base)",
        Mode.POURCENT,
        11.0,
        aide="Souvent entre 8 et 14 % du montant des travaux en réhabilitation.",
    ),
    Poste("CT", "Contrôleur technique", Mode.POURCENT, 1.0),
    Poste("CSPS", "Coordonnateur sécurité et protection de la santé (CSPS)", Mode.POURCENT, 0.8),
    Poste(
        "DO",
        "Assurance dommages-ouvrage",
        Mode.POURCENT,
        1.2,
        tva=0.0,
        aide="Prime soumise à la taxe sur les assurances, sans TVA.",
    ),
    Poste("DIVERS", "Frais divers (publicité, reprographie, raccordements)", Mode.POURCENT, 1.0),
    Poste("ALEAS", "Aléas et imprévus", Mode.POURCENT, 7.0, aide="5 à 10 % selon la connaissance du bâti."),
    Poste("REVISION", "Actualisation et révision des prix", Mode.POURCENT, 3.0),
]
POSTES_PAR_ID = {p.id: p for p in POSTES}
TVA_TRAVAUX = 0.20

# Répartition indicative des honoraires de maîtrise d'œuvre entre les éléments de mission (en %).
REPARTITION_MOE = {
    "DIAG": 6,
    "APS": 10,
    "APD": 15,
    "PRO": 15,
    "DCE": 6,
    "ACT": 6,
    "VISA": 6,
    "DET": 30,
    "AOR": 6,
}

# Postes réglés aux entreprises de travaux (avance et retenue de garantie s'y appliquent).
POSTES_MARCHES_TRAVAUX = ("TRAVAUX", "ALEAS", "REVISION")
# Délai global de paiement des collectivités : 30 jours (code de la commande publique, art. R2192-10).
DELAI_PAIEMENT_JOURS = 30

# Fonds de compensation de la TVA : taux en vigueur depuis 2015, à vérifier selon la loi de finances.
TAUX_FCTVA_DEFAUT = 16.404
# Plafond des aides publiques : le maître d'ouvrage apporte au moins 20 % (CGCT, art. L1111-10).
PLAFOND_AIDES_PUBLIQUES = 80.0


class RegimeFCTVA(str, Enum):
    N = "L'année de la dépense (N)"
    N1 = "L'année suivante (N+1)"
    N2 = "Deux ans après (N+2)"

    @property
    def decalage(self) -> int:
        return {"N": 0, "N1": 1, "N2": 2}[self.name]


class StatutAide(str, Enum):
    A_SOLLICITER = "À solliciter"
    DEPOSEE = "Dossier déposé"
    NOTIFIEE = "Notifiée"


@dataclass(frozen=True)
class Financeur:
    nom: str
    taux: float = 0.0  # % du coût HT de l'opération (ignoré si un montant est saisi)
    montant: float = 0.0  # € ; prioritaire sur le taux
    public: bool = True
    statut: StatutAide = StatutAide.A_SOLLICITER

    def aide(self, base_ht: float) -> float:
        return self.montant if self.montant else base_ht * self.taux / 100


FINANCEURS_DEFAUT = [
    Financeur("DETR (État)"),
    Financeur("DSIL (État)"),
    Financeur("Fonds vert (État)"),
    Financeur("Région"),
    Financeur("Département"),
    Financeur("Certificats d'économies d'énergie (CEE)", public=False),
]


def nommer_collectivites(financeurs: list[Financeur], region: str = "", departement: str = "") -> list[Financeur]:
    """Précise la Région et le Département dans les lignes génériques du plan de financement.

    Seules les lignes « Région » / « Département » et celles déjà nommées automatiquement sont renommées :
    un libellé saisi par l'utilisateur est conservé."""

    def automatique(nom: str, prefixe: str) -> bool:
        return nom == prefixe or nom.startswith(f"{prefixe} : ")

    resultat = []
    for f in financeurs:
        if region and automatique(f.nom, "Région"):
            f = replace(f, nom=f"Région : {region}")
        elif departement and automatique(f.nom, "Département"):
            f = replace(f, nom=f"Département : {departement}")
        resultat.append(f)
    return resultat


def postes_par_defaut(ids_phases: set[str]) -> dict[str, float]:
    """Valeurs par défaut des postes, en écartant ceux dont la phase n'est pas au planning."""
    valeurs = {p.id: p.valeur for p in POSTES}
    if not ids_phases & {"AUDIT", "ANALYSE_CR", "PROG_INIT"}:
        valeurs["ETUDES"] = 0
    if "AMO_MISSION" not in ids_phases:
        valeurs["AMO"] = 0
    return valeurs


@dataclass(frozen=True)
class Budget:
    """Hypothèses budgétaires (immuables : utiliser dataclasses.replace pour en dériver une variante)."""

    travaux_ht: float = 0.0
    postes: dict[str, float] = field(default_factory=dict)
    financeurs: list[Financeur] = field(default_factory=lambda: list(FINANCEURS_DEFAUT))
    taux_fctva: float = TAUX_FCTVA_DEFAUT
    regime_fctva: RegimeFCTVA = RegimeFCTVA.N1
    # Versement des aides : avance au démarrage des travaux, solde après la réception, et entre les deux des
    # acomptes au fil des dépenses justifiées.
    acompte_aides: float = 30.0
    mois_solde_apres_reception: int = 3
    solde_aides: float = 20.0
    # Paiement des entreprises et prestataires.
    delai_paiement_jours: int = DELAI_PAIEMENT_JOURS
    avance_entreprises: float = 5.0  # % des marchés de travaux versé au démarrage, puis récupéré
    retenue_garantie: float = 5.0  # % des marchés de travaux retenu jusqu'à la fin de la GPA

    # ------------------------------------------------------------------ coûts

    @cached_property
    def _couts(self) -> pd.DataFrame:
        # Calculé une seule fois par budget : l'interface interroge les totaux de nombreuses fois.
        lignes = [_cout("TRAVAUX", "Travaux", self.travaux_ht, TVA_TRAVAUX)]
        for poste in POSTES:
            valeur = self.postes.get(poste.id, poste.valeur)
            ht = self.travaux_ht * valeur / 100 if poste.mode is Mode.POURCENT else valeur
            lignes.append(_cout(poste.id, poste.libelle, ht, poste.tva))
        return pd.DataFrame(lignes)

    def couts(self) -> pd.DataFrame:
        return self._couts.copy()

    @cached_property
    def total_ht(self) -> float:
        return float(self._couts["HT"].sum())

    @cached_property
    def total_ttc(self) -> float:
        return float(self._couts["TTC"].sum())

    @cached_property
    def total_tva(self) -> float:
        return float(self._couts["TVA"].sum())

    # ------------------------------------------------------- financement

    def plan_financement(self) -> pd.DataFrame:
        base = self.total_ht
        return pd.DataFrame(
            [
                {
                    "Financeur": f.nom,
                    "Public": f.public,
                    "Statut": f.statut.value,
                    "Montant": round(f.aide(base), 2),
                    "Part du coût HT (%)": round(100 * f.aide(base) / base, 1) if base else 0.0,
                }
                for f in self.financeurs
            ]
        )

    @property
    def aides_publiques(self) -> float:
        return sum(f.aide(self.total_ht) for f in self.financeurs if f.public)

    @property
    def aides_privees(self) -> float:
        return sum(f.aide(self.total_ht) for f in self.financeurs if not f.public)

    @property
    def aides(self) -> float:
        return self.aides_publiques + self.aides_privees

    @property
    def taux_aides_publiques(self) -> float:
        return 100 * self.aides_publiques / self.total_ht if self.total_ht else 0.0

    @property
    def depasse_plafond(self) -> bool:
        return self.taux_aides_publiques > PLAFOND_AIDES_PUBLIQUES + 1e-9

    @property
    def fctva(self) -> float:
        """FCTVA attendu sur les dépenses TTC (assiette simplifiée : toutes les dépenses soumises à TVA)."""
        couts = self._couts
        return float(couts.loc[couts["TVA"] > 0, "TTC"].sum()) * self.taux_fctva / 100

    @property
    def reste_a_charge(self) -> float:
        """Coût net pour la collectivité, une fois les aides et le FCTVA perçus."""
        return self.total_ttc - self.aides - self.fctva

    # -------------------------------------------------- échéancier par année

    def echeancier(self, planning: Planning) -> pd.DataFrame:
        """Dépenses TTC, aides, FCTVA et solde par année budgétaire, calés sur le planning.

        Les factures sont payées ``delai_paiement_jours`` après le service fait. Pour les marchés de travaux :
        avance versée au démarrage puis récupérée sur les paiements suivants, retenue de garantie libérée à la
        fin de la garantie de parfait achèvement. Aides : avance au démarrage des travaux, acomptes au prorata
        des dépenses de chaque année, solde après la réception.
        """
        decalage = timedelta(days=self.delai_paiement_jours)
        debut_travaux, reception = _debut_travaux_et_reception(planning)
        depenses: dict[int, float] = defaultdict(float)
        eligibles: dict[int, float] = defaultdict(float)

        def payer(annee: int, montant: float, soumis_tva: bool) -> None:
            depenses[annee] += montant
            if soumis_tva:
                eligibles[annee] += montant

        for ligne in self._couts.itertuples():
            montant, soumis_tva = ligne.TTC, ligne.TVA > 0
            if ligne.Id in POSTES_MARCHES_TRAVAUX:
                avance = montant * self.avance_entreprises / 100
                retenue = montant * self.retenue_garantie / 100
                payer((debut_travaux + decalage).year, avance, soumis_tva)
                payer((_ajouter_mois(reception, 12) + decalage).year, retenue, soumis_tva)
                montant -= avance + retenue
            periodes = [(d + decalage, f + decalage, p) for d, f, p in fenetres(planning, ligne.Id)]
            for annee, part in _repartir(montant, periodes).items():
                payer(annee, part, soumis_tva)

        acompte = min(self.acompte_aides, 100.0) / 100
        solde = min(self.solde_aides, 100.0 - 100 * acompte) / 100
        recettes_aides: dict[int, float] = defaultdict(float)
        recettes_aides[debut_travaux.year] += self.aides * acompte
        recettes_aides[_ajouter_mois(reception, self.mois_solde_apres_reception).year] += self.aides * solde
        # Les acomptes ne sont versés qu'une fois l'aide attribuée, sur les dépenses à partir du démarrage des
        # travaux (les études antérieures sont couvertes par l'avance et le solde).
        assiette = {a: m for a, m in depenses.items() if a >= debut_travaux.year}
        total_assiette = sum(assiette.values())
        acomptes = self.aides * (1 - acompte - solde)
        if total_assiette > 0:
            for annee, montant in assiette.items():
                recettes_aides[annee] += acomptes * montant / total_assiette
        else:
            # Aucune dépense après le démarrage des travaux : la part des acomptes est versée avec le solde.
            recettes_aides[_ajouter_mois(reception, self.mois_solde_apres_reception).year] += acomptes

        fctva: dict[int, float] = defaultdict(float)
        for annee, montant in eligibles.items():
            fctva[annee + self.regime_fctva.decalage] += montant * self.taux_fctva / 100

        annees = sorted(set(depenses) | set(recettes_aides) | set(fctva))
        if not annees:
            return pd.DataFrame(columns=["Année", "Dépenses TTC", "Aides", "FCTVA", "Solde", "Cumul"])
        annees = list(range(annees[0], annees[-1] + 1))
        df = pd.DataFrame(
            {
                "Année": annees,
                "Dépenses TTC": [round(depenses[a], 2) for a in annees],
                "Aides": [round(recettes_aides[a], 2) for a in annees],
                "FCTVA": [round(fctva[a], 2) for a in annees],
            }
        )
        df["Solde"] = df["Aides"] + df["FCTVA"] - df["Dépenses TTC"]
        df["Cumul"] = df["Solde"].cumsum()
        return df

    # ------------------------------------------------------------ JSON

    def vers_dict(self) -> dict:
        return {
            "travaux_ht": self.travaux_ht,
            "postes": self.postes,
            "financeurs": [
                {"nom": f.nom, "taux": f.taux, "montant": f.montant, "public": f.public, "statut": f.statut.name}
                for f in self.financeurs
            ],
            "taux_fctva": self.taux_fctva,
            "regime_fctva": self.regime_fctva.name,
            "acompte_aides": self.acompte_aides,
            "mois_solde_apres_reception": self.mois_solde_apres_reception,
            "solde_aides": self.solde_aides,
            "delai_paiement_jours": self.delai_paiement_jours,
            "avance_entreprises": self.avance_entreprises,
            "retenue_garantie": self.retenue_garantie,
        }

    @classmethod
    def depuis_dict(cls, donnees: dict) -> Budget:
        return cls(
            travaux_ht=float(donnees.get("travaux_ht", 0)),
            postes={k: float(v) for k, v in (donnees.get("postes") or {}).items()},
            financeurs=[
                Financeur(
                    str(f["nom"]),
                    _nombre_borne(f.get("taux", 0), 0.0, 100.0),
                    _nombre_borne(f.get("montant", 0), 0.0, float("inf")),
                    bool(f.get("public", True)),
                    StatutAide[f.get("statut", "A_SOLLICITER")],
                )
                for f in donnees.get("financeurs", [])
            ]
            if "financeurs" in donnees
            else list(FINANCEURS_DEFAUT),
            taux_fctva=float(donnees.get("taux_fctva", TAUX_FCTVA_DEFAUT)),
            regime_fctva=RegimeFCTVA[donnees.get("regime_fctva", "N1")],
            acompte_aides=float(donnees.get("acompte_aides", 30)),
            mois_solde_apres_reception=int(donnees.get("mois_solde_apres_reception", 3)),
            solde_aides=_nombre_borne(donnees.get("solde_aides", 20), 0.0, 100.0),
            delai_paiement_jours=int(_nombre_borne(donnees.get("delai_paiement_jours", DELAI_PAIEMENT_JOURS), 0, 120)),
            avance_entreprises=_nombre_borne(donnees.get("avance_entreprises", 5), 0.0, 30.0),
            retenue_garantie=_nombre_borne(donnees.get("retenue_garantie", 5), 0.0, 5.0),
        )


# --------------------------------------------------------------------------
# Calage dans le temps


def fenetres(planning: Planning, id_cout: str) -> list[tuple[date, date, float]]:
    """Périodes (début, fin, poids) pendant lesquelles un poste est dépensé."""
    t = planning.taches[planning.taches["Type"].isin([TYPE_PHASE, TYPE_DELAI_MO])]

    def periodes(ids: list[str], seulement_phases: bool = False, poids: float = 1.0) -> list[tuple[date, date, float]]:
        """Lignes du planning pour ces identifiants ; le poids est réparti au prorata de leur durée."""
        sous = t[t["Id"].isin(ids)]
        if seulement_phases:
            sous = sous[sous["Type"] == TYPE_PHASE]
        durees = [max((r.Fin - r.Debut).days, 1) for r in sous.itertuples()]
        total = sum(durees)
        return [(r.Debut, r.Fin, poids * d / total) for r, d in zip(sous.itertuples(), durees, strict=True)]

    tout = [(planning.date_debut, planning.date_fin, 1.0)]
    if id_cout in ("TRAVAUX", "ALEAS", "REVISION"):
        return periodes(["DET"], seulement_phases=True) or tout
    if id_cout == "ETUDES":
        return periodes(["PROG_INIT", "AUDIT", "RESTITUTION", "ANALYSE_CR"], True) or [
            (planning.date_debut, planning.date_debut, 1.0)
        ]
    if id_cout == "AMO":
        return periodes(["AMO_MISSION"], True) or periodes(["AMO_CHOIX"], True) or tout
    if id_cout == "DIVERS":
        return periodes(["ACT"], True) or tout
    if id_cout == "DO":
        debut, _ = _debut_travaux_et_reception(planning)
        return [(debut, debut, 1.0)]
    if id_cout in ("CT", "CSPS"):
        debut = t.loc[t["Id"] == "APS", "Debut"].min() if (t["Id"] == "APS").any() else planning.date_debut
        fin = t.loc[t["Id"] == "AOR", "Fin"].max() if (t["Id"] == "AOR").any() else planning.date_fin
        return [(debut, fin, 1.0)]
    if id_cout == "MOE":
        resultat = []
        for element, poids in REPARTITION_MOE.items():
            resultat += periodes([element], True, float(poids))
        return resultat or tout
    return tout


def _repartir(montant: float, periodes: list[tuple[date, date, float]]) -> dict[int, float]:
    """Répartit un montant sur des périodes, au prorata des poids puis des jours, par année civile."""
    resultat: dict[int, float] = defaultdict(float)
    if not montant or not periodes:
        return resultat
    total_poids = sum(p for _, _, p in periodes)
    for debut, fin, poids in periodes:
        part = montant * poids / total_poids
        jours = (fin - debut).days
        if jours <= 0:
            resultat[debut.year] += part
            continue
        jour = debut
        while jour < fin:
            fin_annee = min(fin, date(jour.year + 1, 1, 1))
            resultat[jour.year] += part * (fin_annee - jour).days / jours
            jour = fin_annee
    return resultat


def _debut_travaux_et_reception(planning: Planning) -> tuple[date, date]:
    t = planning.taches
    travaux = t[(t["Id"] == "DET") & (t["Type"] == TYPE_PHASE)]
    if travaux.empty:
        return planning.date_fin, planning.date_fin
    return travaux["Debut"].min(), travaux["Fin"].max()


def _ajouter_mois(jour: date, mois: int) -> date:
    return (pd.Timestamp(jour) + pd.DateOffset(months=mois)).date()


def _nombre_borne(valeur, mini: float, maxi: float) -> float:
    """Convertit une valeur lue dans un fichier en nombre compris entre mini et maxi (0 si illisible)."""
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return mini
    return mini if math.isnan(nombre) else min(max(nombre, mini), maxi)


def _cout(id_: str, libelle: str, ht: float, tva: float) -> dict:
    return {"Id": id_, "Poste": libelle, "HT": round(ht, 2), "TVA": round(ht * tva, 2), "TTC": round(ht * (1 + tva), 2)}


# --------------------------------------------------------------------------
# Export


def budget_vers_excel(budget: Budget, planning: Planning) -> bytes:
    tampon = io.BytesIO()
    synthese = pd.DataFrame(
        [
            ("Coût de l'opération HT", budget.total_ht),
            ("TVA", budget.total_tva),
            ("Coût de l'opération TTC", budget.total_ttc),
            ("Aides publiques", budget.aides_publiques),
            ("Aides privées (CEE…)", budget.aides_privees),
            ("Taux d'aides publiques (% du HT)", round(budget.taux_aides_publiques, 1)),
            ("FCTVA attendu", round(budget.fctva, 2)),
            ("Reste à charge net", round(budget.reste_a_charge, 2)),
        ],
        columns=["Indicateur", "Valeur"],
    )
    with pd.ExcelWriter(tampon, engine="openpyxl") as writer:
        synthese.to_excel(writer, sheet_name="Synthèse", index=False)
        budget.couts().drop(columns=["Id"]).to_excel(writer, sheet_name="Coût de l'opération", index=False)
        budget.plan_financement().to_excel(writer, sheet_name="Plan de financement", index=False)
        budget.echeancier(planning).to_excel(writer, sheet_name="Échéancier", index=False)
        finaliser_classeur(writer, largeur_max=70)
    return tampon.getvalue()
