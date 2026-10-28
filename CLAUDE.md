# CLAUDE.md

CRM MERCI : CRM interne de l'équipe MERCI (pilote de Strasbourg).

## Documents qui font foi

- Architecture et spec produit : documents de conception tenus hors du dépôt (arborescence, modèle de données, contrat d'API, décisions).
- Référence visuelle du front : `preview/` (ne pas modifier).

## Règles

- TDD : tests du lot d'abord, rouges, puis code jusqu'au vert.
- Tests sans réseau : fournisseurs factices, `httpx.MockTransport`.
- Aucune donnée inventée : base vide, aucun seed. Fixtures de test visiblement fictives (`Entreprise Test 1`, `prenom@exemple.test`).
- Textes visibles en français, vouvoiement. Pas de tiret cadratin ni demi-cadratin : deux-points ou virgules.
- Dates en UTC naïf via `app.temps.maintenant()` uniquement.
- Python 3.11 (`api/.venv`). Lancement : voir `README.md`.

## Vérifications

```
cd api && .venv/bin/pytest -q
```
