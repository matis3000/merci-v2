# CRM MERCI

CRM et prospection d'un pilote associatif à Strasbourg : API FastAPI, front Next.js 16, landing statique, 287 tests sans réseau.

CRM interne de l'équipe MERCI pour le pilote de Strasbourg : il suit les 6 étapes du parcours client (Attirer, Capturer, Suivre, Relancer, Convertir, Fidéliser) pour les donateurs, les entreprises et les associations.

## Contenu

- `api/` : API FastAPI (SQLite en local, Postgres en production), migrations Alembic, tests pytest sans réseau.
- `web/` : CRM web Next.js 16 (React 19, CSS de la preview, sans Tailwind).
- `preview/` : maquette validée, référence visuelle du front.
- `landing/` : landing statique « Rejoindre le pilote », qui envoie ses inscriptions à `POST /public/inscription`.

## Lancement local en 3 commandes

Une seule fois, l'installation (depuis la racine du dépôt) :

```
cd api && /opt/homebrew/bin/python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt && cp .env.example .env && cd ..
cd web && npm install && cp .env.example .env.local && cd ..
```

Puis, chacune dans son terminal, depuis la racine du dépôt :

```
# 1. API sur http://127.0.0.1:8010
cd api && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload

# 2. CRM web sur http://127.0.0.1:3000
cd web && npm run dev

# 3. Landing sur http://127.0.0.1:5500
python3 -m http.server 5500 --bind 127.0.0.1 --directory landing
```

Connexion : `http://127.0.0.1:3000/connexion` avec l'adresse `ADMIN_EMAIL` (par défaut `valentin@merci.local`). En développement, l'écran affiche « Ouvrir le lien de développement » ; le message est aussi écrit dans `api/outbox/`.

Le navigateur n'appelle que `/api/*` sur le port 3000 : Next relaie vers l'API (cookie de session `HttpOnly` sur le domaine du web, pas de CORS). Seule la landing appelle l'API directement, d'où `CORS_ORIGINES`.

Les relances partent dans le créneau (par défaut du lundi au vendredi, de 9 h à 18 h, heure de Paris). En local, pour faire partir les messages en attente :

```
curl -X POST http://127.0.0.1:8010/cron/tick -H "X-Cron-Secret: dev-cron-secret"
```

Les e-mails sont écrits dans `api/outbox/` (un `.json` et un `.html` par message) tant que `RESEND_API_KEY` est vide.

## Variables d'environnement

### API (`api/.env`, modèle : `api/.env.example`)

| Variable | Rôle | Valeur locale |
|---|---|---|
| `MODE` | `development` ou `production` (la production refuse les secrets faibles et les fournisseurs factices) | `development` |
| `DATABASE_URL` | base de données | `sqlite:///./merci.db` |
| `WEB_URL` | adresse du CRM web (liens de connexion, logo des e-mails) | `http://127.0.0.1:3000` |
| `API_URL_PUBLIQUE` | adresse publique de l'API (liens de désinscription) | `http://127.0.0.1:8010` |
| `CORS_ORIGINES` | origines autorisées à appeler `/public/inscription` (la landing) | `http://127.0.0.1:5500,http://localhost:5500` |
| `TRUST_PROXY` | `true` derrière un proxy : IP lue dans `X-Forwarded-For` | `false` |
| `ADMIN_EMAIL`, `ADMIN_PRENOM` | admin du pilote, créé au démarrage | `valentin@merci.local`, `Valentin` |
| `JWT_SECRET`, `SESSION_JOURS` | signature des sessions et des liens de désinscription, durée de session en jours | valeur de développement, `7` |
| `CRON_SECRET` | en-tête `X-Cron-Secret` de `/cron/*` | `dev-cron-secret` |
| `CLE_APP_MERCI` | en-tête `X-Cle-App` de `/public/evenement` (App MERCI) | `dev-cle-app` |
| `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` | envoi réel des e-mails et signature des webhooks Resend ; vide = boîte locale `outbox/` | vides |
| `EMAIL_EXPEDITEUR`, `EMAIL_EXPEDITEUR_NOM` | expéditeur des e-mails | `bonjour@exemple.test`, `MERCI` |
| `OUTBOX_DIR` | dossier de la boîte locale | `outbox` |
| `LINKEDIN_FOURNISSEUR` | `factice` ou `connectsafely` | `factice` |
| `LINKEDIN_WEBHOOK_SECRET` | secret des webhooks LinkedIn | vide |
| `CONNECTSAFELY_API_KEY`, `CONNECTSAFELY_ACCOUNT_ID` | accès ConnectSafely | vides |
| `FRANCE_TRAVAIL_CLIENT_ID`, `FRANCE_TRAVAIL_CLIENT_SECRET` | offres d'emploi RSE (optionnel) | vides |
| `HUBSPOT_TOKEN` | jeton d'app privée HubSpot : contacts, organisations et affaires répliqués vers HubSpot (sens unique) ; vide = synchro factice, rien n'est envoyé | vide |

