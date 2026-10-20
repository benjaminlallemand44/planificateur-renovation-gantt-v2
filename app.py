"""Interface Streamlit du planificateur de projet de rénovation.

Lancement : ``streamlit run app.py``
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _recharger_le_package_si_modifie() -> None:
    """Recharge le package ``renovation_gantt`` quand ses fichiers ont changé.

    Streamlit réexécute ``app.py`` à chaque mise à jour du dépôt, mais garde en mémoire les modules déjà importés :
    sans ce rechargement, l'application mélange l'ancien et le nouveau code après une mise à jour sur Streamlit
    Cloud (erreurs du type « unexpected keyword argument »). La session est alors réinitialisée, comme après un
    redémarrage, car elle peut contenir des objets créés par l'ancien code.
    """
    package = sys.modules.get("renovation_gantt")
    if package is None:
        return
    dossier = Path(__file__).parent / "renovation_gantt"
    # Même calcul que renovation_gantt.empreinte_sources, refait ici sans passer par le module en mémoire.
    actuelle = hashlib.sha1(b"".join(f.read_bytes() for f in sorted(dossier.glob("*.py")))).hexdigest()
    if getattr(package, "_empreinte", None) != actuelle:
        for nom in [n for n in sys.modules if n == "renovation_gantt" or n.startswith("renovation_gantt.")]:
            del sys.modules[nom]
        st.session_state.clear()


_recharger_le_package_si_modifie()

from renovation_gantt import __version__
from renovation_gantt.budget import (
    DELAI_PAIEMENT_JOURS,
    PLAFOND_AIDES_PUBLIQUES,
    POSTES,
    TAUX_FCTVA_DEFAUT,
    Budget,
    Financeur,
    Mode,
    RegimeFCTVA,
    StatutAide,
    budget_vers_excel,
    nommer_collectivites,
    postes_par_defaut,
)
from renovation_gantt.charts import figure_gantt
from renovation_gantt.export import Scenario, planning_vers_csv, planning_vers_excel, planning_vers_ics
from renovation_gantt.pdf import planning_vers_pdf
from renovation_gantt.phases import (
    ARTICLES_INSTRUCTION,
    FINANCEMENT_APRES_DEFAUT,
    GLOSSAIRE_COMPLET,
    LIBELLES_GLOSSAIRE,
    TREVE_SEMAINES_DEFAUT,
    TYPES_MAJORES_ABF,
    Autorisation,
    EtatProjet,
    FenetreTravaux,
    Groupe,
    TypeAutorisation,
    definition_courte,
    phases_pour_etat,
)
from renovation_gantt.saisie import borner
from renovation_gantt.territoires import DEPARTEMENTS, REGIONS, CalendrierEte, Departement, departements_de

RACINE = Path(__file__).parent
LOGO = RACINE / "images" / "Logo_ACTEE_CMYN-HD.png"
ICONES_GROUPES = {Groupe.ETUDES: "📋", Groupe.AMO: "🧠", Groupe.SELECTION_MOE: "🧑‍💼", Groupe.MOE: "🏗️"}

st.set_page_config(page_title="Planificateur rénovation", page_icon="📊", layout="wide")

# Smartphone : détecté par le navigateur déclaré (« Mobi » : iPhone, Android…). Sert à compacter le Gantt et à
# replier les réglages pour que le diagramme ne soit pas relégué tout en bas de la page.
SMARTPHONE = "Mobi" in (st.context.headers.get("User-Agent") or "")

# Petits écrans : titre et indicateurs moins imposants.
st.html(
    """
<style>
@media (max-width: 640px) {
  h1 { font-size: 1.6rem !important; }
  [data-testid="stMetricValue"] { font-size: 1.6rem; }
}
</style>
"""
)


def _defaut(cle: str, valeur) -> str:
    """Initialise une valeur de widget une seule fois (évite les conflits avec un scénario chargé)."""
    st.session_state.setdefault(cle, valeur)
    return cle


# --------------------------------------------------------------------------
# Chargement d'un scénario : on alimente st.session_state avant de créer les widgets.


# Bornes des champs de saisie. Un scénario chargé est ramené dans ces bornes : sinon Streamlit remplacerait
# silencieusement toute valeur hors bornes par le minimum (200 semaines de travaux deviendraient 1 semaine).
DUREE_MAX = 156
DELAI_MO_MAX = 52
FINANCEMENT_MAX = 104
TREVE_MAX = 4
TAUX_FCTVA_MAX = 30.0


def _borner(cle: str, valeur, mini, maxi, libelle: str, ajustements: list[str]) -> None:
    """Place dans la session une valeur ramenée dans [mini, maxi] et note l'ajustement éventuel."""
    corrige, ajuste = borner(valeur, mini, maxi)
    if ajuste:
        ajustements.append(f"{libelle} : {valeur} → {corrige}")
    st.session_state[cle] = corrige


def _charger_scenario() -> None:
    fichier = st.session_state.get("fichier_scenario")
    if fichier is None:
        return
    try:
        scenario = Scenario.depuis_json(fichier.getvalue())
    except ValueError as exc:
        st.session_state["erreur_scenario"] = str(exc)
        return
    _appliquer_scenario(scenario)
    st.session_state["scenario_charge"] = fichier.name


