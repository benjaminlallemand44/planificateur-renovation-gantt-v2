# Planificateur de rénovation énergétique — v2

Application **Streamlit** qui aide un maître d'ouvrage public à planifier un projet de
rénovation énergétique : études préalables, AMO programmiste, recrutement de la maîtrise
d'œuvre puis phases de la **loi MOP** (DIAG → APS → APD → PRO → DCE → ACT → VISA → DET → AOR).

Cette version est une refonte du projet
[Projet_renovation_Gantt](https://github.com/benjaminlallemand44/Projet_renovation_Gantt).

![Aperçu du diagramme de Gantt](docs/apercu_gantt.png)

## Lancer l'application

```bash
pip install -r requirements.txt
streamlit run app.py
```

Pour développer (tests et linter) :

```bash
pip install -r requirements-dev.txt
pytest
ruff check . && ruff format --check .
```

Déploiement sur [Streamlit Community Cloud](https://share.streamlit.io) : choisir ce dépôt et le
fichier `app.py`.

## Fonctionnalités

- **5 états de départ** du projet : de « pas encore d'audit » à « MOE sélectionnée ».
- **Durées modifiables** (en semaines), avec les minimums réglementaires (APS ≥ 3, APD ≥ 6, PRO ≥ 4).
- **Délais de validation du maître d'ouvrage** affichés en orange, et modifiables (option de la barre latérale).
- **Dossiers de financement** (DETR, DSIL, Fonds vert…) montés après l'APD (ou dès le début) : les marchés de
  travaux ne sont pas signés avant l'accusé de dossier complet, la signature valant commencement d'exécution.
- **Recrutement du contrôleur technique et du CSPS** en parallèle du DIAG ; le dépôt du dossier d'autorisation
  l'attend.
- **Attentes visibles** (en jaune) quand un prérequis n'est pas prêt : autorisation, financement, CT/CSPS.
- **Bâtiment scolaire** : l'outil demande si le bâtiment est scolaire et propose de caler les travaux sur les
  vacances d'été (démarrage au début de l'été, ou travaux uniquement l'été, sur plusieurs étés si nécessaire).
  Il indique alors combien de semaines il faudrait gagner en amont pour démarrer un été plus tôt.
- **Garantie de parfait achèvement** : un an après la réception, affichée sans allonger la durée du projet.
- **Autorisation d'urbanisme** (DP, PC, PC d'un ERP, autorisation de travaux ERP) avec son **délai d'instruction
  réglementaire** de droit commun, l'éventuelle majoration pour avis de l'ABF et, en option, la purge du recours
  des tiers. L'instruction se déroule en parallèle des études PRO / DCE ; les travaux attendent l'autorisation, et
  l'attente éventuelle est chiffrée.
- **Trêve de fin d'année** (2 semaines par défaut, jusqu'au 1er janvier) : les phases qui la traversent sont
  prolongées d'autant, tandis que les délais réglementaires continuent de courir.
- **Gantt mis à jour en direct** avec un bandeau par catégorie, les jalons clés (décision des élus,
  MOE recrutée, dépôt du PC/DP, marchés signés, réception, fin du projet) et une ligne « aujourd'hui ».
- **Indicateurs** : date de fin, durée totale, part des délais de validation.
- **Exports** : **PDF A4 paysage prêt à présenter** (Gantt, synthèse, jalons, détail des phases),
  Excel (feuilles Résumé, Planning, Jalons), CSV (compatible Excel FR), **jalons au format agenda (.ics)** pour
  Outlook ou Google Agenda, et image du Gantt (icône 📷).
- **Scénarios** : enregistrer ses paramètres en JSON et les recharger plus tard.
- **Glossaire** complet des phases de la loi MOP (y compris VISA et DET), et définitions affichées au survol des barres.

## Ce qui change par rapport à la v1

| v1 | v2 |
|---|---|
| Un script unique de 370 lignes | Package `renovation_gantt/` (métier, calcul, graphique, export) séparé de l'interface `app.py` |
| ESQ affichée par erreur sur le Gantt | ESQ masquée comme prévu |
| Définitions vides au survol (recherche dans le glossaire erronée) | Glossaire indexé par identifiant de phase |
| VISA et DET absents du glossaire | Glossaire complet |
| Pas de bandeau ni de délai MO pour l'AMO | Bandeau AMO et délai de validation |
| Gantt effacé à chaque modification (bouton) | Gantt recalculé en direct |
| Tests cassés (modules `config`/`gantt` inexistants) | 94 tests pytest, dont des tests de l'interface (`AppTest`) |
| README non à jour | README, CI GitHub Actions (Python 3.11 à 3.14), ruff |
| Pas d'export ni de date de fin | Excel, CSV, JSON, jalons, indicateurs |

## Structure

```
app.py                      Interface Streamlit
renovation_gantt/
├── phases.py               États, phases, durées par défaut, glossaire
├── planning.py             Calcul des dates et des jalons (sans Streamlit)
├── charts.py               Diagramme de Gantt Plotly
├── export.py               Excel / CSV / scénarios JSON
└── pdf.py                  Export PDF (Gantt matplotlib + mise en page fpdf2)
tests/                      Tests pytest
images/                     Logo ACTEE
```

Pour modifier une durée par défaut ou ajouter une phase, il suffit d'éditer
`renovation_gantt/phases.py` : l'interface, le Gantt et les exports suivent automatiquement.

## Durées par défaut

Ordres de grandeur pour une rénovation énergétique de bâtiment public, à ajuster projet par projet :

| Phase | Durée | Validation MO |
|---|---|---|
| Signature des marchés de MOE | 3 sem. | — |
| Recrutement CT / CSPS (en parallèle) | 8 sem. | — |
| DIAG | 6 sem. | 2 sem. |
| APS / APD | 4 / 8 sem. | 2 / 5 sem. |
| PRO / DCE | 5 / 4 sem. | 3 / 2 sem. |
| ACT (consultation, analyse, attribution) | 10 sem. | 2 sem. |
| Période de préparation (VISA) | 6 sem. | — |
| Travaux (DET) | 24 sem. | — |
| AOR | 4 sem. | — |
| Dossiers de financement (jusqu'au dossier complet) | 12 sem. | — |

## Délais réglementaires retenus

| Autorisation | Délai d'instruction | Référence |
|---|---|---|
| Déclaration préalable | 1 mois (+1 mois avec avis ABF) | C. urb. R423-23, R423-24 |
| Permis de construire | 3 mois (+1 mois avec avis ABF) | C. urb. R423-23, R423-24 |
| Autorisation de travaux ERP | 4 mois | Code de la construction et de l'habitation |
| Permis de construire d'un ERP | 5 mois | C. urb. R423-28 |
| Recours des tiers (option) | 2 mois après affichage | C. urb. R600-2 |

Ce sont des délais de droit commun : un dossier incomplet ou des consultations supplémentaires peuvent les
allonger. Ils se modifient dans `renovation_gantt/phases.py`.

## Licence

MIT — voir [LICENSE](LICENSE).