### Web (`web/.env.local`, modèle : `web/.env.example`)

| Variable | Rôle | Valeur locale |
|---|---|---|
| `API_URL` | cible de la réécriture `/api/*`, côté serveur Next uniquement | `http://127.0.0.1:8010` |

### Landing

L'adresse d'envoi du formulaire est l'attribut `data-endpoint` du formulaire `#form-pilote` (landing en ligne : `/api/public/inscription` ; recette locale : `data-endpoint-local`, `http://127.0.0.1:8010/public/inscription`). Le formulaire envoie le profil, le prénom, l'e-mail, la structure, `source_detail` lu dans `utm_source` de l'URL, le consentement avec le texte exact de la case, et un champ piège invisible.

## Ce qu'il reste à configurer pour la production

- **Domaine d'envoi et Resend** : créer le compte Resend, y vérifier le domaine d'envoi (enregistrements SPF, DKIM et DMARC chez le registrar), puis renseigner `RESEND_API_KEY`, `EMAIL_EXPEDITEUR` (une adresse de ce domaine) et `EMAIL_EXPEDITEUR_NOM`. Déclarer le webhook `https://<api>/webhooks/resend` dans Resend et recopier son secret dans `RESEND_WEBHOOK_SECRET`. L'offre gratuite plafonne à 100 e-mails par jour : à trancher avant l'ouverture du pilote.
- **Fournisseur LinkedIn** : renseigner `LINKEDIN_FOURNISSEUR=connectsafely`, connecter le compte LinkedIn de l'équipe chez ConnectSafely, renseigner ses variables, déclarer le webhook `https://<api>/webhooks/linkedin` et recopier son secret dans `LINKEDIN_WEBHOOK_SECRET`.
- **Liens des messages** : dans Réglages, renseigner le lien de prise de rendez-vous (utilisé par la séquence entreprise) et le lien de création de compte de l'App MERCI (utilisé à l'ouverture du pilote). Tant qu'un lien manque, l'envoi concerné passe en erreur visible ; il repart au tick suivant une fois le lien renseigné (trois essais au plus).
- **Adresses** : `WEB_URL` et `API_URL_PUBLIQUE` en https ; `DATABASE_URL` vers Postgres ; `TRUST_PROXY=true` derrière le proxy de l'hébergeur.
- **Secrets** : `JWT_SECRET` (32 caractères au moins), `CRON_SECRET` et `CLE_APP_MERCI` neufs ; `ADMIN_EMAIL` réel ; `MODE=production`.
- **Landing** : remplacer `data-endpoint` par l'URL publique de l'API (`https://<api>/public/inscription`) et ajouter le domaine de la landing à `CORS_ORIGINES`.
- **Tâches planifiées** : `POST /cron/tick` toutes les 15 minutes et `POST /cron/prospection` chaque jour à 6 h (heure de Paris), avec l'en-tête `X-Cron-Secret`.
- **Démarrage** : `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, un seul worker.

## Déploiement Vercel (un projet, trois services)

`vercel.json` à la racine déclare trois services dans un seul projet (doc : https://vercel.com/docs/services) :

| Service | Dossier | Public sur | Rôle |
|---|---|---|---|
| `api` | `api/` (FastAPI, Python 3.12) | `/api/*`, sur tous les domaines | API du CRM, inscriptions de la landing, désinscription, webhooks, cron |
| `web` | `web/` (Next.js) | domaine qui commence par `crm.` | CRM de l'équipe |
| `landing` | `landing/` (statique) | tous les autres domaines, dont l'adresse `*.vercel.app` | Landing « Rejoindre le pilote » |

- Vercel transmet au service le chemin public complet (`/api/contacts`) : l'API monte ses routes sous `/api` quand `VERCEL=1` (variable posée par Vercel), sans préfixe en local. `PREFIXE_API` force une autre valeur.
- Aucune liaison (`bindings`) : le CRM et la landing appellent l'API depuis le navigateur, en `/api/*` sur leur propre domaine. Le cookie `merci_session` reste sur `crm.<domaine>` et la landing n'a pas besoin de CORS. Sur Vercel, la réécriture Next vers `API_URL` est désactivée (elle ne sert qu'en local).
- La landing envoie le formulaire à `/api/public/inscription` ; servie en local (127.0.0.1 ou localhost), elle utilise `data-endpoint-local` (`http://127.0.0.1:8010/public/inscription`).
- Domaines : ajouter `<domaine>` et `crm.<domaine>` au projet. Tant que `crm.<domaine>` n'existe pas, le CRM n'est pas joignable (l'adresse `*.vercel.app` affiche la landing).
- Variables à poser dans le projet : `MODE=production`, `DATABASE_URL` (Postgres Neon, pas de SQLite sur Vercel), `WEB_URL=https://crm.<domaine>`, `API_URL_PUBLIQUE=https://<domaine>/api`, `TRUST_PROXY=true`, `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `EMAIL_EXPEDITEUR`, `EMAIL_EXPEDITEUR_NOM`, et les secrets de la section précédente.
- Migrations : `DATABASE_URL=<Neon> .venv/bin/alembic upgrade head` depuis `api/`, avant le premier déploiement et après chaque nouvelle migration.
- E-mails : Resend est déjà branché (`RESEND_API_KEY`). Sans clé, la boîte locale est écrite dans `/tmp/outbox`, perdue à chaque arrêt de fonction. Webhook Resend : `https://<domaine>/api/webhooks/resend`.
- Cron : `POST https://<domaine>/api/cron/tick` avec l'en-tête `X-Cron-Secret`. Le plan Hobby limite les tâches planifiées Vercel à une par jour : appeler le tick depuis un planificateur externe (GitHub Actions par exemple).
- Une requête dure 300 s au maximum (`maxDuration`).
- En ligne aujourd'hui : landing https://merci-v2.vercel.app, CRM https://merci-crm.vercel.app (domaine `merci-crm.vercel.app` ajouté au projet, routé vers `web`), base Neon `merci-pilote`. `EXIGER_FOURNISSEURS=false` tant que Resend et LinkedIn ne sont pas branchés : aucun e-mail ne part.
- Connexion sans Resend : `DATABASE_URL=<Neon> WEB_URL=https://merci-crm.vercel.app MODE=development ADMIN_EMAIL=<admin> .venv/bin/python -m scripts.lien_connexion` depuis `api/` affiche un lien valable 15 minutes.
- Tâches planifiées : `.github/workflows/cron.yml` appelle le tick toutes les 15 minutes et la prospection chaque jour (secret du dépôt `CRON_SECRET`).
- Vérification locale du build : `npx vercel@latest build --yes` (CLI 63 ou plus ; les versions 50 ne connaissent pas les services).

## Vérifications

```
cd api && .venv/bin/pytest -q
cd web && npx tsc --noEmit && npm run build
```

Aucun appel réseau pendant les tests : les fournisseurs (Resend, LinkedIn, registre des entreprises) sont simulés.

## Données

Base vide au départ : aucune donnée d'exemple n'est insérée.
