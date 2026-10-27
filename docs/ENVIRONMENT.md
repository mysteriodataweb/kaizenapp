# Variables d'environnement

Ne jamais versionner de vraies valeurs. Modèle : [`.env.example`](../.env.example).
Local : `backend/.env` (lu automatiquement) et `apps/web/.env.local`.

## Backend (Render : groupe « opportunity-intelligence-shared », utilisé par l'API et les Cron Jobs)

| Variable | Obligatoire | Usage | Exemple / valeur |
| --- | --- | --- | --- |
| `DATABASE_URL` | **oui** | Connexion Neon (chaîne **pooled**, `-pooler` dans l'hôte), `postgres://`/`postgresql://` acceptés | `postgresql://user:***@ep-xxx-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require` |
| `DATABASE_MIGRATION_URL` (ou `DATABASE_URL_UNPOOLED`) | recommandé | Connexion **directe** Neon pour Alembic ; `DATABASE_URL_UNPOOLED` est le nom écrit par `neon deploy` / l'intégration Neon | idem sans `-pooler` |
| `APP_ENV` | oui | `production` active les contrôles stricts et masque /docs | `production` |
| `SECRET_KEY` | **oui** (≥ 32 car. en prod) | Empreintes HMAC (limitation de débit par IP) | générée par Render (`generateValue`) |
| `FRONTEND_URL` | oui | Liens dans les e-mails (réinitialisation, analyses) | `https://opportunity-intelligence.vercel.app` |
| `CORS_ORIGINS` | oui | Origines autorisées (séparées par virgules) | URL Vercel |
| `DEFAULT_TIMEZONE` | non | Fuseau des nouveaux comptes | `Europe/Paris` |
| `LOG_LEVEL` | non | Niveau de logs | `INFO` |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | une fois | Crée le compte admin au démarrage **si aucun compte n'existe** ; supprimer le mot de passe ensuite | — |
| `RESEND_API_KEY` | non | E-mails réels ; absent ⇒ **mode simulation** | `re_…` |
| `EMAIL_FROM` | avec Resend | Expéditeur d'un domaine **vérifié** dans Resend | `Opportunity Intelligence <alertes@votre-domaine.fr>` |
| `ALERT_RECIPIENT` | non | Adresse autorisée supplémentaire pour les alertes | — |
| `EMAIL_ALLOWED_RECIPIENTS` | non | Autres adresses autorisées (virgules) | — |
| `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` | non | Assistant de rédaction ; `anthropic` ; modèle par défaut `claude-opus-5-5` | — |
| `STORAGE_PROVIDER` | non | `s3`, `local` (dev — disque **éphémère** sur Render) ou `none` (téléversement désactivé) | `none` par défaut sur Render |
| `STORAGE_BUCKET`, `STORAGE_ENDPOINT_URL`, `STORAGE_REGION`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` | avec `s3` | Bucket **privé** S3-compatible (ex. Cloudflare R2 : endpoint `https://<compte>.r2.cloudflarestorage.com`, région `auto`) | — |
| `MAX_UPLOAD_MB` | non | Taille max. d'un fichier (≤ 4 derrière Vercel) | `4` |
| `COLLECTOR_USER_AGENT` | non | User-Agent identifiable envoyé aux sources | — |
| `MATCH_WEIGHT_ACADEMIC`, `_SKILLS`, `_FUNDING`, `_PREFERENCES`, `_LANGUAGES` | non | Pondération du matching | 30, 25, 20, 15, 10 |
| `PYTHON_VERSION` | Render | Version Python | `3.12.8` |

Après modification d'une variable sur Render : redéployer le Web Service (les Cron Jobs lisent la valeur à la prochaine exécution).

Contrôle sans afficher les valeurs : `python -m app.cli check-config`.

## Frontend (Vercel → Project Settings → Environment Variables)

| Variable | Obligatoire | Usage |
| --- | --- | --- |
| `BACKEND_API_URL` | **oui** | URL HTTPS de l'API Render (utilisée **côté serveur uniquement** par la passerelle) |
| `NEXT_PUBLIC_APP_URL` | oui | URL publique du site (vérification d'origine CSRF) |
| `NEXT_PUBLIC_API_URL` | non | Repli si `BACKEND_API_URL` absent ; ne contient aucun secret |

Aucune variable secrète n'est préfixée `NEXT_PUBLIC_`. Après modification : redéployer sur Vercel.

## Outils CLI (machine du développeur, facultatif)

`GITHUB_TOKEN`, `NEON_API_KEY`, `VERCEL_TOKEN`, `RENDER_API_KEY` ne sont pas utilisés par l'application ;
ils ne servent qu'aux CLI si vous automatisez le déploiement. Ne les ajoutez pas aux services.