def _appliquer_scenario(scenario: Scenario) -> None:
    """Place les paramètres d'un scénario dans la session, avant la création des widgets."""
    st.session_state["etat"] = scenario.etat
    st.session_state["date_debut"] = scenario.date_debut
    st.session_state["nom_projet"] = scenario.nom_projet
    st.session_state["region"] = scenario.region or None
    st.session_state["departement"] = scenario.departement or None
    st.session_state["ete_personnalise_on"] = scenario.ete_personnalise is not None
    if scenario.ete_personnalise:
        (m1, j1), (m2, j2) = scenario.ete_personnalise
        st.session_state["ete_debut"] = date(2000, m1, j1)
        st.session_state["ete_rentree"] = date(2000, m2, j2)
    ajustements: list[str] = []
    budget = scenario.budget
    _borner("travaux_ht", budget.travaux_ht, 0, 10**10, "Montant des travaux", ajustements)
    for id_poste, valeur in budget.postes.items():
        _borner(f"poste_{id_poste}", valeur, 0.0, 10.0**9, f"Poste {id_poste}", ajustements)
    _borner("taux_fctva", budget.taux_fctva, 0.0, TAUX_FCTVA_MAX, "Taux du FCTVA", ajustements)
    st.session_state["regime_fctva"] = budget.regime_fctva
    _borner("acompte_aides", budget.acompte_aides, 0.0, 100.0, "Avance des aides", ajustements)
    _borner("solde_aides", budget.solde_aides, 0.0, 100.0, "Solde des aides", ajustements)
    _borner("delai_paiement_jours", budget.delai_paiement_jours, 0, 120, "Délai de paiement", ajustements)
    _borner("avance_entreprises", budget.avance_entreprises, 0.0, 30.0, "Avance aux entreprises", ajustements)
    _borner("retenue_garantie", budget.retenue_garantie, 0.0, 5.0, "Retenue de garantie", ajustements)
    st.session_state["financeurs"] = budget.financeurs
    st.session_state["financeurs_base"] = budget.financeurs
    st.session_state.pop("editeur_financeurs", None)
    st.session_state["financement_on"] = bool(scenario.financement_semaines)
    if scenario.financement_semaines:
        _borner(
            "financement_semaines",
            scenario.financement_semaines,
            1,
            FINANCEMENT_MAX,
            "Durée des dossiers de financement",
            ajustements,
        )
    st.session_state["financement_apres"] = scenario.financement_apres
    for phase in scenario.phases():
        _borner(f"duree_{phase.id}", phase.duree, phase.duree_min, DUREE_MAX, f"Durée « {phase.nom} »", ajustements)
        _borner(f"delai_{phase.id}", phase.delai_mo, 0, DELAI_MO_MAX, f"Délai MO « {phase.nom} »", ajustements)
    st.session_state["type_autorisation"] = scenario.autorisation.type
    st.session_state["abf"] = scenario.autorisation.abf
    st.session_state["purge_recours"] = scenario.autorisation.purge_recours
    _borner("treve_semaines", scenario.treve_semaines, 0, TREVE_MAX, "Trêve de fin d'année", ajustements)
    st.session_state["batiment_scolaire"] = scenario.batiment_scolaire
    if scenario.fenetre_travaux is not FenetreTravaux.AUCUNE:
        st.session_state["fenetre_travaux"] = scenario.fenetre_travaux
    st.session_state["afficher_delais"] = any(
        p.delai_mo != d.delai_mo for p, d in zip(scenario.phases(), phases_pour_etat(scenario.etat), strict=True)
    )
    st.session_state["erreur_scenario"] = None
    st.session_state["ajustements_scenario"] = ajustements


# --------------------------------------------------------------------------
# Sauvegarde automatique dans le navigateur (localStorage) : les saisies survivent à un rechargement de la page
# ou à une mise à jour de l'application, sur le même ordinateur et le même navigateur.

CLE_MEMOIRE = "planificateur-renovation-gantt:scenario"
_JS_MEMOIRE = """
export default function ({ data, setStateValue }) {
  const cle = data.cle;
  let stocke = null;
  try { stocke = window.localStorage.getItem(cle); } catch (e) { /* stockage indisponible (navigation privée…) */ }
  if (!data.pret) {
    // Première exécution de la session : on transmet la sauvegarde avant d'écrire quoi que ce soit.
    setStateValue("lu", { contenu: stocke, jeton: data.jeton });
    return;
  }
  try {
    // Pas encore de scénario (état du projet non choisi, ou « Nouveau projet ») : on efface la sauvegarde.
    if (data.json === null) window.localStorage.removeItem(cle);
    else if (data.json !== stocke) window.localStorage.setItem(cle, data.json);
  } catch (e) { /* quota dépassé ou stockage refusé : la sauvegarde manuelle (.json) reste possible */ }
}
"""
_memoire_navigateur = st.components.v2.component("memoire_navigateur", js=_JS_MEMOIRE)


def _restaurer_memoire() -> None:
    """Reçoit la sauvegarde lue dans le navigateur, avant la création des widgets."""
    lu = (st.session_state.get("memoire_navigateur") or {}).get("lu") or {}
    if lu.get("jeton") != st.session_state.get("jeton_memoire") or st.session_state.get("memoire_prete"):
        return
    st.session_state["memoire_prete"] = True
    if not lu.get("contenu"):
        return
    try:
        _appliquer_scenario(Scenario.depuis_json(lu["contenu"]))
    except ValueError:
        return  # sauvegarde illisible : on repart des valeurs par défaut
    st.session_state["memoire_restauree"] = True


def _nouveau_projet() -> None:
    """Efface toutes les saisies ; la sauvegarde du navigateur est remplacée par les valeurs par défaut."""
    garder = {"jeton_memoire", "memoire_prete", "memoire_navigateur"}
    for cle in [c for c in st.session_state if c not in garder]:
        del st.session_state[cle]


