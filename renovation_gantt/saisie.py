"""Contrôle des valeurs saisies ou lues dans un fichier de scénario."""

from __future__ import annotations

import math


def borner(valeur, mini: float, maxi: float) -> tuple[float, bool]:
    """Ramène une valeur dans [mini, maxi].

    Renvoie la valeur corrigée (entière si les bornes sont entières) et un indicateur d'ajustement.
    Une valeur illisible ou NaN est remplacée par le minimum.
    """
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        nombre = math.nan
    corrige = mini if math.isnan(nombre) else min(max(nombre, mini), maxi)
    if isinstance(mini, int) and isinstance(maxi, int):
        corrige = int(round(corrige))
    else:
        corrige = float(corrige)
    return corrige, math.isnan(nombre) or corrige != nombre
