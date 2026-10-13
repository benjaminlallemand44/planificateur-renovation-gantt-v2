"""Export PDF du planning (A4 paysage), prêt à présenter.

Le Gantt est redessiné avec matplotlib plutôt qu'exporté depuis Plotly : l'export
d'images Plotly nécessite un navigateur Chrome, absent de Streamlit Community Cloud.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from fpdf import FPDF  # noqa: E402
from fpdf.fonts import FontFace  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

from .avancement import Avancement, Statut  # noqa: E402
from .charts import COULEUR_TREVE, COULEURS_TYPES, etiquettes_a_droite, libelle_bandeau  # noqa: E402
from .export import indicateurs  # noqa: E402
from .phases import COULEURS_GROUPES, EtatProjet, Groupe  # noqa: E402
from .planning import Planning  # noqa: E402
from .suivi import Reference, ecart_fin_jours, elements_suivis, meteo, points_attention, prochains_jalons  # noqa: E402

BLEU = (9, 21, 166)
MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
_EMOJIS = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]")


def texte_sans_emoji(texte: str) -> str:
    return re.sub(r"\s+", " ", _EMOJIS.sub("", texte)).strip()


def planning_vers_pdf(
    planning: Planning,
    etat: EtatProjet | None = None,
    logo: Path | None = None,
    edition: date | None = None,
) -> bytes:
    if planning.taches.empty:
        raise ValueError("Le planning ne contient aucune tâche à exporter.")
    edition = edition or date.today()

    pdf = _document()

    # Page 1 : en-tête et diagramme de Gantt
    pdf.add_page()
    _entete(pdf, etat, logo, edition)
    image = _gantt_png(planning)
    pdf.image(image, x=10, y=pdf.get_y() + 2, w=pdf.epw)

    # Page 2 : indicateurs, jalons et détail des phases
    pdf.add_page()
    _titre_section(pdf, "Synthèse")
    _tableau(pdf, [("Indicateur", "Valeur"), *indicateurs(planning)], (70, 120))
    pdf.ln(4)
    _titre_section(pdf, "Jalons clés")
    _tableau(
        pdf,
        [("Jalon", "Date"), *[(j.nom, j.date.strftime("%d/%m/%Y")) for j in planning.jalons]],
        (90, 35),
    )
    pdf.ln(4)
    _titre_section(pdf, "Détail des phases")
    lignes = [("Phase", "Type", "Début", "Fin", "Durée (sem.)")]
    for t in planning.taches.itertuples():
        lignes.append(
            (
                texte_sans_emoji(t.Tache),
                t.Type,
                t.Debut.strftime("%d/%m/%Y"),
                t.Fin.strftime("%d/%m/%Y"),
                f"{t.Semaines:.0f}",
            )
        )
    _tableau(pdf, lignes, (125, 45, 30, 30, 25))
    return bytes(pdf.output())


COULEURS_METEO = {"vert": (46, 158, 68), "orange": (230, 140, 20), "rouge": (200, 30, 30), "gris": (130, 130, 130)}


def point_avancement_pdf(
    planning: Planning,
    reference: Reference | None,
    aujourd_hui: date,
    nom_projet: str = "",
    logo: Path | None = None,
) -> bytes:
    """Point d'avancement synthétique pour les élus : météo, chiffres clés, prochaines étapes,
    points d'attention (page 1) et Gantt actualisé (page 2)."""
    if planning.taches.empty:
        raise ValueError("Le planning ne contient aucune tâche à exporter.")
    pdf = _document()
    pdf.add_page()

    # En-tête
    x_texte = 10
    if logo is not None and Path(logo).exists():
        pdf.image(str(logo), x=10, y=8, h=14)
        x_texte = 75
    pdf.set_xy(x_texte, 8)
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(*BLEU)
    pdf.cell(0, 8, "Point d'avancement")
    pdf.set_xy(x_texte, 17)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 5, f"{nom_projet or 'Projet de rénovation énergétique'}  —  situation au {aujourd_hui:%d/%m/%Y}")

    # Météo
    ecart = ecart_fin_jours(planning, reference)
    niveau, libelle = meteo(ecart)
    pdf.set_fill_color(*COULEURS_METEO[niveau])
    pdf.rect(10, 30, pdf.epw, 14, style="F", round_corners=True, corner_radius=3)
    pdf.set_xy(14, 33)
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, libelle)

    # Chiffres clés
    elements = elements_suivis(planning)
    statuts = [planning.avancement.get(i, Avancement()).statut for i, _ in elements]
    terminees = sum(s is Statut.TERMINEE for s in statuts)
    en_cours = [texte_sans_emoji(n) for (i, n), s in zip(elements, statuts, strict=True) if s is Statut.EN_COURS]
    chiffres = [
        ("Fin du projet prévue", f"{planning.date_fin:%d/%m/%Y}"),
        (
            "Écart avec la référence",
            "—" if ecart is None else ("à l'heure" if abs(ecart) < 7 else f"{ecart / 7:+.0f} semaines"),
        ),
        ("Étapes terminées", f"{terminees} / {len(elements)}"),
    ]
    largeur = (pdf.epw - 10) / 3
    for k, (titre, valeur) in enumerate(chiffres):
        x = 10 + k * (largeur + 5)
        pdf.set_fill_color(240, 242, 250)
        pdf.rect(x, 49, largeur, 22, style="F", round_corners=True, corner_radius=2)
        pdf.set_xy(x + 4, 51)
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(largeur - 8, 5, titre)
        pdf.set_xy(x + 4, 58)
        pdf.set_font("DejaVu", "B", 15)
        pdf.set_text_color(*BLEU)
        pdf.cell(largeur - 8, 9, valeur)
    if reference is not None:
        pdf.set_xy(10, 73)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(0, 4, f"Référence : « {reference.nom} », fin prévue le {reference.date_fin:%d/%m/%Y}.")

    # Prochaines étapes et points d'attention, sur deux colonnes
    y0 = 80
    colonne = (pdf.epw - 8) / 2
    pdf.set_xy(10, y0)
    _titre_section(pdf, "Où en est-on ?")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(10)
    pdf.multi_cell(colonne, 5.5, "En cours : " + (", ".join(en_cours) if en_cours else "aucune étape en cours."))
    pdf.ln(2)
    pdf.set_x(10)
    _titre_section(pdf, "Prochaines étapes")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(0, 0, 0)
    for jalon in prochains_jalons(planning, aujourd_hui):
        pdf.set_x(10)
        pdf.multi_cell(colonne, 5.5, f"•  {jalon.date:%d/%m/%Y}  —  {jalon.nom}")

    x_droite = 10 + colonne + 8
    pdf.set_xy(x_droite, y0)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*BLEU)
    pdf.cell(colonne, 7, "Points d'attention", new_x="LEFT", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(0, 0, 0)
    points = points_attention(planning, reference, aujourd_hui)[:7] or ["Aucun point d'attention particulier."]
    for point in points:
        pdf.set_x(x_droite)
        pdf.multi_cell(colonne, 5.5, f"•  {point}")
        pdf.ln(1)

    # Page 2 : Gantt actualisé
    pdf.add_page()
    _titre_section(pdf, "Planning actualisé")
    pdf.image(_gantt_png(planning), x=10, y=pdf.get_y() + 1, w=pdf.epw)
    return bytes(pdf.output())


def _document() -> _Document:
    pdf = _Document(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    polices = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdf.add_font("DejaVu", "", polices / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", polices / "DejaVuSans-Bold.ttf")
    return pdf


class _Document(FPDF):
    def footer(self) -> None:
        self.set_y(-11)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(110, 110, 110)
        self.cell(
            0,
            5,
            "Planning indicatif : les durées de travaux et les délais réglementaires sont à confirmer "
            f"auprès de la maîtrise d'œuvre et du service instructeur.    Page {self.page_no()}/{{nb}}",
            align="C",
        )


def _entete(pdf: FPDF, etat: EtatProjet | None, logo: Path | None, edition: date) -> None:
    x_texte = 10
    if logo is not None and Path(logo).exists():
        pdf.image(str(logo), x=10, y=8, h=14)
        x_texte = 75
    pdf.set_xy(x_texte, 8)
    pdf.set_font("DejaVu", "B", 15)
    pdf.set_text_color(*BLEU)
    pdf.cell(0, 7, "Planning prévisionnel du projet de rénovation énergétique")
    pdf.set_xy(x_texte, 16)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(60, 60, 60)
    sous_titre = f"Édité le {edition.strftime('%d/%m/%Y')}"
    if etat is not None:
        sous_titre = f"Situation de départ : {EtatProjet(etat).value}  —  {sous_titre}"
    pdf.multi_cell(0, 4.5, sous_titre)
    pdf.set_y(max(pdf.get_y(), 24))


def _titre_section(pdf: FPDF, titre: str) -> None:
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*BLEU)
    pdf.cell(0, 7, titre, new_x="LMARGIN", new_y="NEXT")


def _tableau(pdf: FPDF, lignes: list[tuple[str, ...]], largeurs: tuple[int, ...]) -> None:
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(0, 0, 0)
    entete = FontFace(emphasis="BOLD", fill_color=(230, 233, 250))
    with pdf.table(
        col_widths=largeurs,
        width=sum(largeurs),
        align="LEFT",
        headings_style=entete,
        line_height=5,
        first_row_as_headings=True,
    ) as table:
        for ligne in lignes:
            row = table.row()
            for valeur in ligne:
                row.cell(str(valeur))


# --------------------------------------------------------------------------
# Diagramme de Gantt matplotlib


def _gantt_png(planning: Planning) -> io.BytesIO:
    df = planning.taches.copy()
    df["Libelle"] = df["Tache"].map(texte_sans_emoji)
    lignes = list(dict.fromkeys(df["Libelle"]))
    position = {nom: len(lignes) - 1 - i for i, nom in enumerate(lignes)}

    fig, ax = plt.subplots(figsize=(11.2, 6.7), dpi=200)
    debut_axe = planning.date_debut - timedelta(days=7)
    fin_axe = planning.date_fin_affichage + timedelta(days=7)

    for debut, fin in planning.periodes_treve:
        ax.axvspan(debut, fin, color=COULEUR_TREVE, zorder=0, lw=0)

    for t in df.itertuples():
        ax.barh(
            position[t.Libelle],
            (t.Fin - t.Debut).days,
            left=mdates.date2num(t.Debut),
            height=0.62,
            color=COULEURS_TYPES.get(t.Type, "#888888"),
            edgecolor="black",
            linewidth=0.4,
            zorder=3,
        )

    trans = blended_transform_factory(ax.transData, ax.transAxes)
    debut_axe_num, fin_axe_num = mdates.date2num(debut_axe), mdates.date2num(fin_axe)
    for groupe in Groupe:
        sous_df = df[df["Groupe"] == groupe.value]
        if sous_df.empty:
            continue
        debut, fin = mdates.date2num(sous_df["Debut"].min()), mdates.date2num(sous_df["Fin"].max())
        texte = libelle_bandeau(groupe, (fin - debut) / (fin_axe_num - debut_axe_num))
        y0 = 1.075 if groupe is Groupe.FINANCEMENT else 1.01
        ax.add_patch(
            Rectangle(
                (debut, y0),
                fin - debut,
                0.055,
                transform=trans,
                clip_on=False,
                color=COULEURS_GROUPES[groupe],
                lw=0,
            )
        )
        ax.text(
            debut + (fin - debut) / 2,
            y0 + 0.0275,
            texte,
            transform=trans,
            ha="center",
            va="center",
            fontsize=6.5,
            fontweight="bold",
            clip_on=False,
        )

    for jalon, a_droite in zip(planning.jalons, etiquettes_a_droite(planning), strict=True):
        couleur = "#c00000" if jalon.nom == "Fin du projet" else "#444444"
        ax.axvline(jalon.date, color=couleur, lw=0.7, ls="--", zorder=2)
        ax.text(
            mdates.date2num(jalon.date) + (2 if a_droite else -2),
            0.995,
            f"◆ {jalon.nom}",
            transform=trans,
            rotation=90,
            ha="left" if a_droite else "right",
            va="top",
            fontsize=5.5,
            color=couleur,
            zorder=4,
        )

    ax.set_yticks(range(len(lignes)))
    ax.set_yticklabels(list(reversed(lignes)), fontsize=6.5)
    ax.set_ylim(-0.7, len(lignes) - 0.3)
    ax.set_xlim(debut_axe, fin_axe)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=_mois_graduations(planning)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_format_mois))
    ax.tick_params(axis="x", labelsize=6.5)
    ax.grid(axis="x", color="#dddddd", lw=0.5, zorder=1)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)

    types = [t for t in COULEURS_TYPES if t in set(df["Type"])]
    legende = [Patch(facecolor=COULEURS_TYPES[t], edgecolor="black", lw=0.4, label=t) for t in types]
    if planning.periodes_treve:
        legende.append(Patch(facecolor=COULEUR_TREVE, edgecolor="#999999", lw=0.4, label="Trêve de fin d'année"))
    ax.legend(
        handles=legende,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.07),
        ncol=len(legende),
        fontsize=6.5,
        frameon=False,
    )

    fig.tight_layout()
    tampon = io.BytesIO()
    fig.savefig(tampon, format="png")
    plt.close(fig)
    tampon.seek(0)
    return tampon


def _mois_graduations(planning: Planning) -> list[int]:
    mois = (planning.date_fin_affichage - planning.date_debut).days / 30.4
    pas = 1 if mois <= 14 else 2 if mois <= 30 else 3
    return list(range(1, 13, pas))


def _format_mois(valeur: float, _position) -> str:
    jour = mdates.num2date(valeur)
    return f"{MOIS_FR[jour.month - 1]} {jour.year}"