def _sauvegarder_dans_le_navigateur(json_scenario: str | None) -> None:
    """Monte le composant de sauvegarde : à appeler à chaque exécution, y compris avant un ``st.stop()``,
    sinon la sauvegarde ne serait jamais relue."""
    _memoire_navigateur(
        key="memoire_navigateur",
        data={
            "cle": CLE_MEMOIRE,
            "jeton": st.session_state.setdefault("jeton_memoire", uuid.uuid4().hex),
            "pret": bool(st.session_state.get("memoire_prete")),
            "json": json_scenario,
        },
        on_lu_change=_restaurer_memoire,
        height=0,
    )


def _saisir_vacances(departement: Departement | None) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Affiche les dates de vacances d'été retenues et permet de les ajuster ; renvoie les dates personnalisées."""
    annee = date.today().year + (1 if date.today().month > 8 else 0)
    debut, rentree = CalendrierEte().vacances(annee)
    if departement is None:
        lieu = "Choisissez le département pour vérifier le calendrier applicable."
    elif departement.calendrier_specifique:
        lieu = (
            f"⚠️ {departement.nom} a un calendrier scolaire propre (hors zones A, B, C) : "
            "saisissez ci-dessous les dates de vos grandes vacances."
        )
    else:
        lieu = (
            f"{departement.nom} est en zone {departement.zone} : les vacances d'été sont les mêmes "
            "dans les trois zones de métropole."
        )
    st.caption(
        f"Vacances d'été {annee} (calendrier national) : du {debut:%d/%m/%Y} à la rentrée du {rentree:%d/%m/%Y}. {lieu}"
    )
    personnalise = st.toggle(
        "Saisir d'autres dates de vacances",
        key=_defaut("ete_personnalise_on", bool(departement and departement.calendrier_specifique)),
        help="Utile pour la Corse, l'outre-mer (grandes vacances de décembre à janvier à La Réunion et à Mayotte) "
        "ou un calendrier local. Les dates s'appliquent chaque année.",
    )
    if not personnalise:
        return None
    col_d, col_f = st.columns(2)
    with col_d:
        jour_debut = st.date_input(
            "Début des vacances (jour et mois)",
            format="DD/MM/YYYY",
            key=_defaut("ete_debut", debut),
        )
    with col_f:
        jour_rentree = st.date_input(
            "Jour de la rentrée (jour et mois)",
            format="DD/MM/YYYY",
            key=_defaut("ete_rentree", rentree),
        )
    return (jour_debut.month, jour_debut.day), (jour_rentree.month, jour_rentree.day)


# --------------------------------------------------------------------------
# Barre latérale

with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), width="stretch")
    st.header("💾 Scénario")
    if st.session_state.pop("memoire_restauree", False):
        st.toast("Saisies de votre dernière visite restaurées.", icon="💾")
    st.caption(
        "Vos saisies sont enregistrées automatiquement dans ce navigateur. Pour les retrouver sur un autre poste "
        "ou les partager, téléchargez le scénario (.json)."
    )
    st.button("🗒️ Nouveau projet (tout effacer)", on_click=_nouveau_projet, width="stretch")
    st.file_uploader("Charger un scénario (.json)", type="json", key="fichier_scenario", on_change=_charger_scenario)
    if st.session_state.get("erreur_scenario"):
        st.error(st.session_state["erreur_scenario"])
    elif st.session_state.get("scenario_charge"):
        st.success(f"Scénario « {st.session_state['scenario_charge']} » chargé.")
        if st.session_state.get("ajustements_scenario"):
            st.warning(
                "Valeurs hors des limites de saisie, ramenées dans les bornes :\n\n"
                + "\n".join(f"- {a}" for a in st.session_state["ajustements_scenario"])
            )
    afficher_delais = st.toggle(
        "Modifier les délais de validation MO",
        key=_defaut("afficher_delais", False),
        help="Par défaut, les délais de validation du maître d'ouvrage sont fixés.",
    )
    st.caption(f"Version {__version__}")


# --------------------------------------------------------------------------
# En-tête

st.title("📊 Assistant planification du projet de rénovation")
st.markdown(
    "Indiquez où en est votre projet et sa **date de début**, puis ajustez les durées "
    "(en **semaines**). Le diagramme de Gantt se met à jour automatiquement."
)

col_nom, col_region, col_dep = st.columns([2, 1, 1])
with col_nom:
    nom_projet = st.text_input(
        "Nom du projet",
        key=_defaut("nom_projet", ""),
        placeholder="Ex. : Rénovation de l'école Jules Ferry",
    )
with col_region:
    region = st.selectbox(
        "Région",
        options=REGIONS,
        index=None,
        placeholder="Choisir la région",
        key="region",
    )
with col_dep:
    choix_departements = departements_de(region) if region else list(DEPARTEMENTS.values())
    if st.session_state.get("departement") not in [d.code for d in choix_departements]:
        st.session_state["departement"] = None
    code_departement = st.selectbox(
        "Département",
        options=[d.code for d in choix_departements],
        format_func=lambda c: DEPARTEMENTS[c].libelle,
        index=None,
        placeholder="Choisir le département",
        key="departement",
    )
departement = DEPARTEMENTS.get(code_departement) if code_departement else None
if departement and not region:
    region = departement.region

col_etat, col_date = st.columns([3, 1])
with col_etat:
    etat = st.selectbox(
        "Où en êtes-vous dans votre projet de rénovation énergétique ?",
        options=list(EtatProjet),
        # Sur smartphone, la liste n'affiche qu'une ligne par choix : libellés courts.
        format_func=lambda e: e.libelle_court if SMARTPHONE else e.value,
        index=None,
        placeholder="Sélectionnez l'état de votre projet",
        key="etat",
    )
