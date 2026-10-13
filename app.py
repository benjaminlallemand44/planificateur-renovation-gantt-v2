"""Interface Streamlit du planificateur de projet de rénovation.

Lancement : ``streamlit run app.py``
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from renovation_gantt import __version__
from renovation_gantt.avancement import Avancement, Statut
from renovation_gantt.charts import figure_gantt
from renovation_gantt.export import Scenario, planning_vers_csv, planning_vers_excel, planning_vers_ics
from renovation_gantt.pdf import planning_vers_pdf, point_avancement_pdf
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
from renovation_gantt.suivi import (
    Reference,
    comparer,
    ecart_fin_jours,
    elements_suivis,
    meteo,
    points_attention,
    prochains_jalons,
)

RACINE = Path(__file__).parent
LOGO = RACINE / "images" / "Logo_ACTEE_CMYN-HD.png"
ICONES_GROUPES = {Groupe.ETUDES: "📋", Groupe.AMO: "🧠", Groupe.SELECTION_MOE: "🧑‍💼", Groupe.MOE: "🏗️"}
ICONES_METEO = {"vert": "🟢", "orange": "🟠", "rouge": "🔴", "gris": "⚪"}
AUJOURD_HUI = date.today()

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
    st.session_state["avancement"] = scenario.avancement
    st.session_state["references"] = scenario.references
    st.session_state.pop("editeur_avancement", None)
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
    date_debut = st.date_input("📅 Date de début", format="DD/MM/YYYY", key=_defaut("date_debut", AUJOURD_HUI))

if etat is None:
    st.info("Sélectionnez l'état de votre projet pour afficher les étapes.")
    st.stop()

onglet_plan, onglet_suivi = st.tabs(["📅 Planification", "📍 Suivi de l'avancement"])


# --------------------------------------------------------------------------
# Onglet Planification : paramètres

with onglet_plan:
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
                help="Abords d'un monument historique ou site patrimonial remarquable "
                "(art. R423-24 du code de l'urbanisme).",
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

scenario_prevu = Scenario(
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
# Planning théorique, sans avancement : il fournit la liste des éléments à suivre.
planning_prevu = scenario_prevu.planning()


# --------------------------------------------------------------------------
# Onglet Suivi : saisie de l'avancement


def _en_date(valeur) -> date | None:
    return None if valeur is None or pd.isna(valeur) else pd.Timestamp(valeur).date()


with onglet_suivi:
    st.markdown(
        "Indiquez l'avancement réel de chaque étape. Le planning se recalcule à partir des dates réelles "
        "(les étapes à venir ne peuvent pas démarrer avant aujourd'hui) et se compare au **planning de référence** "
        "que vous avez figé, par exemple lors d'une délibération."
    )
    saisi: dict[str, Avancement] = st.session_state.get("avancement", {})
    elements = elements_suivis(planning_prevu)
    tableau = pd.DataFrame(
        [
            {
                "Id": id_,
                "Étape": libelle,
                "Statut": saisi.get(id_, Avancement()).statut.value,
                "Début réel": saisi.get(id_, Avancement()).debut,
                "Fin réelle / prévue": saisi.get(id_, Avancement()).fin,
                "Commentaire": saisi.get(id_, Avancement()).commentaire,
            }
            for id_, libelle in elements
        ]
    )
    for colonne in ("Début réel", "Fin réelle / prévue"):
        tableau[colonne] = pd.to_datetime(tableau[colonne])
    with st.expander("✏️ Saisir l'avancement", expanded=True):
        edite = st.data_editor(
            tableau,
            key="editeur_avancement",
            hide_index=True,
            width="stretch",
            disabled=["Étape"],
            column_config={
                "Id": None,
                "Étape": st.column_config.TextColumn(width="large"),
                "Statut": st.column_config.SelectboxColumn(options=[s.value for s in Statut], required=True),
                "Début réel": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Fin réelle / prévue": st.column_config.DateColumn(
                    format="DD/MM/YYYY",
                    help="Terminée : date de fin réelle, validation comprise. "
                    "En cours : nouvelle date de fin prévue (facultatif).",
                ),
                "Commentaire": st.column_config.TextColumn(width="medium"),
            },
        )
    avancement = {
        ligne["Id"]: Avancement(
            Statut(ligne["Statut"]),
            _en_date(ligne["Début réel"]),
            _en_date(ligne["Fin réelle / prévue"]),
            ligne["Commentaire"] or "",
        )
        for ligne in edite.to_dict("records")
    }
    avancement = {k: v for k, v in avancement.items() if v != Avancement()}
    st.session_state["avancement"] = avancement

references: list[Reference] = st.session_state.setdefault("references", [])
scenario = replace(scenario_prevu, avancement=avancement, references=references)
planning = scenario.planning(aujourd_hui=AUJOURD_HUI)


# --------------------------------------------------------------------------
# Onglet Planification : résultats

with onglet_plan:
    st.divider()
    if scenario.suivi_actif:
        st.caption("📍 Planning actualisé avec l'avancement saisi dans l'onglet « Suivi de l'avancement ».")
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
        if not travaux.empty:
            debut_travaux = travaux["Debut"].min()
            message = f"🏫 Les travaux démarrent le **{debut_travaux:%d/%m/%Y}**"
            if len(travaux) > 1:
                message += f" et se répartissent sur **{len(travaux)} étés**"
            attente_ete = next((a for a in planning.attentes if a.motif == "début des vacances d'été"), None)
            if attente_ete and planning.gain_pour_ete_precedent_jours:
                message += (
                    f", après **{attente_ete.jours / 7:.0f} semaines d'attente** de l'été. Pour démarrer un été plus "
                    f"tôt ({debut_travaux.year - 1}), il faudrait gagner environ "
                    f"**{planning.gain_pour_ete_precedent_jours / 7:.0f} semaines** sur les phases précédentes."
                )
            else:
                message += "."
            st.info(message)

    st.plotly_chart(figure_gantt(planning, aujourd_hui=AUJOURD_HUI), width="stretch", key="gantt_plan")

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
            "Jalons dans mon agenda (.ics)",
            planning_vers_ics(planning, nom_projet or "Projet de rénovation"),
            file_name="jalons_renovation.ics",
            mime="text/calendar",
            width="stretch",
            help="À importer dans Outlook ou Google Agenda : un événement par jalon.",
        )
        st.download_button(
            "Scénario (.json)",
            scenario.vers_json(),
            file_name="scenario_renovation.json",
            mime="application/json",
            width="stretch",
            help="Paramètres, avancement et références : à recharger plus tard depuis la barre latérale.",
        )
        st.caption("Le Gantt peut aussi être enregistré en image via l'icône 📷 du graphique.")

    with st.expander("📚 Glossaire des phases de la loi MOP", expanded=False):
        for code, definition in GLOSSAIRE_COMPLET.items():
            st.markdown(f"**{LIBELLES_GLOSSAIRE[code]}** — {definition}")


# --------------------------------------------------------------------------
# Onglet Suivi : référence, écarts et point d'avancement

with onglet_suivi:
    col_r1, col_r2, col_r3 = st.columns([3, 2, 1], vertical_alignment="bottom")
    with col_r1:
        nom_reference = st.text_input(
            "Nom de la référence à figer",
            value=f"Planning validé le {AUJOURD_HUI:%d/%m/%Y}",
            help="Par exemple : « Délibération du 12/03/2027 » ou « APD validé ».",
        )
    with col_r2:
        if st.button("📌 Figer le planning actuel comme référence", width="stretch"):
            references.append(Reference.depuis_planning(planning, nom_reference, AUJOURD_HUI))
            st.session_state["reference_choisie"] = len(references) - 1
            st.rerun()

    reference = None
    if references:
        with col_r3:
            if st.button("🗑️ Supprimer", width="stretch", help="Supprime la référence sélectionnée."):
                references.pop(st.session_state.get("reference_choisie", len(references) - 1))
                st.session_state["reference_choisie"] = max(0, len(references) - 1)
                st.rerun()
        choix = st.selectbox(
            "Comparer à la référence",
            options=range(len(references)),
            format_func=lambda i: f"{references[i].nom} (fin prévue le {references[i].date_fin:%d/%m/%Y})",
            key=_defaut("reference_choisie", len(references) - 1),
        )
        reference = references[min(choix, len(references) - 1)]
    else:
        st.info("Aucune référence pour l'instant : figez le planning actuel pour pouvoir mesurer les écarts ensuite.")

    ecart = ecart_fin_jours(planning, reference)
    niveau, libelle_meteo = meteo(ecart)
    elements_statuts = [planning.avancement.get(i, Avancement()).statut for i, _ in elements_suivis(planning)]
    bandeau = {"vert": st.success, "orange": st.warning, "rouge": st.error, "gris": st.info}[niveau]
    bandeau(f"**Météo du projet : {libelle_meteo}**", icon=ICONES_METEO[niveau])
    s2, s3, s4 = st.columns(3)
    s2.metric("Fin prévue", f"{planning.date_fin:%d/%m/%Y}")
    s3.metric("Écart avec la référence", "—" if ecart is None else f"{ecart / 7:+.0f} sem.")
    s4.metric(
        "Étapes terminées",
        f"{sum(s is Statut.TERMINEE for s in elements_statuts)} / {len(elements_statuts)}",
    )

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.subheader("⚠️ Points d'attention")
        points = points_attention(planning, reference, AUJOURD_HUI)
        if points:
            for point in points:
                st.markdown(f"- {point}")
        else:
            st.caption("Aucun point d'attention particulier.")
    with col_p2:
        st.subheader("🔜 Prochaines étapes")
        for jalon in prochains_jalons(planning, AUJOURD_HUI):
            st.markdown(f"- **{jalon.date:%d/%m/%Y}** — {jalon.nom}")

    st.plotly_chart(
        figure_gantt(planning, aujourd_hui=AUJOURD_HUI, reference=reference.elements if reference else None),
        width="stretch",
        key="gantt_suivi",
    )

    st.subheader("📋 Tableau de suivi")
    suivi = comparer(planning, reference).drop(columns=["Id"])
    st.dataframe(
        suivi,
        hide_index=True,
        width="stretch",
        column_config={
            "Début": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Fin": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Fin (référence)": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Écart (sem.)": st.column_config.NumberColumn(format="%+d"),
        },
    )

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        st.download_button(
            "🗳️ Point d'avancement pour les élus (PDF)",
            lambda: point_avancement_pdf(planning, reference, AUJOURD_HUI, nom_projet, LOGO),
            file_name=f"point_avancement_{AUJOURD_HUI:%Y%m%d}.pdf",
            mime="application/pdf",
            on_click="ignore",
            type="primary",
            width="stretch",
        )
    with col_e2:
        st.download_button(
            "💾 Enregistrer le suivi (scénario .json)",
            scenario.vers_json(),
            file_name="scenario_renovation.json",
            mime="application/json",
            width="stretch",
            key="json_suivi",
        )
    st.caption(
        "L'avancement et les références ne sont conservés que dans le fichier scénario : pensez à l'enregistrer "
        "après chaque mise à jour, puis à le recharger depuis la barre latérale."
    )
