# Opportunity Intelligence

Application web personnelle qui **recherche automatiquement des stages et des bourses de master**,
évalue leur pertinence de façon **explicable**, suit les candidatures, gère les documents et envoie
des **alertes e-mail** — sans jamais envoyer une candidature à votre place.

> Principe : automatiser la recherche, l'analyse, le classement et les rappels ; la soumission
> reste toujours une action humaine explicitement confirmée.

## Fonctionnalités

| Domaine | Ce qui est implémenté |
| --- | --- |
| Authentification | Compte admin créé par CLI/amorçage ; inscription publique **désactivable** (`ALLOW_REGISTRATION`, adresse e-mail confirmée obligatoire), Argon2id, sessions opaques hachées, limitation de débit, réinitialisation du mot de passe par e-mail, cookie httpOnly + contrôle d'origine (CSRF) |
| Profil | Identité, nationalités, études, compétences, expériences, projets, engagements, langues (CECRL), préférences ; **import de CV PDF** avec écran de confirmation (rien n'est inventé ni enregistré automatiquement) |
| Documents | Espace privé (PDF, DOCX, PNG, JPEG, texte), contrôle du type réel par signature binaire, versions, notes, association aux candidatures, téléchargement par URL signée (S3) ou flux authentifié |
| Catalogue | Stages et bourses avec provenance, filtres serveur (type, pays, domaine, organisme, niveau, financement, échéance, éligibilité, score, statut), recherche plein texte, tri, pagination, favoris |
| Collecte | Connecteurs Greenhouse, Lever, Arbeitnow, Erasmus Mundus (EACEA), RSS ; validation, normalisation, dédoublonnage multi-niveaux, idempotence, robots.txt, limitation de débit, journal des exécutions |
| Matching | Moteur déterministe : **éligibilité** (eligible / ineligible / unknown), **compatibilité** /100 pondérée avec fiabilité, **priorité** explicable ; recalcul automatique |
| Candidatures | Pipeline 8 statuts (en français), Kanban / tableau / calendrier, historique, tâches, documents, relances ; **confirmation humaine obligatoire** avant « Envoyée » |
| Alertes | Resend (ou mode simulation), nouvelles opportunités, récapitulatif quotidien/hebdomadaire, rappels J-14/7/3/1, tâches, modifications, erreurs de collecte ; déduplication et journal |
| Tableau de bord | Indicateurs réels, échéances 7/30 j avec urgence expliquée, tâches en retard, pipeline, état des sources, collectes, e-mails, erreurs |
| Assistant IA | Facultatif (désactivé sans clé) : brouillons modifiables à partir du profil uniquement, informations manquantes signalées |

## Stack

- **Frontend** : Next.js 16 (App Router), React 19, TypeScript strict, Tailwind CSS v4, React Hook Form + Zod, SWR, Recharts, lucide-react — design system **néo-brutaliste** maison (`apps/web/src/components/ui`).
- **Backend** : Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.1 (psycopg 3), Alembic, HTTPX, Pytest.
- **Base** : PostgreSQL (Neon en production).
- **Hébergement** : Vercel (frontend), Render (API + Cron Jobs), Resend (e-mails).

```
.
├── apps/web/                 # Frontend Next.js (BFF : /api/auth/*, /api/backend/*)
│   ├── src/app/              # Pages (App Router) et route handlers
│   ├── src/components/       # Design system + layout
│   ├── src/features/         # Écrans par domaine
│   ├── src/lib/              # Client API, formatage, types, couche serveur
│   ├── src/i18n/             # Dictionnaire (fr), prêt pour l'anglais
│   ├── tests/unit/           # Vitest + Testing Library
│   └── e2e/                  # Playwright
├── backend/
│   ├── app/api/v1/           # Routes REST /api/v1
│   ├── app/core/             # Config, sécurité, erreurs, logs, temps, texte
│   ├── app/db/               # Session SQLAlchemy, verrous de jobs
│   ├── app/models/           # Modèles (19 tables)
│   ├── app/schemas/          # Schémas Pydantic
│   ├── app/services/         # Logique métier
│   ├── app/workers/          # Connecteurs, ingestion, matching, notifications
│   ├── app/jobs/             # Commandes planifiées (python -m app.jobs.*)
│   ├── migrations/           # Alembic
│   └── tests/                # Pytest (PostgreSQL réel) + jeux de test
├── docs/                     # Documentation technique
├── scripts/e2e.sh            # Tests end-to-end locaux/CI
├── render.yaml               # Blueprint Render (API + cron jobs)
└── .env.example              # Variables (valeurs fictives)
```

## Prérequis

- Python 3.12, Node.js ≥ 20.9 (22 recommandé), PostgreSQL ≥ 14 (local) ou une base Neon.

## Installation locale

```bash
# 1. Base de données locale
createdb oi_dev && createdb oi_test

# 2. Backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp ../.env.example .env            # puis renseigner DATABASE_URL et SECRET_KEY
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli seed-sources
.venv/bin/python -m app.cli create-admin --email vous@example.com   # mot de passe demandé (12 car. min.)
.venv/bin/uvicorn app.main:app --reload --port 8000                  # docs : http://localhost:8000/docs

# 3. Frontend (autre terminal)
cd apps/web
npm ci
cp .env.example .env.local
npm run dev                                                         # http://localhost:3000
```

## Commandes utiles

| Action | Commande |
| --- | --- |
| Tests backend | `cd backend && .venv/bin/pytest` (base `oi_test` ou `TEST_DATABASE_URL`) |
| Lint backend | `cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests` |
| Tests frontend | `cd apps/web && npm test` |
| Lint / types frontend | `cd apps/web && npm run lint && npm run typecheck` |
| Build frontend | `cd apps/web && npm run build` |
| End-to-end | `npm --prefix apps/web run build && bash scripts/e2e.sh` (base locale `oi_e2e`) |
| Nouvelle migration | `cd backend && .venv/bin/alembic revision --autogenerate -m "message"` |
| Appliquer les migrations | `cd backend && .venv/bin/alembic upgrade head` |
| Tester une source (à blanc) | `cd backend && .venv/bin/python -m app.cli test-source --key greenhouse-internships` |
| Lancer une collecte | `cd backend && .venv/bin/python -m app.jobs.collect_opportunities` |
| Vérifier la configuration | `cd backend && .venv/bin/python -m app.cli check-config` |

## Déploiement

Voir [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) : Neon (base), Render (Blueprint `render.yaml`), Vercel
(racine `apps/web`), Resend. Variables : [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Base de données](docs/DATABASE.md) · [API](docs/API.md) ·
[Déploiement](docs/DEPLOYMENT.md) · [Environnement](docs/ENVIRONMENT.md) · [Sécurité](docs/SECURITY.md) ·
[Tests](docs/TESTING.md) · [Connecteurs](docs/CONNECTORS.md) · [Exploitation](docs/OPERATIONS.md) ·
[État d'avancement](docs/STATUS.md)

## Limites connues

- Les connecteurs n'ont **pas pu être vérifiés contre les sources réelles** depuis l'environnement de
  développement (réseau sortant restreint) : ils sont testés sur des jeux de données reproduisant les formats
  documentés. Chaque source est **désactivée par défaut** et se vérifie en un clic (« Tester ») une fois déployée.
- Pas d'OCR : un CV scanné (image) ne produit aucune suggestion.
- Téléversement limité à 4 Mo (limite des fonctions Vercel traversées par la passerelle).
- Le plan gratuit Render met l'API en veille après inactivité (premier appel lent).
- Interface en français uniquement (architecture i18n prête pour l'anglais).
