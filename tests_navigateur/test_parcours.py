"""Parcours utilisateur complets dans le navigateur."""

import json
import re

from playwright.sync_api import Page, expect


def _attendre_calcul(page: Page) -> None:
    page.wait_for_timeout(600)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=30_000)
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)


def _choisir_etat(page: Page, libelle: str) -> None:
    page.locator('[data-testid="stSelectbox"]').filter(has_text="Où en êtes-vous").click()
    page.get_by_role("option", name=libelle).click()
    _attendre_calcul(page)


def _ouvrir_budget(page: Page, montant: int) -> None:
    page.get_by_role("tab", name="💶 Budget et financement").click()
    champ = page.get_by_role("spinbutton", name="Montant estimé des travaux")
    champ.fill(str(montant))
    champ.press("Enter")
    _attendre_calcul(page)


def _saisir_cellule(page: Page, ligne: int, decalage_colonne: int, valeur: str) -> None:
    """Saisit une valeur dans le plan de financement : ligne (à partir de 0), colonne à droite de « Financeur »."""
    grille = page.locator('.st-key-editeur_financeurs [data-testid="stDataFrame"]')
    grille.scroll_into_view_if_needed()
    boite = grille.bounding_box()
    # Le tableau est dessiné dans un canvas : clic sur la cellule « Financeur » de la ligne (lignes de 35 px).
    page.mouse.click(boite["x"] + 120, boite["y"] + 35 + 35 * ligne + 17)
    for _ in range(decalage_colonne):
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")  # ouvre l'éditeur de la cellule
    page.wait_for_timeout(300)
    page.keyboard.press("Control+A")
    page.keyboard.type(valeur, delay=50)
    page.keyboard.press("Enter")
    _attendre_calcul(page)


def test_parcours_planning_et_exports(page: Page):
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    expect(page.locator('[data-testid="stMetric"]').first).to_contain_text("Date de fin estimée")
    expect(page.locator(".js-plotly-plot").first).to_be_visible()
    with page.expect_download() as telechargement:
        page.get_by_role("button", name="Planning PDF (à présenter)").click()
    assert telechargement.value.suggested_filename == "planning_renovation.pdf"


def test_region_departement_et_vacances(page: Page):
    page.locator('[data-testid="stSelectbox"]').filter(has=page.get_by_text("Région", exact=True)).click()
    page.keyboard.type("Pays de la Loire")
    page.get_by_role("option", name="Pays de la Loire").click()
    _attendre_calcul(page)
    page.locator('[data-testid="stSelectbox"]').filter(has=page.get_by_text("Département", exact=True)).click()
    page.keyboard.type("44")
    page.get_by_role("option", name="44 – Loire-Atlantique").click()
    _attendre_calcul(page)
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    page.get_by_text("Ce bâtiment est-il un bâtiment scolaire ?").click()
    _attendre_calcul(page)
    expect(page.get_by_text(re.compile("Loire-Atlantique est en zone B"))).to_be_visible()
    expect(page.get_by_text(re.compile("Les travaux démarrent le"))).to_be_visible()


def test_plan_de_financement_saisi_dans_le_tableau(page: Page):
    """Le tableau modifiable des financeurs : saisie d'un taux, contrôle du plafond de 80 %."""
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    _ouvrir_budget(page, 800_000)
    # DETR (ligne 0) : 50 % ; DSIL (ligne 1) : 40 % → 90 % d'aides publiques.
    _saisir_cellule(page, 0, 2, "50")
    expect(page.get_by_text(re.compile(r"Participation du maître d'ouvrage : 50"))).to_be_visible()
    _saisir_cellule(page, 1, 2, "40")
    expect(page.get_by_text(re.compile("participation minimale de 20 % du maître d'ouvrage n'est pas"))).to_be_visible()


def test_sauvegarde_et_rechargement_du_scenario(page: Page, tmp_path):
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    _ouvrir_budget(page, 500_000)
    _saisir_cellule(page, 0, 2, "25")
    page.get_by_role("tab", name="📅 Planification").click()
    with page.expect_download() as telechargement:
        page.get_by_role("button", name="Scénario (.json)").click()
    fichier = tmp_path / "scenario.json"
    telechargement.value.save_as(fichier)
    donnees = json.loads(fichier.read_text(encoding="utf-8"))
    assert donnees["budget"]["travaux_ht"] == 500_000
    assert donnees["budget"]["financeurs"][0]["taux"] == 25

    # Rechargement dans une session neuve.
    page.goto(page.url)
    page.wait_for_selector('[data-testid="stFileUploaderDropzoneInput"]', state="attached", timeout=30_000)
    page.locator('[data-testid="stFileUploaderDropzoneInput"]').set_input_files(fichier)
    _attendre_calcul(page)
    expect(page.get_by_text(re.compile("Scénario « scenario.json » chargé"))).to_be_visible()
    page.get_by_role("tab", name="💶 Budget et financement").click()
    expect(page.get_by_role("spinbutton", name="Montant estimé des travaux")).to_have_value("500000")


