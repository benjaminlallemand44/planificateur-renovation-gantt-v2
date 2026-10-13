"""Construction du diagramme de Gantt Plotly."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .phases import COULEURS_GROUPES, Groupe
from .planning import TYPE_DELAI_MO, TYPE_FINANCEMENT, TYPE_PHASE, Planning

COULEURS_TYPES = {TYPE_PHASE: "#0915a6", TYPE_DELAI_MO: "#ff5300", TYPE_FINANCEMENT: "#2e9e44"}


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

    _ajouter_bandeaux(fig, df)
    _ajouter_jalons(fig, planning)
    if aujourd_hui and planning.date_debut <= aujourd_hui <= planning.date_fin:
        _ligne_verticale(fig, aujourd_hui, "Aujourd'hui", "#888888", "dot")

    fig.update_layout(
        height=max(450, 32 * len(ordre_taches) + 220),
        margin=dict(l=20, r=20, t=110, b=40),
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="top", y=-0.06, x=0, title=None),
        title=dict(text="📅 Diagramme de Gantt du projet", font=dict(size=18, color="#0915a6")),
    )
    return fig


def _ajouter_bandeaux(fig: go.Figure, df: pd.DataFrame) -> None:
    for groupe in Groupe:
        sous_df = df[df["Groupe"] == groupe.value]
        if sous_df.empty:
            continue
        debut, fin = sous_df["Debut"].min(), sous_df["Fin"].max()
        y0, y1 = (1.10, 1.16) if groupe is Groupe.FINANCEMENT else (1.02, 1.08)
        fig.add_shape(
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
        fig.add_annotation(
            x=debut + (fin - debut) / 2,
            y=(y0 + y1) / 2,
            xref="x",
            yref="paper",
            text=f"<b>{groupe.value}</b>",
            showarrow=False,
            font=dict(size=11, color="black"),
        )


def _ajouter_jalons(fig: go.Figure, planning: Planning) -> None:
    for jalon in planning.jalons:
        couleur = "#c00000" if jalon.nom == "Fin du projet" else "#444444"
        _ligne_verticale(fig, jalon.date, f"◆ {jalon.nom}", couleur, "dash")


def _ligne_verticale(fig: go.Figure, jour: date, texte: str, couleur: str, style: str) -> None:
    x = pd.Timestamp(jour)
    fig.add_shape(
        type="line", xref="x", yref="paper", x0=x, x1=x, y0=0, y1=1, line=dict(color=couleur, width=1, dash=style)
    )
    fig.add_annotation(
        x=x,
        y=1,
        xref="x",
        yref="paper",
        text=texte,
        showarrow=False,
        textangle=-90,
        xanchor="right",
        yanchor="top",
        font=dict(size=10, color=couleur),
    )
