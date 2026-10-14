"""Interface Streamlit du planificateur de projet de rénovation.

Lancement : ``streamlit run app.py``
"""

from __future__ import annotations

import hashlib
import sys
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
    PLAFOND_AIDES_PUBLIQUES,
    POSTES,
    TAUX_FCTVA_DEFAUT,
    Budget,
    Financeur,
    Mode,
    RegimeFCTVA,
    StatutAide,
    budget_vers_excel,
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

RACINE = Path(__file__).parent
LOGO = RACINE / "images" / "Logo_ACTEE_CMYN-HD.png"
ICONES_GROUPES = {Groupe.ETUDES: "📋", Groupe.AMO: "🧠", Groupe.SELECTION_MOE: "🧑‍💼", Groupe.MOE: "🏗️"}

st.set_page_config(page_title="Planificateur rénovation", page_icon="📊", layout="wide")


def _defaut(cle: str, valeur) -> str:
    """Initialise une valeur de widget une seule fois (évite les conflits avec un scénario chargé)."""
    st.session_state.setdefault(cle, valeur)
    return cle


# --------------------------------------------------------------------------
# Chargement d'un scénario : on alimente st.session_state avant de créer les widgets.


def _charger_scenario() -> None:
    fichier = st.session_state.get("fichier_scenario")
    if fichier is None:
        return
    try:
        scenario = Scenario.depuis_json(fichier.getvalue())
    except ValueError as exc:
        st.session_state["erreur_scenario"] = str(exc)
        return
    st.session_state["etat"] = scenario.etat
    st.session_state["date_debut"] = scenario.date_debut
    st.session_state["nom_projet"] = scenario.nom_projet
    budget = scenario.budget
    st.session_state["travaux_ht"] = int(budget.travaux_ht)
    for id_poste, valeur in budget.postes.items():
        st.session_state[f"poste_{id_poste}"] = float(valeur)
    st.session_state["taux_fctva"] = budget.taux_fctva
    st.session_state["regime_fctva"] = budget.regime_fctva
    st.session_state["acompte_aides"] = budget.acompte_aides
    st.session_state["financeurs"] = budget.financeurs
    st.session_state.pop("editeur_financeurs", None)
    st.session_state["financement_on"] = bool(scenario.financement_semaines)
    if scenario.financement_semaines:
        st.session_state["financement_semaines"] = scenario.financement_semaines
    st.session_state["financement_apres"] = scenario.financement_apres
    for phase in scenario.phases():
        st.session_state[f"duree_{phase.id}"] = phase.duree
        st.session_state[f"delai_{phase.id}"] = phase.delai_mo
    st.session_state["type_autorisation"] = scenario.autorisation.type
    st.session_state["abf"] = scenario.autorisation.abf
    st.session_state["purge_recours"] = scenario.autorisation.purge_recours
    st.session_state["treve_semaines"] = scenario.treve_semaines
    st.session_state["batiment_scolaire"] = scenario.batiment_scolaire
    if scenario.fenetre_travaux is not FenetreTravaux.AUCUNE:
        st.session_state["fenetre_travaux"] = scenario.fenetre_travaux
    st.session_state["afficher_delais"] = any(
        p.delai_mo != d.delai_mo for p, d in zip(scenario.phases(), phases_pour_etat(scenario.etat), strict=True)
    )
    st.session_state["erreur_scenario"] = None
    st.session_state["scenario_charge"] = fichier.name


# --------------------------------------------------------------------------
# Barre latérale

with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), width="stretch")
    st.header("💾 Scénario")
    st.file_uploader("Charger un scénario (.json)", type="json", key="fichier_scenario", on_change=_charger_scenario)
    if st.session_state.get("erreur_scenario"):
        st.error(st.session_state["erreur_scenario"])
    elif st.session_state.get("scenario_charge"):
        st.success(f"Scénario « {st.session_state['scenario_charge']} » chargé.")
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

col_nom, col_etat, col_date = st.columns([2, 3, 1])
with col_nom:
    nom_projet = st.text_input(
        "Nom du projet",
        key=_defaut("nom_projet", ""),
        placeholder="Ex. : Rénovation de l'école Jules Ferry",
    )
with col_etat:
    etat = st.selectbox(
        "Où en êtes-vous dans votre projet de rénovation énergétique ?",
        options=list(EtatProjet),
        format_func=lambda e: e.value,
        index=None,
        placeholder="Sélectionnez l'état de votre projet",
        key="etat",
    )