with col_date:
    date_debut = st.date_input("📅 Date de début", format="DD/MM/YYYY", key=_defaut("date_debut", date.today()))

if etat is None:
    st.info("Sélectionnez l'état de votre projet pour afficher les étapes.")
    _sauvegarder_dans_le_navigateur(None)
    st.stop()

onglet_plan, onglet_budget = st.tabs(["📅 Planification", "💶 Budget et financement"])

with onglet_plan:
    # --------------------------------------------------------------------------
    # Saisie des durées

    DEMARRAGES_FINANCEMENT = {
        FINANCEMENT_APRES_DEFAUT: "Après validation de l'APD (coût prévisionnel connu)",
        None: "Dès le début du projet",
    }
    financement_semaines = None
    financement_apres = st.session_state.get("financement_apres", FINANCEMENT_APRES_DEFAUT)
    col_f1, col_f2, col_f3 = st.columns([1, 2, 2])
    with col_f1:
        avec_financement = st.toggle("💶 Financement", key=_defaut("financement_on", True))
    if avec_financement:
        with col_f2:
            financement_apres = st.selectbox(
                "Montage des dossiers de subvention",
                options=list(DEMARRAGES_FINANCEMENT),
                format_func=DEMARRAGES_FINANCEMENT.get,
                key=_defaut("financement_apres", FINANCEMENT_APRES_DEFAUT),
            )
        with col_f3:
            financement_semaines = st.number_input(
                "Durée jusqu'à l'accusé de dossier complet (sem.)",
                min_value=1,
                max_value=FINANCEMENT_MAX,
                key=_defaut("financement_semaines", 12),
                help="Montage et dépôt des dossiers (DETR, DSIL, Fonds vert…), puis délai pour que le dossier soit "
                "déclaré complet (réputé complet après 2 mois sans réponse). Les marchés de travaux ne seront pas "
                "signés avant : la signature vaut commencement d'exécution.",
            )

    with st.expander("🏛️ Autorisation d'urbanisme et calendrier", expanded=not SMARTPHONE):
        col_a1, col_a2, col_a3 = st.columns([2, 2, 1])
        with col_a1:
            type_autorisation = st.selectbox(
                "Autorisation d'urbanisme nécessaire",
                options=list(TypeAutorisation),
                format_func=lambda t: t.value,
                key=_defaut("type_autorisation", TypeAutorisation.DP),
                help="L'instruction se déroule en parallèle des études PRO / DCE. "
                "Les travaux (VISA, DET) ne démarrent qu'une fois l'autorisation obtenue.",
            )
        with col_a2:
            abf = st.checkbox(
                "Avis de l'Architecte des Bâtiments de France (+1 mois)",
                key=_defaut("abf", False),
                disabled=type_autorisation not in TYPES_MAJORES_ABF,
                help="Abords d'un monument historique ou site patrimonial remarquable (art. R423-24 du code de l'urbanisme).",
            )
            purge_recours = st.checkbox(
                "Attendre la purge du recours des tiers (+2 mois)",
                key=_defaut("purge_recours", False),
                disabled=type_autorisation is TypeAutorisation.AUCUNE,
                help="Démarrer les travaux après le délai de recours des tiers (art. R600-2 du code de l'urbanisme).",
            )
        with col_a3:
            treve_semaines = st.number_input(
                "Trêve de fin d'année (sem.)",
                min_value=0,
                max_value=TREVE_MAX,
                key=_defaut("treve_semaines", TREVE_SEMAINES_DEFAUT),
                help="Semaines non travaillées jusqu'au 1er janvier inclus. Les phases qui la traversent sont "
                "prolongées d'autant ; les délais réglementaires, eux, continuent de courir.",
            )
        autorisation = Autorisation(type_autorisation, abf=abf, purge_recours=purge_recours)
        if autorisation.requise:
            st.caption(
                f"Délai d'instruction retenu : **{autorisation.mois_instruction} mois** "
                f"({ARTICLES_INSTRUCTION[type_autorisation]}). Délai indicatif de droit commun, "
                "à confirmer avec le service instructeur (dossier incomplet, consultations…)."
            )

        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            batiment_scolaire = st.toggle(
                "🏫 Ce bâtiment est-il un bâtiment scolaire ?",
                key=_defaut("batiment_scolaire", False),
                help="École, collège, crèche, gymnase scolaire… Les travaux bruyants se font en général pendant "
                "les vacances d'été.",
            )
        fenetre_travaux = FenetreTravaux.AUCUNE
        ete_personnalise = None
        if batiment_scolaire:
            with col_s2:
                fenetre_travaux = st.radio(
                    "Organisation des travaux",
                    options=list(FenetreTravaux),
                    format_func=lambda f: f.value,
                    key=_defaut("fenetre_travaux", FenetreTravaux.DEBUT_ETE),
                )
            ete_personnalise = _saisir_vacances(departement)

    phases_defaut = phases_pour_etat(etat)
    durees: dict[str, int] = {}
    delais: dict[str, int] = {}

    for groupe in [g for g in ICONES_GROUPES if any(p.groupe is g for p in phases_defaut)]:
        with st.expander(f"{ICONES_GROUPES[groupe]} {groupe.value}", expanded=not SMARTPHONE):
            for phase in (p for p in phases_defaut if p.groupe is groupe):
                colonnes = st.columns([4, 1, 1] if afficher_delais else [5, 1])
                with colonnes[0]:
                    st.markdown(f"**{phase.libelle}**")
                    if definition_courte(phase):
                        st.caption(definition_courte(phase))
                with colonnes[1]:
                    if phase.modifiable:
                        durees[phase.id] = st.number_input(
                            "Durée (sem.)",
                            min_value=phase.duree_min,
                            max_value=DUREE_MAX,
                            key=_defaut(f"duree_{phase.id}", phase.duree),
                            help=f"Minimum : {phase.duree_min} semaine(s)" if phase.duree_min > 1 else None,
                        )
                    elif not phase.afficher_gantt:
                        st.caption("Non affichée sur le Gantt")
                if afficher_delais and phase.afficher_gantt:
                    with colonnes[2]:
                        delais[phase.id] = st.number_input(
                            "Délai MO (sem.)",
                            min_value=0,
                            max_value=DELAI_MO_MAX,
                            key=_defaut(f"delai_{phase.id}", phase.delai_mo),
                        )

    scenario = Scenario(
        etat=etat,
        date_debut=date_debut,
        financement_semaines=financement_semaines,
        durees=durees,
        delais_mo=delais,
        autorisation=autorisation,
        treve_semaines=treve_semaines,
        financement_apres=financement_apres,
        batiment_scolaire=batiment_scolaire,
        fenetre_travaux=fenetre_travaux,
        nom_projet=nom_projet,
        region=region or "",
        departement=code_departement or "",
        ete_personnalise=ete_personnalise,
    )
    planning = scenario.planning()

    # --------------------------------------------------------------------------
    # Résultats

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Date de fin estimée", planning.date_fin.strftime("%d/%m/%Y"))
    m2.metric(
        "Durée totale",
        f"{planning.duree_totale_mois:.1f} mois".replace(".", ","),
        help=f"{planning.duree_totale_semaines:.0f} semaines",
    )
    m3.metric("Dont validations MO", f"{planning.semaines_delai_mo():.0f} semaines")
    if planning.attentes:
        m4.metric(
            "Temps d'attente",
            f"{planning.attente_totale_jours / 7:.0f} semaines",
            help="\n".join(f"- {a.phase} attend : {a.motif} ({a.jours / 7:.0f} sem.)" for a in planning.attentes),
        )
    else:
        m4.metric("Nombre de phases", int((planning.taches["Type"] == "Phase").sum()))

    if planning.fenetre_travaux is not FenetreTravaux.AUCUNE:
        travaux = planning.taches[(planning.taches["Id"] == "DET") & (planning.taches["Type"] == "Phase")]
        debut_travaux = travaux["Debut"].min()
        message = f"🏫 Les travaux démarrent le **{debut_travaux:%d/%m/%Y}**"
        if len(travaux) > 1:
            message += f" et se répartissent sur **{len(travaux)} étés**"
        if planning.gain_pour_ete_precedent_jours:
            attente = next(a for a in planning.attentes if a.motif == "début des vacances d'été")
            message += (
                f", après **{attente.jours / 7:.0f} semaines d'attente** de l'été. Pour démarrer un été plus tôt "
                f"({debut_travaux.year - 1}), il faudrait gagner environ "
                f"**{planning.gain_pour_ete_precedent_jours / 7:.0f} semaines** sur les phases précédentes."
            )
        else:
            message += "."
        st.info(message)

    st.plotly_chart(figure_gantt(planning, aujourd_hui=date.today(), compact=SMARTPHONE), width="stretch")

    st.warning(
        "Vigilance (DET / AOR) : les durées de travaux et de réception sont indicatives et "
        "peuvent évoluer selon la disponibilité des entreprises, des matériaux et de l'équipe de MOE."
    )

    col_jalons, col_export = st.columns([2, 1])
    with col_jalons:
        st.subheader("🏁 Jalons clés")
        st.dataframe(
            [{"Jalon": j.nom, "Date": j.date.strftime("%d/%m/%Y")} for j in planning.jalons],
            hide_index=True,
            width="stretch",
        )
    with col_export:
        st.subheader("⬇️ Exporter")
        st.download_button(
            "Planning PDF (à présenter)",
            lambda: planning_vers_pdf(planning, etat, LOGO, nom_projet=nom_projet, budget=scenario.budget),
            file_name="planning_renovation.pdf",
            mime="application/pdf",
            on_click="ignore",
            type="primary",
            width="stretch",
        )
        st.download_button(
            "Planning Excel (.xlsx)",
            lambda: planning_vers_excel(planning),
            on_click="ignore",
            file_name="planning_renovation.xlsx",
            width="stretch",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Planning CSV",
            lambda: planning_vers_csv(planning),
            on_click="ignore",
            file_name="planning_renovation.csv",
            mime="text/csv",
            width="stretch",
        )
        st.download_button(
            "Jalons dans mon agenda (.ics)",
            lambda: planning_vers_ics(planning, nom_projet or "Projet de rénovation"),
            on_click="ignore",
            file_name="jalons_renovation.ics",
            mime="text/calendar",
            width="stretch",
            help="À importer dans Outlook ou Google Agenda : un événement par jalon.",
        )
        st.download_button(
            "Scénario (.json)",
            # Généré au clic, pour inclure le budget saisi dans l'onglet « Budget et financement ».
            lambda: scenario.vers_json(),
            file_name="scenario_renovation.json",
            mime="application/json",
            on_click="ignore",
            width="stretch",
            help="Paramètres du planning et du budget, à recharger plus tard depuis la barre latérale.",
        )
        st.caption("Le Gantt peut aussi être enregistré en image via l'icône 📷 du graphique.")

    # --------------------------------------------------------------------------
    # Glossaire

    with st.expander("📚 Glossaire des phases de la loi MOP", expanded=False):
        for code, definition in GLOSSAIRE_COMPLET.items():
            st.markdown(f"**{LIBELLES_GLOSSAIRE[code]}** — {definition}")


