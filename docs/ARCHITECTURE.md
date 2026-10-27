# Architecture

## Vue d'ensemble

```
Navigateur ──HTTPS──▶ Vercel : Next.js (pages + passerelle BFF)
                          │  cookie httpOnly « oi_session » (jamais lisible en JS)
                          │  /api/auth/login|logout   /api/backend/*  (contrôle d'origine)
                          ▼
                     Render : FastAPI /api/v1  ◀── Render Cron Jobs (python -m app.jobs.*)
                          │  Authorization: Bearer <jeton opaque>
                          ▼
                     Neon : PostgreSQL          Resend (e-mails)   Stockage S3 compatible (documents)
                                                 Sources publiques (API Greenhouse/Lever/Arbeitnow, EACEA, RSS)
```

### Pourquoi une passerelle (BFF) ?

Le frontend (Vercel) et l'API (Render) sont sur deux domaines différents. Plutôt que des cookies
tiers (bloqués par Safari/Firefox) ou un jeton en `localStorage` (exposé au XSS) :

1. `POST /api/auth/login` (route Next.js) appelle l'API, reçoit le jeton et le place dans un cookie
   **httpOnly, Secure, SameSite=Lax**, sur le domaine Vercel.
2. Le navigateur n'appelle que `/api/backend/<chemin>` ; la passerelle ajoute
   `Authorization: Bearer <jeton>` et relaie vers `BACKEND_API_URL/api/v1/<chemin>`.
3. Toute requête modifiant l'état doit avoir un en-tête `Origin` (ou `Referer`) de la même origine
   (protection CSRF en plus de SameSite).
4. Le layout privé vérifie la session côté serveur (`/auth/me`) ; `proxy.ts` ne fait qu'une redirection
   rapide des visiteurs sans cookie.

L'API ne fait **jamais** confiance à un `user_id` fourni par le client : l'identité découle du jeton.

## Backend

| Couche | Rôle |
| --- | --- |
| `api/v1/*` | Routes REST, validation Pydantic, dépendances d'authentification (`deps.py`) |
| `services/*` | Logique métier : auth, profil, catalogue, candidatures/tâches, documents, matching, priorité, CV, IA, stockage |
| `workers/connectors` | Un connecteur par source + client HTTP « poli » (robots.txt, délai par hôte, Retry-After) |
| `workers/ingestion.py` | Validation → dédoublonnage → upsert idempotent → provenance → journal d'exécution |
| `workers/matching` | Moteur déterministe et explicable (fonctions pures) |
| `workers/notifications` | Client Resend / simulation, modèles HTML+texte, envoi dédupliqué |
| `jobs/*` | Points d'entrée des Cron Jobs, avec verrou à bail et code de sortie |

Choix notables :

- **SQLAlchemy synchrone + psycopg 3** : simple et robuste ; FastAPI exécute les routes synchrones dans un pool de threads.
- **Compatibilité PgBouncer (Neon pooled)** : requêtes préparées côté serveur désactivées (`prepare_threshold=None`),
  `pool_pre_ping`, recyclage à 5 min (Neon suspend le calcul inactif).
- **Verrous de jobs** dans la table `job_locks` (bail avec expiration) plutôt que des advisory locks de session,
  incompatibles avec un pooler en mode transaction.
- **Commits explicites** dans les routes : un échec d'écriture n'est jamais masqué derrière une réponse 200.
- **Aucun scheduler dans l'API** : seules les Cron Jobs exécutent les traitements planifiés (pas de doublons entre instances).

## Moteur de matching

Trois notions strictement séparées :

1. **Éligibilité** — `eligible` seulement si l'annonce publie des critères structurés (nationalités, niveaux,
   langues) **tous** satisfaits ; `ineligible` uniquement si un critère publié est **explicitement** incompatible ;
   sinon `unknown` (information manquante côté profil ou annonce).
2. **Compatibilité** (0–100) — cinq critères pondérés (configurables par variables `MATCH_WEIGHT_*`) :
   académique 30, compétences 25, financement 20, préférences 15, langues 10. Chaque critère peut être
   partiellement connu ; un critère **sans objet** (ex. aucune langue exigée) est retiré du dénominateur.
   `score = points / poids connus`, `fiabilité = poids connus / poids applicables` (affichée ; < 0,5 = « faible »).
   Vocabulaire bilingue FR/EN des domaines (ex. « Informatique » ↔ « Computer Science », domaines voisins à 0,6).
3. **Priorité** (`services/priority.py`) — calculée à la lecture : échéance, éligibilité, score, documents exigés
   manquants, temps de préparation vs jours restants, prochaine action en retard ; chaque point est justifié.

Les scores sont recalculés quand la version du profil, l'empreinte de l'annonce ou la version du moteur changent.
Le score n'est **pas** une probabilité d'acceptation (rappelé dans l'interface et les e-mails).

## Frontend

- App Router ; pages privées sous `src/app/(app)`, authentification sous `src/app/(auth)`.
- Données métier chargées côté client via SWR à travers la passerelle (aucun secret côté navigateur).
- Design system néo-brutaliste (`components/ui`) : tokens Tailwind v4 (`@theme` dans `globals.css`),
  boutons, champs, cartes, badges, tableaux responsives (cartes sur mobile), modales `<dialog>`, alertes,
  progression, toasts. Polices auto-hébergées (Archivo condensée pour les titres, Inter pour le texte).
- Accessibilité : libellés reliés, erreurs annoncées (`role="alert"`), focus visible jaune/noir, navigation
  clavier, lien d'évitement, menu mobile modal, contrastes AA.
- i18n : `src/i18n/fr.ts` (type `Dictionary`) — ajouter `en.ts` et un sélecteur pour l'anglais.

## Décisions et écarts assumés

| Sujet | Décision |
| --- | --- |
| Composants UI | Design system maison plutôt que shadcn/ui : contrôle total du style néo-brutaliste, aucune dépendance Radix nécessaire (`<dialog>` natif) |
| Stockage des documents | Interface interchangeable `local` / `s3` / `none` ; S3-compatible (ex. Cloudflare R2) recommandé en production ; Vercel Blob non retenu (API privée moins standard) |
| Téléversement | 4 Mo max : la passerelle Vercel limite le corps des requêtes à ~4,5 Mo |
| Assistant IA | SDK officiel Anthropic derrière une interface `AIProvider` ; désactivé sans `AI_PROVIDER`/`AI_API_KEY` |
| Python | `app/workers` et `app/jobs` dans le paquet `app` (au lieu de `backend/workers`) pour un import unique |