def test_ajout_d_un_financeur(page: Page):
    """Une ligne ajoutée est pré-remplie et son montant est bien pris en compte."""
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    _ouvrir_budget(page, 400_000)
    grille = page.locator('.st-key-editeur_financeurs [data-testid="stDataFrame"]')
    grille.scroll_into_view_if_needed()
    grille.hover()
    # La barre d'outils de la grille peut être recouverte (en-tête de l'appli, grille) selon la taille d'écran :
    # on déclenche le clic directement sur le bouton plutôt qu'aux coordonnées de la souris.
    page.locator('.st-key-editeur_financeurs [data-testid="stElementToolbarButton"]').filter(
        has=page.locator('[aria-label="Add row"]')
    ).first.locator("button").dispatch_event("click")
    page.keyboard.press("Escape")
    _attendre_calcul(page)
    # La ligne ajoutée est la 7e (index 6) : on la renomme puis on saisit le montant (3 colonnes à droite du nom).
    _saisir_cellule(page, 6, 0, "Programme ACTEE")
    _saisir_cellule(page, 6, 3, "9000")
    expect(page.get_by_text(re.compile(r"Aides publiques \(1,8 % du HT\)"))).to_be_visible()


def test_rien_n_est_memorise_sans_consentement(page: Page):
    """Case « Mémoriser » décochée (par défaut) : rien n'est écrit dans le navigateur."""
    nom = page.get_by_role("textbox", name="Nom du projet")
    nom.fill("École Jules Ferry")
    nom.press("Enter")
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    assert page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('planificateur'))") == []
    page.reload()
    page.wait_for_selector('[data-testid="stSelectbox"]', timeout=30_000)
    _attendre_calcul(page)
    expect(page.get_by_role("textbox", name="Nom du projet")).to_have_value("")


def test_sauvegarde_automatique_dans_le_navigateur(page: Page):
    """Case cochée : les saisies reviennent après un rechargement ; la décocher les efface."""
    page.get_by_text("Mémoriser mes saisies sur cet appareil", exact=True).click()
    _attendre_calcul(page)
    nom = page.get_by_role("textbox", name="Nom du projet")
    nom.fill("École Jules Ferry")
    nom.press("Enter")
    _choisir_etat(page, "Nous venons de sélectionner notre équipe de maitrise d'oeuvre")
    _ouvrir_budget(page, 750_000)
    # La sauvegarde est écrite par le navigateur juste après le calcul : on attend qu'elle contienne le montant.
    page.wait_for_function(
        "() => (localStorage.getItem('planificateur-renovation-gantt:scenario') || '').includes('750000')"
    )

    page.reload()
    page.wait_for_selector('[data-testid="stSelectbox"]', timeout=30_000)
    _attendre_calcul(page)
    expect(page.get_by_role("textbox", name="Nom du projet")).to_have_value("École Jules Ferry")
    page.get_by_role("tab", name="💶 Budget et financement").click()
    expect(page.get_by_role("spinbutton", name="Montant estimé des travaux")).to_have_value("750000")

    expect(page.get_by_role("checkbox", name="Mémoriser mes saisies sur cet appareil")).to_be_checked()

    # Décocher la case efface la sauvegarde.
    page.get_by_text("Mémoriser mes saisies sur cet appareil", exact=True).click()
    _attendre_calcul(page)
    assert page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('planificateur'))") == []
    page.reload()
    page.wait_for_selector('[data-testid="stSelectbox"]', timeout=30_000)
    _attendre_calcul(page)
    expect(page.get_by_role("textbox", name="Nom du projet")).to_have_value("")


IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def test_affichage_smartphone(navigateur, url_app):
    """Sur un écran de smartphone : libellés courts, réglages repliés, Gantt compact, pas de défilement horizontal."""
    contexte = navigateur.new_context(viewport={"width": 390, "height": 844}, user_agent=IPHONE, locale="fr-FR")
    page = contexte.new_page()
    try:
        page.goto(url_app)
        page.wait_for_selector('[data-testid="stSelectbox"]', timeout=30_000)
        _attendre_calcul(page)
        champ = page.locator('[data-testid="stSelectbox"]').filter(has_text="Où en êtes-vous").locator("input").first
        champ.scroll_into_view_if_needed()
        champ.click()
        # Libellé court propre au smartphone : on le tape pour filtrer la liste, puis on valide.
        page.keyboard.type("Équipe de MOE")
        expect(page.get_by_role("option", name="Équipe de MOE sélectionnée")).to_be_visible()
        page.keyboard.press("Enter")
        _attendre_calcul(page)
        expect(page.locator(".js-plotly-plot").first).to_be_visible()
        expect(page.locator(".js-plotly-plot").first).to_contain_text("Gantt du projet")
        # Réglages des phases repliés : le Gantt n'est pas relégué en bas d'une très longue page.
        expect(page.get_by_text("DIAG - Diagnostic", exact=False).first).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
    finally:
        contexte.close()
