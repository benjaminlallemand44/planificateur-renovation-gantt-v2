"""Interface Streamlit du planificateur de projet de rénovation.

Lancement : ``streamlit run app.py``
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from renovation_gantt import __version__
from renovation_gantt.charts import figure_gantt
from renovation_gantt.export import Scenario, planning_vers_csv, planning_vers_excel
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

col_etat, col_date = st.columns([3, 1])
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
        lambda: planning_vers_pdf(planning, etat, LOGO),
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
        "Scénario (.json)",
        scenario.vers_json(),
        file_name="scenario_renovation.json",
        mime="application/json",
        width="stretch",
        help="À recharger plus tard depuis la barre latérale.",
    )
    st.caption("Le Gantt peut aussi être enregistré en image via l'icône 📷 du graphique.")


# --------------------------------------------------------------------------
# Glossaire

with st.expander("📚 Glossaire des phases de la loi MOP", expanded=False):
    for code, definition in GLOSSAIRE_COMPLET.items():
        st.markdown(f"**{LIBELLES_GLOSSAIRE[code]}** — {definition}")