with col_date:
    date_debut = st.date_input("📅 Date de début", format="DD/MM/YYYY", key=_defaut("date_debut", date.today()))

if etat is None:
    st.info("Sélectionnez l'état de votre projet pour afficher les étapes.")
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
                max_value=104,
                key=_defaut("financement_semaines", 12),
                help="Montage et dépôt des dossiers (DETR, DSIL, Fonds vert…), puis délai pour que le dossier soit "
                "déclaré complet (réputé complet après 2 mois sans réponse). Les marchés de travaux ne seront pas "
                "signés avant : la signature vaut commencement d'exécution.",
            )

    with st.expander("🏛️ Autorisation d'urbanisme et calendrier", expanded=True):
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
                max_value=4,
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
        if batiment_scolaire:
            with col_s2:
                fenetre_travaux = st.radio(
                    "Organisation des travaux",
                    options=list(FenetreTravaux),
                    format_func=lambda f: f.value,
                    key=_defaut("fenetre_travaux", FenetreTravaux.DEBUT_ETE),
                    help="Vacances d'été retenues : du 6 juillet au 31 août, à ajuster au calendrier de votre zone.",
                )

    phases_defaut = phases_pour_etat(etat)
    durees: dict[str, int] = {}
    delais: dict[str, int] = {}

    for groupe in [g for g in ICONES_GROUPES if any(p.groupe is g for p in phases_defaut)]:
        with st.expander(f"{ICONES_GROUPES[groupe]} {groupe.value}", expanded=True):
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
                            max_value=156,
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
                            max_value=52,
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

    st.plotly_chart(figure_gantt(planning, aujourd_hui=date.today()), width="stretch")

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
            lambda: planning_vers_pdf(planning, etat, LOGO, nom_projet=nom_projet),
            file_name="planning_renovation.pdf",
            mime="application/pdf",
            on_click="ignore",
            type="primary",
            width="stretch",
        )
        st.download_button(
            "Planning Excel (.xlsx)",
            planning_vers_excel(planning),
            file_name="planning_renovation.xlsx",
            width="stretch",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Planning CSV",
            planning_vers_csv(planning),
            file_name="planning_renovation.csv",
            mime="text/csv",
            width="stretch",
        )
        st.download_button(
            "Jalons dans mon agenda (.ics)",
            planning_vers_ics(planning, nom_projet or "Projet de rénovation"),
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

    with st.expander("⚙️ FCTVA et versement des aides"):
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            taux_fctva = st.number_input(
                "Taux du FCTVA (%)",
                min_value=0.0,
                max_value=30.0,
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
                help="Avance ou acompte ; le solde est versé environ 3 mois après la réception, sur justificatifs.",
            )

    # 2. Plan de financement
    financeurs_saisis: list[Financeur] = st.session_state.get("financeurs") or Budget().financeurs
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
        column_config={c: st.column_config.NumberColumn(f"{c} (€)", format="localized") for c in ("HT", "TVA", "TTC")},
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
        column_config={
            "Financeur": st.column_config.TextColumn(required=True, width="large"),
            "Public": st.column_config.CheckboxColumn(help="Aide d'une personne publique (comptée dans le plafond)."),
            "Taux (% du HT)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.1f %%"),
            "Montant (€)": st.column_config.NumberColumn(
                min_value=0.0, format="localized", help="Prioritaire sur le taux s'il est renseigné."
            ),
            "Statut": st.column_config.SelectboxColumn(options=[s.value for s in StatutAide], required=True),
        },
    )
    financeurs = [
        Financeur(
            str(ligne["Financeur"]),
            float(ligne["Taux (% du HT)"] or 0),
            float(ligne["Montant (€)"] or 0),
            bool(ligne["Public"]) if pd.notna(ligne["Public"]) else True,
            StatutAide(ligne["Statut"]) if ligne["Statut"] else StatutAide.A_SOLLICITER,
        )
        for ligne in edite.fillna({"Taux (% du HT)": 0, "Montant (€)": 0}).to_dict("records")
        if ligne["Financeur"] and pd.notna(ligne["Financeur"])
    ]
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
            "travaux, aléas et révisions répartis sur la durée des travaux ; honoraires de maîtrise d'œuvre répartis "
            "par élément de mission ; aides versées en acompte au démarrage des travaux et en solde après la réception."
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
