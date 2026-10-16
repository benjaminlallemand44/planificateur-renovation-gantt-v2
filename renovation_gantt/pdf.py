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

from .budget import Budget  # noqa: E402
from .charts import COULEUR_TREVE, COULEURS_TYPES, etiquettes_a_droite, libelle_bandeau  # noqa: E402
from .export import indicateurs  # noqa: E402
from .phases import COULEURS_GROUPES, EtatProjet, Groupe  # noqa: E402
from .planning import Planning  # noqa: E402

BLEU = (9, 21, 166)
MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
_EMOJIS = re.compile("[\U0001f000-\U0001faff☀-➿⬀-⯿️‍]")


def texte_sans_emoji(texte: str) -> str:
    return re.sub(r"\s+", " ", _EMOJIS.sub("", texte)).strip()


def planning_vers_pdf(
    planning: Planning,
    etat: EtatProjet | None = None,
    logo: Path | None = None,
    edition: date | None = None,
    nom_projet: str = "",
    budget: Budget | None = None,
) -> bytes:
    """PDF du planning ; une page « Budget et plan de financement » s'ajoute si un budget est renseigné."""
    if planning.taches.empty:
        raise ValueError("Le planning ne contient aucune tâche à exporter.")
    edition = edition or date.today()

    pdf = _Document(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    polices = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdf.add_font("DejaVu", "", polices / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", polices / "DejaVuSans-Bold.ttf")

    # Page 1 : en-tête et diagramme de Gantt
    pdf.add_page()
    _entete(pdf, etat, logo, edition, nom_projet)
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

    if budget is not None and budget.total_ttc > 0:
        _pages_budget(pdf, budget, planning)
    return bytes(pdf.output())


def _euros(montant: float) -> str:
    return f"{montant:,.0f} €".replace(",", "\u00a0")


def _pct(valeur: float) -> str:
    return f"{valeur:.1f} %".replace(".", ",")


def _pages_budget(pdf: FPDF, budget: Budget, planning: Planning) -> None:
    pdf.add_page()
    _titre_section(pdf, "Coût de l'opération")
    couts = budget.couts()
    lignes = [("Poste", "HT", "TVA", "TTC")]
    lignes += [(r.Poste, _euros(r.HT), _euros(r.TVA), _euros(r.TTC)) for r in couts.itertuples() if r.HT]
    lignes.append(("Total", _euros(budget.total_ht), _euros(budget.total_tva), _euros(budget.total_ttc)))
    _tableau(pdf, lignes, (110, 32, 32, 32), alignements=("LEFT", "RIGHT", "RIGHT", "RIGHT"))
    pdf.ln(4)

    _titre_section(pdf, "Plan de financement")
    lignes = [("Financeur", "Statut", "Montant", "Part du coût HT")]
    base = budget.total_ht
    for f in budget.financeurs:
        if f.aide(base):
            nom = texte_sans_emoji(f.nom) + ("" if f.public else " (aide privée)")
            lignes.append((nom, f.statut.value, _euros(f.aide(base)), _pct(100 * f.aide(base) / base)))
    lignes += [
        ("FCTVA attendu", "", _euros(budget.fctva), ""),
        ("Reste à charge net de la collectivité", "", _euros(budget.reste_a_charge), ""),
    ]
    _tableau(pdf, lignes, (110, 40, 32, 32), alignements=("LEFT", "LEFT", "RIGHT", "RIGHT"))
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(*(200, 30, 30) if budget.depasse_plafond else (60, 60, 60))
    pdf.multi_cell(
        0,
        4.5,
        f"Aides publiques : {_pct(budget.taux_aides_publiques)} du coût HT "
        + (
            "— au-delà du plafond de 80 % (participation minimale de 20 % du maître d'ouvrage, CGCT art. L1111-10)."
            if budget.depasse_plafond
            else "(plafond : 80 %, CGCT art. L1111-10)."
        ),
    )
    pdf.ln(3)

    echeancier = budget.echeancier(planning)
    if not echeancier.empty:
        _titre_section(pdf, "Échéancier budgétaire (crédits de paiement)")
        lignes = [("Année", "Dépenses TTC", "Aides", "FCTVA", "Solde", "Cumul")]
        lignes += [
            (str(int(r.Année)), *(_euros(v) for v in (r[2], r.Aides, r.FCTVA, r.Solde, r.Cumul)))
            for r in echeancier.itertuples()
        ]
        _tableau(pdf, lignes, (25, 35, 35, 35, 35, 35), alignements=("LEFT",) + ("RIGHT",) * 5)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(
            0,
            4.5,
            f"Besoin de financement maximal : {_euros(-echeancier['Cumul'].min())}. Hypothèses : factures payées "
            f"à {budget.delai_paiement_jours} jours, avance de {_pct(budget.avance_entreprises)} et retenue de "
            f"garantie de {_pct(budget.retenue_garantie)} sur les marchés de travaux, aides versées pour "
            f"{_pct(budget.acompte_aides)} au démarrage des travaux et {_pct(budget.solde_aides)} après la réception.",
        )


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


def _entete(pdf: FPDF, etat: EtatProjet | None, logo: Path | None, edition: date, nom_projet: str = "") -> None:
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
    parties = [texte_sans_emoji(nom_projet)] if nom_projet else []
    if etat is not None:
        parties.append(f"Situation de départ : {EtatProjet(etat).value}")
    parties.append(f"Édité le {edition:%d/%m/%Y}")
    pdf.multi_cell(0, 4.5, "  —  ".join(parties))
    pdf.set_y(max(pdf.get_y(), 24))


def _titre_section(pdf: FPDF, titre: str) -> None:
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*BLEU)
    pdf.cell(0, 7, titre, new_x="LMARGIN", new_y="NEXT")


def _tableau(
    pdf: FPDF,
    lignes: list[tuple[str, ...]],
    largeurs: tuple[int, ...],
    alignements: tuple[str, ...] | None = None,
) -> None:
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
            for i, valeur in enumerate(ligne):
                row.cell(str(valeur), align=alignements[i] if alignements else None)


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
