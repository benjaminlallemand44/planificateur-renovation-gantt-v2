"""Charte graphique ACTEE : couleurs et polices partagées par l'interface, les graphiques et le PDF."""

from pathlib import Path

# Gamme principale. Le bleu domine, l'orange reste en touches ; le texte courant est noir.
BLEU = "#0a17a6"
ORANGE = "#ff5400"
NOIR = "#000000"
LILA = "#d1bffc"
CYAN = "#0dcccc"
BLANC = "#ffffff"

# Gamme complémentaire (toujours avec une ou deux couleurs de la gamme principale).
VERT = "#5bba50"
JAUNE = "#ffc300"
BRUN = "#634123"
GRIS = "#e0e6de"
VERT_FONCE = "#05700f"
BLEU_CIEL = "#8dc8f8"
BLEU_EAU = "#b5dee1"

# Ordre des séries dans les graphiques : bleu, orange, cyan, lila, puis complémentaires.
SERIES = [BLEU, ORANGE, CYAN, LILA, JAUNE, VERT, BLEU_CIEL, BLEU_EAU, BRUN, VERT_FONCE]

TITRAGE = "Bitter"
LABEUR = "Schibsted Grotesk"
# Pile de polices pour le navigateur (substituts de la charte : Georgia et Arial).
FAMILLE_TITRAGE = f"{TITRAGE}, Georgia, serif"
FAMILLE_LABEUR = f"{LABEUR}, Arial, sans-serif"

DOSSIER_POLICES = Path(__file__).resolve().parents[1] / "static" / "fonts"
POLICES = {
    "titrage-black": DOSSIER_POLICES / "Bitter-Black.ttf",
    "titrage-extrabold": DOSSIER_POLICES / "Bitter-ExtraBold.ttf",
    "labeur-medium": DOSSIER_POLICES / "SchibstedGrotesk-Medium.ttf",
    "labeur-bold": DOSSIER_POLICES / "SchibstedGrotesk-Bold.ttf",
}


def rgb(couleur: str) -> tuple[int, int, int]:
    """« #0a17a6 » → (10, 23, 166), pour fpdf."""
    valeur = couleur.lstrip("#")
    return int(valeur[0:2], 16), int(valeur[2:4], 16), int(valeur[4:6], 16)
