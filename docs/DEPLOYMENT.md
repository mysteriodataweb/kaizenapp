# Déploiement

Cible : **Neon** (PostgreSQL) · **Render** (API FastAPI + Cron Jobs, Blueprint `render.yaml`) ·
**Vercel** (frontend, racine `apps/web`) · **Resend** (e-mails) · stockage S3-compatible (documents, facultatif).

Tout se fait depuis les tableaux de bord web (aucune CLI requise). Les équivalents CLI sont indiqués en fin de page.
Ordre recommandé : Neon → Render → Vercel → finalisation.

## 0. Code source

Le code est sur GitHub (`mysteriodataweb/kaizenapp`). Fusionnez la branche de travail dans `main`
(pull request), ou sélectionnez directement la branche lors de la configuration Render/Vercel.

## 1. Neon — base PostgreSQL

1. <https://console.neon.tech> → **New Project** → nom `opportunity-intelligence`, région
   **AWS Europe Central 1 (Frankfurt)** (même région que Render `frankfurt` pour la latence), PostgreSQL 16+.
2. **Connect** → copier deux chaînes :
   - **Pooled connection** (hôte contenant `-pooler`) → `DATABASE_URL`
   - **Direct connection** → `DATABASE_MIGRATION_URL`
3. Ne collez ces chaînes **que** dans le groupe d'environnement Render (jamais dans Git ni dans Vercel).

Plan gratuit Neon : suffisant pour un usage personnel ; le calcul se suspend après inactivité (géré par l'API).

## 2. Render — API et tâches planifiées

1. <https://dashboard.render.com> → **New → Blueprint** → connecter GitHub → choisir le dépôt et la branche.
   Render détecte `render.yaml` et propose : le groupe `opportunity-intelligence-shared` et le Web Service
   `opportunity-intelligence-api` (plan **free**). Les Cron Jobs sont **commentés** (payants, facturés à l'usage) :
   pour les activer plus tard, décommentez `oi-daily` (un seul job quotidien, le moins cher) ou les 5 jobs séparés,
   puis resynchronisez le Blueprint. Sans Cron Jobs, la collecte et les rappels se déclenchent depuis
   l'écran **Sources de veille** (« Collecter maintenant ») et l'API admin (`/admin/jobs/check-deadlines`).
2. Ouvrir **Env Groups → opportunity-intelligence-shared** et ajouter :
   - `DATABASE_URL`, `DATABASE_MIGRATION_URL` (Neon)
   - `BOOTSTRAP_ADMIN_EMAIL` = votre e-mail ; `BOOTSTRAP_ADMIN_PASSWORD` = mot de passe fort (≥ 12 caractères)
   - `FRONTEND_URL` et `CORS_ORIGINS` : provisoirement `https://example.invalid`, à corriger à l'étape 4
3. **Manual Deploy** du Web Service. Le démarrage exécute : `alembic upgrade head` → `seed-sources` →
   `bootstrap-admin` → `uvicorn`.
4. Vérifier : `https://<service>.onrender.com/api/v1/health` doit renvoyer `"database": "ok"` et `"migration": "0001"`.
   Les logs (onglet **Logs**) sont en JSON.
5. Retirer `BOOTSTRAP_ADMIN_PASSWORD` du groupe après la première connexion réussie (l'amorçage ne s'exécute de
   toute façon que si aucun compte n'existe).

Plan gratuit : mise en veille après ~15 min sans trafic (premier appel ~1 min). Les Cron Jobs ne dépendent
pas de l'API : ils accèdent directement à la base.

## 3. Vercel — frontend

1. <https://vercel.com/new> → importer le dépôt GitHub.
2. **Root Directory** : `apps/web` (Framework : Next.js détecté ; `vercel.json` fixe `npm ci`, `npm run build`, région `fra1`).
3. **Environment Variables** (Production + Preview) :
   - `BACKEND_API_URL` = `https://<service>.onrender.com`
   - `NEXT_PUBLIC_APP_URL` = URL Vercel du projet (ex. `https://opportunity-intelligence.vercel.app`)
4. **Deploy**. Les déploiements de branches créent des previews ; `main` déploie la production.

## 4. Finalisation

1. Render → groupe d'environnement : `FRONTEND_URL` et `CORS_ORIGINS` = URL Vercel de production → redéployer l'API.
2. Se connecter sur l'URL Vercel avec le compte amorcé.
3. **Sources de veille** (menu admin) : cliquer « Tester (à blanc) » sur chaque source. Une source exploitable
   passe « vérifiée » ; ajustez la configuration (boards Greenhouse, sites Lever, flux RSS) puis **activez** les sources voulues.
4. Facultatif : « Collecter maintenant » (protégé : admin, 1 collecte manuelle / 10 min, verrou anti-chevauchement).
5. Profil : compléter les informations utiles au matching.

## 5. E-mails (Resend)

1. <https://resend.com> → **Domains** → ajouter et vérifier votre domaine (enregistrements DNS).
2. **API Keys** → créer une clé « Sending access ».
3. Render (groupe) : `RESEND_API_KEY`, `EMAIL_FROM` (adresse du domaine vérifié), éventuellement `ALERT_RECIPIENT`.
   Redéployer l'API.
4. Application → **Alertes** : la bannière « mode simulation » disparaît ; « E-mail de test » (confirmation requise).
   Le journal affiche l'identifiant Resend du message.

Sans domaine vérifié, Resend n'autorise que l'envoi vers l'adresse du compte Resend : gardez le mode simulation en attendant.

## 6. Documents (stockage privé S3-compatible)

Exemple Cloudflare R2 : créer un bucket **privé**, un jeton API « Object Read & Write » limité au bucket, puis :
`STORAGE_PROVIDER=s3`, `STORAGE_BUCKET`, `STORAGE_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com`,
`STORAGE_REGION=auto`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`. Les téléchargements utilisent des URL signées de 5 min.
Sans configuration (`none`), le téléversement est désactivé proprement (message explicite), le reste fonctionne.

## 7. Assistant IA (facultatif)

`AI_PROVIDER=anthropic`, `AI_API_KEY=<clé>`, éventuellement `AI_MODEL` (défaut `claude-opus-5-5`). Sinon la fonction reste désactivée.

## Vérifications après déploiement

| Contrôle | Comment |
| --- | --- |
| API en ligne | `GET /api/v1/health` → 200, `database: ok` |
| Migrations | `migration` = révision Alembic attendue |
| Frontend | URL Vercel → redirection `/login` ; connexion → tableau de bord |
| Pages privées | Sans cookie : redirection vers `/login` ; avec session expirée : retour à `/login?expired=1` |
| Appels API | Tableau de bord chargé (sinon vérifier `BACKEND_API_URL` et les logs Vercel) |
| Cron Jobs | Render → chaque Cron Job → **Trigger Run** puis logs `job start` / `job end` (code de sortie 0) |
| Collecte | Admin → Exécutions récentes |
| E-mails | Alertes → E-mail de test → statut « Envoyé » + identifiant Resend |

## Équivalents CLI (facultatif, sur une machine avec les outils)

```bash
# GitHub
gh repo view mysteriodataweb/kaizenapp
# Neon
neonctl projects create --name opportunity-intelligence --region-id aws-eu-central-1
neonctl connection-string --pooled        # DATABASE_URL
neonctl connection-string                 # DATABASE_MIGRATION_URL
# Vercel (depuis apps/web)
vercel link && vercel env add BACKEND_API_URL production && vercel --prod
# Render : créer le Blueprint depuis le dashboard ; la CLI `render` permet ensuite logs et déploiements.
```