# --------------------------------------------------------------------------
# Onglet Budget et financement


def _euros(montant: float) -> str:
    return f"{montant:,.0f} €".replace(",", " ")


def _pct(valeur: float) -> str:
    return f"{valeur:.1f} %".replace(".", ",")


def _jalon(nom: str) -> date | None:
    return next((j.date for j in planning.jalons if j.nom == nom), None)


with onglet_budget:
    st.markdown(
        "Estimez le **coût de l'opération**, construisez le **plan de financement** et obtenez l'**échéancier des "
        "dépenses et recettes par année budgétaire**, calé sur le planning de l'onglet précédent. Les taux par "
        "défaut sont des ordres de grandeur, à ajuster à votre projet."
    )

    # 1. Coût de l'opération
    st.subheader("1. Coût de l'opération")
    defauts = postes_par_defaut(set(planning.taches["Id"]))
    # Les forfaits par défaut dépendent des phases au planning (études préalables, AMO) : quand l'état du projet
    # change, on les met à jour, sauf si l'utilisateur les a modifiés.
    precedents = st.session_state.get("postes_auto", {})
    for id_poste, valeur in defauts.items():
        cle = f"poste_{id_poste}"
        if cle in st.session_state and st.session_state[cle] == precedents.get(id_poste) != valeur:
            st.session_state[cle] = float(valeur)
    st.session_state["postes_auto"] = dict(defauts)
    col_t1, col_t2 = st.columns([1, 2])
    with col_t1:
        travaux_ht = st.number_input(
            "Montant estimé des travaux (€ HT)",
            min_value=0,
            step=10_000,
            key=_defaut("travaux_ht", 0),
            help="Estimation issue de l'audit énergétique, du programme ou de l'APD.",
        )
    with st.expander("⚙️ Hypothèses : honoraires, aléas et frais (modifiables)"):
        postes: dict[str, float] = {}
        colonnes_postes = st.columns(3)
        for i, poste in enumerate(POSTES):
            pourcent = poste.mode is Mode.POURCENT
            with colonnes_postes[i % 3]:
                postes[poste.id] = st.number_input(
                    f"{poste.libelle} ({'% des travaux' if pourcent else '€ HT'})",
                    min_value=0.0,
                    step=0.1 if pourcent else 1_000.0,
                    format="%.1f" if pourcent else "%.0f",
                    key=_defaut(f"poste_{poste.id}", float(defauts[poste.id])),
                    help=poste.aide or None,
                )

    with st.expander("⚙️ Trésorerie : FCTVA, versement des aides, paiement des entreprises"):
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            taux_fctva = st.number_input(
                "Taux du FCTVA (%)",
                min_value=0.0,
                max_value=TAUX_FCTVA_MAX,
                step=0.001,
                format="%.3f",
                key=_defaut("taux_fctva", TAUX_FCTVA_DEFAUT),
                help="16,404 % depuis 2015 : à vérifier selon la loi de finances en vigueur.",
            )
        with col_v2:
            regime_fctva = st.selectbox(
                "Versement du FCTVA",
                options=list(RegimeFCTVA),
                format_func=lambda r: r.value,
                key=_defaut("regime_fctva", RegimeFCTVA.N1),
                help="Selon le régime de votre collectivité : N (EPCI, communes nouvelles…), N+1 (régime issu du "
                "plan de relance de 2009) ou N+2 (régime de droit commun).",
            )
        with col_v3:
            acompte_aides = st.number_input(
                "Aides versées au démarrage des travaux (%)",
                min_value=0.0,
                max_value=100.0,
                step=5.0,
                key=_defaut("acompte_aides", 30.0),
                help="Avance versée par les financeurs au démarrage des travaux.",
            )
            solde_aides = st.number_input(
                "Aides versées en solde après la réception (%)",
                min_value=0.0,
                max_value=100.0,
                step=5.0,
                key=_defaut("solde_aides", 20.0),
                help="Versé environ 3 mois après la réception, sur justificatifs. Le reste est versé en acomptes, "
                "au fil des dépenses justifiées.",
            )
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            delai_paiement = st.number_input(
                "Délai de paiement des factures (jours)",
                min_value=0,
                max_value=120,
                step=5,
                key=_defaut("delai_paiement_jours", DELAI_PAIEMENT_JOURS),
                help="Délai global de paiement des collectivités : 30 jours (code de la commande publique, "
                "art. R2192-10).",
            )
        with col_p2:
            avance_entreprises = st.number_input(
                "Avance aux entreprises de travaux (%)",
                min_value=0.0,
                max_value=30.0,
                step=1.0,
                key=_defaut("avance_entreprises", 5.0),
                help="Versée au démarrage, puis récupérée sur les paiements suivants. Au moins 5 % pour les marchés "
                "de plus de 50 000 € HT et de plus de deux mois, sauf renonciation du titulaire.",
            )
        with col_p3:
            retenue_garantie = st.number_input(
                "Retenue de garantie (%)",
                min_value=0.0,
                max_value=5.0,
                step=1.0,
                key=_defaut("retenue_garantie", 5.0),
                help="Au plus 5 % des marchés de travaux, conservés jusqu'à la fin de la garantie de parfait "
                "achèvement (souvent remplacée par une garantie à première demande : mettre alors 0).",
            )

    # 2. Plan de financement
    # Le tableau modifiable part d'une base qui ne doit PAS changer d'une exécution à l'autre : si on lui
    # redonnait le résultat modifié, Streamlit croirait à un nouveau tableau et perdrait la saisie en cours.
    # La base n'est remplacée qu'au chargement d'un scénario ou quand les noms Région/Département changent.
    base_financeurs: list[Financeur] = st.session_state.get("financeurs_base") or Budget().financeurs
    dernier_resultat: list[Financeur] = st.session_state.get("financeurs") or base_financeurs
    renommes = nommer_collectivites(
        dernier_resultat, region or "", f"{departement.nom} ({departement.code})" if departement else ""
    )
    if renommes != dernier_resultat:
        base_financeurs = renommes
        st.session_state["financeurs_base"] = renommes
        st.session_state.pop("editeur_financeurs", None)
    financeurs_saisis = base_financeurs
    tableau_financeurs = pd.DataFrame(
        [
            {
                "Financeur": f.nom,
                "Public": f.public,
                "Taux (% du HT)": f.taux,
                "Montant (€)": f.montant,
                "Statut": f.statut.value,
            }
            for f in financeurs_saisis
        ]
    )

    budget_provisoire = Budget(
        travaux_ht=float(travaux_ht),
        postes=postes,
        financeurs=financeurs_saisis,
        taux_fctva=taux_fctva,
        regime_fctva=regime_fctva,
        acompte_aides=acompte_aides,
        solde_aides=solde_aides,
        delai_paiement_jours=int(delai_paiement),
        avance_entreprises=avance_entreprises,
        retenue_garantie=retenue_garantie,
    )
    couts = budget_provisoire.couts()
    with col_t2:
        k1, k2, k3 = st.columns(3)
        k1.metric("Coût de l'opération HT", _euros(budget_provisoire.total_ht))
        k2.metric("TVA", _euros(budget_provisoire.total_tva))
        k3.metric("Coût de l'opération TTC", _euros(budget_provisoire.total_ttc))
    st.dataframe(
        couts.drop(columns=["Id"]),
        hide_index=True,
        width="stretch",
        # Smartphone : le libellé du poste et le TTC seulement, pour que les montants restent visibles.
        column_order=["Poste", "TTC"] if SMARTPHONE else None,
        column_config={
            "Poste": st.column_config.TextColumn(width="medium" if SMARTPHONE else None),
            **{c: st.column_config.NumberColumn(f"{c} (€)", format="localized") for c in ("HT", "TVA", "TTC")},
        },
    )

    st.subheader("2. Plan de financement")
    st.caption(
        "Saisissez pour chaque financeur un taux (sur le coût HT) ou un montant. Ajoutez des lignes au besoin "
        "(programme ACTEE pour les études, fonds européens, mécénat…). Les CEE sont des aides privées."
    )
    edite = st.data_editor(
        tableau_financeurs,
        key="editeur_financeurs",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        # Smartphone : les montants juste après le nom, visibles sans faire défiler le tableau.
        column_order=["Financeur", "Taux (% du HT)", "Montant (€)", "Public", "Statut"] if SMARTPHONE else None,
        column_config={
            # Valeurs par défaut : une ligne ajoutée est directement utilisable.
            "Financeur": st.column_config.TextColumn(
                width="medium" if SMARTPHONE else "large", default="Nouveau financeur"
            ),
            "Public": st.column_config.CheckboxColumn(
                help="Aide d'une personne publique (comptée dans le plafond).", default=True
            ),
            "Taux (% du HT)": st.column_config.NumberColumn(
                min_value=0.0, max_value=100.0, format="%.1f %%", default=0.0
            ),
            "Montant (€)": st.column_config.NumberColumn(
                min_value=0.0, format="localized", help="Prioritaire sur le taux s'il est renseigné.", default=0.0
            ),
            "Statut": st.column_config.SelectboxColumn(
                options=[s.value for s in StatutAide], default=StatutAide.A_SOLLICITER.value
            ),
        },
    )
    financeurs = []
    for ligne in edite.fillna({"Taux (% du HT)": 0, "Montant (€)": 0}).to_dict("records"):
        nom = str(ligne["Financeur"]).strip() if pd.notna(ligne["Financeur"]) else ""
        taux, montant = float(ligne["Taux (% du HT)"] or 0), float(ligne["Montant (€)"] or 0)
        if not nom and not taux and not montant:
            continue  # ligne vide
        financeurs.append(
            Financeur(
                # Une ligne chiffrée mais sans nom est conservée : l'ignorer fausserait le plan de financement.
                nom or "Financeur sans nom",
                taux,
                montant,
                bool(ligne["Public"]) if pd.notna(ligne["Public"]) else True,
                StatutAide(ligne["Statut"])
                if pd.notna(ligne["Statut"]) and ligne["Statut"]
                else StatutAide.A_SOLLICITER,
            )
        )
    st.session_state["financeurs"] = financeurs
    budget = replace(budget_provisoire, financeurs=financeurs)
    scenario = replace(scenario, budget=budget)

    f1, f2, f3, f4 = st.columns(4)
    f1.metric(f"Aides publiques ({_pct(budget.taux_aides_publiques)} du HT)", _euros(budget.aides_publiques))
    f2.metric("Aides privées (CEE…)", _euros(budget.aides_privees))
    f3.metric("FCTVA attendu", _euros(budget.fctva), help=f"{budget.taux_fctva:.3f} % des dépenses TTC éligibles")
    f4.metric(
        "Reste à charge net",
        _euros(budget.reste_a_charge),
        help="Coût TTC − aides − FCTVA : à couvrir par l'autofinancement ou l'emprunt.",
    )
    if budget.total_ht and budget.depasse_plafond:
        st.error(
            f"Les aides publiques atteignent {_pct(budget.taux_aides_publiques)} du coût HT : au-delà de "
            f"{PLAFOND_AIDES_PUBLIQUES:.0f} %, la participation minimale de 20 % du maître d'ouvrage n'est pas "
            "respectée (CGCT, art. L1111-10). Des dérogations existent : à vérifier auprès de la préfecture."
        )
    elif budget.total_ht and budget.aides:
        st.success(
            f"Participation du maître d'ouvrage : {_pct(100 - budget.taux_aides_publiques)} du coût HT "
            "(minimum 20 % des financements publics, CGCT art. L1111-10)."
        )

    if budget.total_ttc:
        parts = {
            "Aides publiques": budget.aides_publiques,
            "Aides privées (CEE…)": budget.aides_privees,
            "FCTVA": budget.fctva,
            "Reste à charge": max(budget.reste_a_charge, 0),
        }
        donut = go.Figure(
            go.Pie(
                labels=list(parts),
                values=list(parts.values()),
                hole=0.55,
                sort=False,
                marker=dict(colors=["#0915a6", "#2e9e44", "#7b2cbf", "#ff5300"]),
                textinfo="percent",
                textposition="inside",
                hovertemplate="%{label} : %{value:,.0f} €<extra></extra>",
            )
        )
        donut.update_layout(
            title=dict(text="Qui finance le coût TTC ?", font=dict(size=16, color="#0915a6")),
            showlegend=True,
            legend=dict(orientation="h", y=-0.05),
            separators=", ",
            uniformtext=dict(minsize=11, mode="hide"),
            height=360,
            margin=dict(l=10, r=10, t=50, b=10),
        )
        col_d1, col_d2 = st.columns([1, 1])
        with col_d1:
            st.plotly_chart(donut, width="stretch", key="donut_financement")
        with col_d2:
            st.markdown("**Calendrier des demandes d'aide (issu du planning)**")
            depot = _jalon("APD validé")
            complet = _jalon("Financement : dossier complet")
            signature = _jalon("Marchés de travaux signés")
            if depot and complet:
                st.markdown(f"- Montage et dépôt des dossiers à partir du **{depot:%d/%m/%Y}** (APD validé)")
                st.markdown(f"- Dossiers complets attendus le **{complet:%d/%m/%Y}**")
            if signature:
                st.markdown(
                    f"- Signature des marchés de travaux le **{signature:%d/%m/%Y}** : aucun marché ne doit être "
                    "signé avant l'accusé de dossier complet (commencement d'exécution)."
                )
            st.caption(
                "Pensez aux calendriers des appels à projets : la DETR et la DSIL se déposent en général en début "
                "d'année auprès de la préfecture."
            )

    # 3. Échéancier
    st.subheader("3. Échéancier budgétaire (autorisation de programme et crédits de paiement)")
    echeancier = budget.echeancier(planning)
    if budget.total_ttc and not echeancier.empty:
        besoin = -echeancier["Cumul"].min()
        annee_besoin = int(echeancier.loc[echeancier["Cumul"].idxmin(), "Année"])
        e1, e2, e3 = st.columns(3)
        e1.metric("Autorisation de programme (TTC)", _euros(budget.total_ttc))
        e2.metric(
            "Besoin de financement maximal",
            _euros(besoin),
            help="Creux de trésorerie cumulé, avant perception du solde des aides et du FCTVA.",
        )
        e3.metric("Année du besoin maximal", str(annee_besoin))

        fig = go.Figure()
        fig.add_bar(x=echeancier["Année"], y=-echeancier["Dépenses TTC"], name="Dépenses TTC", marker_color="#ff5300")
        fig.add_bar(x=echeancier["Année"], y=echeancier["Aides"], name="Aides", marker_color="#2e9e44")
        fig.add_bar(x=echeancier["Année"], y=echeancier["FCTVA"], name="FCTVA", marker_color="#7b2cbf")
        fig.add_scatter(
            x=echeancier["Année"],
            y=echeancier["Cumul"],
            name="Solde cumulé",
            mode="lines+markers",
            line=dict(color="#0915a6", width=3),
        )
        fig.update_layout(
            barmode="relative",
            height=420,
            margin=dict(l=10, r=10, t=40, b=10),
            plot_bgcolor="white",
            legend=dict(orientation="h", y=-0.15),
            yaxis=dict(title="€", gridcolor="lightgrey", tickformat=",.0f"),
            xaxis=dict(dtick=1),
            separators=", ",
            title=dict(text="Dépenses et recettes par année", font=dict(size=16, color="#0915a6")),
        )
        st.plotly_chart(fig, width="stretch", key="echeancier_budget")
        st.dataframe(
            echeancier.round(0),
            hide_index=True,
            width="stretch",
            column_config={
                "Année": st.column_config.NumberColumn(format="%d"),
                **{
                    c: st.column_config.NumberColumn(f"{c} (€)", format="localized")
                    for c in ("Dépenses TTC", "Aides", "FCTVA", "Solde", "Cumul")
                },
            },
        )
        st.caption(
            "Les crédits de paiement de chaque année correspondent à la colonne « Dépenses TTC ». Hypothèses : "
            "factures payées après le délai de paiement ; travaux, aléas et révisions répartis sur la durée du "
            "chantier, avec l'avance versée au démarrage et la retenue de garantie libérée à la fin de la GPA ; "
            "honoraires de maîtrise d'œuvre répartis par élément de mission ; aides versées en avance au démarrage "
            "des travaux, en acomptes au fil des dépenses et en solde après la réception."
        )
        st.download_button(
            "⬇️ Budget et plan de financement (.xlsx)",
            lambda: budget_vers_excel(budget, planning),
            file_name="budget_renovation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            on_click="ignore",
            type="primary",
        )
    else:
        st.info("Saisissez le montant estimé des travaux pour obtenir l'échéancier.")

_sauvegarder_dans_le_navigateur(scenario.vers_json())
