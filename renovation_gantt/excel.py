"""Mise en forme commune des classeurs Excel exportés."""

from __future__ import annotations

import pandas as pd


def finaliser_classeur(writer: pd.ExcelWriter, largeur_max: int = 80) -> None:
    """Ajuste la largeur des colonnes et neutralise les formules.

    Les exports ne contiennent jamais de formule : un texte saisi qui commence par « = » (nom de financeur,
    nom de projet…) est donc conservé comme texte, pour qu'il ne soit pas exécuté à l'ouverture du fichier.
    """
    for feuille in writer.sheets.values():
        for colonne in feuille.columns:
            for cellule in colonne:
                if cellule.data_type == "f":
                    cellule.data_type = "s"
            largeur = max(len(str(c.value or "")) for c in colonne)
            feuille.column_dimensions[colonne[0].column_letter].width = min(max(12, largeur + 2), largeur_max)
