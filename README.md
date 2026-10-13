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
- **Recherche de financement** en parallèle des études.
- **Gantt mis à jour en direct** avec un bandeau par catégorie, les jalons clés (décision des élus,
  MOE recrutée, dépôt du PC/DP, marchés signés, réception, fin du projet) et une ligne « aujourd'hui ».
- **Indicateurs** : date de fin, durée totale, part des délais de validation.
- **Exports** : planning Excel (feuilles Résumé, Planning, Jalons), CSV (compatible Excel FR) et image
  du Gantt (icône 📷).
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
| Tests cassés (modules `config`/`gantt` inexistants) | 51 tests pytest, dont des tests de l'interface (`AppTest`) |
| README non à jour | README, CI GitHub Actions (Python 3.11 à 3.14), ruff |
| Pas d'export ni de date de fin | Excel, CSV, JSON, jalons, indicateurs |

## Structure

```
app.py                      Interface Streamlit
renovation_gantt/
├── phases.py               États, phases, durées par défaut, glossaire
├── planning.py             Calcul des dates et des jalons (sans Streamlit)
├── charts.py               Diagramme de Gantt Plotly
└── export.py               Excel / CSV / scénarios JSON
tests/                      Tests pytest
images/                     Logo ACTEE
```

Pour modifier une durée par défaut ou ajouter une phase, il suffit d'éditer
`renovation_gantt/phases.py` : l'interface, le Gantt et les exports suivent automatiquement.

## Licence

MIT — voir [LICENSE](LICENSE).
