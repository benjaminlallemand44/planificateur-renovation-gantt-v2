"""Construction du diagramme de Gantt Plotly."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .phases import COULEURS_GROUPES, Groupe
from .planning import (
    TYPE_ATTENTE,
    TYPE_DELAI_MO,
    TYPE_FINANCEMENT,
    TYPE_GPA,
    TYPE_INSTRUCTION,
    TYPE_PHASE,
    TYPE_RECOURS,
    Planning,
)

COULEURS_TYPES = {
    TYPE_PHASE: "#0915a6",
    TYPE_DELAI_MO: "#ff5300",
    TYPE_FINANCEMENT: "#2e9e44",
    TYPE_INSTRUCTION: "#7b2cbf",
    TYPE_RECOURS: "#c3a6e8",
    TYPE_ATTENTE: "#f6d55c",
    TYPE_GPA: "#b8dcc6",
}
COULEUR_TREVE = "#e6e6e6"


def figure_gantt(planning: Planning, aujourd_hui: date | None = None) -> go.Figure:
    """Diagramme de Gantt : barres par phase, bandeaux par catégorie et jalons."""
    df = planning.taches.copy()
    if df.empty:
        raise ValueError("Le planning ne contient aucune tâche à afficher.")

    df["Debut"] = pd.to_datetime(df["Debut"])
    df["Fin"] = pd.to_datetime(df["Fin"])
    df["Survol"] = (
        df["Definition"].fillna("")
        + "<br>Du "
        + df["Debut"].dt.strftime("%d/%m/%Y")
        + " au "
        + df["Fin"].dt.strftime("%d/%m/%Y")
        + "<br>Durée : "
        + df["Semaines"].round(1).astype(str)
        + " semaine(s)"
    )

    ordre_taches = list(dict.fromkeys(df["Tache"]))
    fig = px.timeline(
        df,
        x_start="Debut",
        x_end="Fin",
        y="Tache",
        color="Type",
        custom_data=["Survol", "Groupe"],
        color_discrete_map=COULEURS_TYPES,
        category_orders={"Tache": ordre_taches, "Type": list(COULEURS_TYPES)},
    )
    fig.update_traces(
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>Catégorie : %{customdata[1]}<extra></extra>",
        marker_line_width=1,
        marker_line_color="black",
    )
    fig.update_yaxes(title=None, tickfont=dict(size=12))
    fig.update_xaxes(showgrid=True, gridcolor="lightgrey", title=None, tickfont=dict(size=13))

    # Formes et annotations sont ajoutées en une seule fois : les ajouter une à une est très lent avec Plotly.
    formes: list[dict] = []
    annotations: list[dict] = []
    _ajouter_treve(fig, planning, formes)
    _ajouter_bandeaux(df, formes, annotations)
    _ajouter_jalons(planning, formes, annotations)
    if aujourd_hui and planning.date_debut <= aujourd_hui <= planning.date_fin_affichage:
        _ligne_verticale(formes, annotations, aujourd_hui, "Aujourd'hui", "#888888", "dot")

    fig.update_layout(shapes=formes, annotations=annotations)
    fig.update_layout(
        height=max(560, 32 * len(ordre_taches) + 220),
        margin=dict(l=20, r=20, t=110, b=40),
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="top", y=-0.06, x=0, title=None),
        title=dict(text="📅 Diagramme de Gantt du projet", font=dict(size=18, color="#0915a6")),
    )
    return fig


def _ajouter_treve(fig: go.Figure, planning: Planning, formes: list[dict]) -> None:
    for debut, fin in planning.periodes_treve:
        formes.append(
            dict(
                type="rect",
                xref="x",
                yref="paper",
                x0=pd.Timestamp(debut),
                x1=pd.Timestamp(fin),
                y0=0,
                y1=1,
                fillcolor=COULEUR_TREVE,
                line=dict(width=0),
                layer="below",
            )
        )
    if planning.periodes_treve:
        # Entrée de légende pour expliquer les bandes grises.
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(symbol="square", size=14, color=COULEUR_TREVE, line=dict(color="#999999", width=1)),
                name="Trêve de fin d'année",
                hoverinfo="skip",
            )
        )


ABREVIATIONS_GROUPES = {
    Groupe.ETUDES: "Études",
    Groupe.AMO: "AMO",
    Groupe.SELECTION_MOE: "Sél. MOE",
    Groupe.MOE: "MOE",
    Groupe.FINANCEMENT: "Financ.",
}


def libelle_bandeau(groupe: Groupe, fraction: float, largeur_caractere: float = 0.0075) -> str:
    """Libellé du bandeau d'une catégorie, abrégé (ou omis) si le bandeau est trop étroit.

    ``fraction`` : largeur du bandeau rapportée à la durée totale affichée."""
    for texte in (groupe.value, ABREVIATIONS_GROUPES[groupe]):
        if fraction >= len(texte) * largeur_caractere:
            return texte
    return ""


def _ajouter_bandeaux(df: pd.DataFrame, formes: list[dict], annotations: list[dict]) -> None:
    etendue = df["Fin"].max() - df["Debut"].min()
    for groupe in Groupe:
        sous_df = df[df["Groupe"] == groupe.value]
        if sous_df.empty:
            continue
        debut, fin = sous_df["Debut"].min(), sous_df["Fin"].max()
        texte = libelle_bandeau(groupe, (fin - debut) / etendue)
        y0, y1 = (1.10, 1.16) if groupe is Groupe.FINANCEMENT else (1.02, 1.08)
        formes.append(
            dict(
                type="rect",
                xref="x",
                yref="paper",
                x0=debut,
                x1=fin,
                y0=y0,
                y1=y1,
                fillcolor=COULEURS_GROUPES[groupe],
                line=dict(width=0),
                opacity=0.9,
            )
        )
        annotations.append(
            dict(
                x=debut + (fin - debut) / 2,
                y=(y0 + y1) / 2,
                xref="x",
                yref="paper",
                text=f"<b>{texte}</b>" if texte else "",
                hovertext=groupe.value,
                showarrow=False,
                font=dict(size=11, color="black"),
            )
        )


def etiquettes_a_droite(planning: Planning) -> list[bool]:
    """Pour chaque jalon, indique si son étiquette doit passer à droite de sa ligne.

    Par défaut l'étiquette est à gauche ; on la bascule à droite quand le jalon précédent
    est trop proche, pour éviter que les deux textes se superposent."""
    ecart_min = max(10, (planning.date_fin - planning.date_debut).days * 0.015)
    resultat, precedent = [], None
    for jalon in planning.jalons:
        a_droite = precedent is not None and (jalon.date - precedent).days < ecart_min and not resultat[-1]
        resultat.append(a_droite)
        precedent = jalon.date
    return resultat


def _ajouter_jalons(planning: Planning, formes: list[dict], annotations: list[dict]) -> None:
    for jalon, a_droite in zip(planning.jalons, etiquettes_a_droite(planning), strict=True):
        couleur = "#c00000" if jalon.nom == "Fin du projet" else "#444444"
        _ligne_verticale(formes, annotations, jalon.date, f"◆ {jalon.nom}", couleur, "dash", a_droite)


def _ligne_verticale(
    formes: list[dict],
    annotations: list[dict],
    jour: date,
    texte: str,
    couleur: str,
    style: str,
    a_droite: bool = False,
) -> None:
    x = pd.Timestamp(jour)
    formes.append(
        dict(type="line", xref="x", yref="paper", x0=x, x1=x, y0=0, y1=1, line=dict(color=couleur, width=1, dash=style))
    )
    annotations.append(
        dict(
            x=x,
            y=1,
            xref="x",
            yref="paper",
            text=texte,
            showarrow=False,
            textangle=-90,
            xanchor="left" if a_droite else "right",
            yanchor="top",
            font=dict(size=10, color=couleur),
        )
    )
