# Exploitation

## Tâches planifiées (Render Cron Jobs, horaires UTC)

| Job | Commande | Planification | Rôle |
| --- | --- | --- | --- |
| `oi-collect-opportunities` | `python -m app.jobs.collect_opportunities` | 04:15 chaque jour | Sources activées → recalcul des scores → alertes « nouvelles opportunités » → alertes d'échecs de collecte |
| `oi-recompute-matches` | `python -m app.jobs.recompute_matches [--force]` | 04:45 | Recalcule les scores obsolètes |
| `oi-check-deadlines` | `python -m app.jobs.check_deadlines` | 06:00 | Rappels J-14/7/3/1, tâches dues, modifications significatives |
| `oi-send-digest` | `python -m app.jobs.send_digest` | 07:05 | Récapitulatif quotidien/hebdomadaire (une fois par période et par utilisateur) |
| `oi-cleanup` | `python -m app.jobs.cleanup_logs` | dimanche 03:30 | Journaux anciens, sessions expirées, annonces échues fermées, annonces non revues marquées « périmées » |
| *(option)* `oi-daily` | `python -m app.jobs.daily` | 05:15 | Tout enchaîner dans un seul job (économique) |

Garanties communes (`app/jobs/_runner.py`) : logs JSON `job start` / `job end` (durée, résultat), code de sortie
0 en cas de succès ou si le job tourne déjà ailleurs (verrou à bail `job_locks`), 1 en cas d'échec ; relançables sans
effet indésirable (upserts idempotents, notifications dédupliquées). Aucun scheduler ne tourne dans l'API.

Exécution manuelle : Render → Cron Job → **Trigger Run**, ou localement `cd backend && .venv/bin/python -m app.jobs.<job>`.

## Supervision

- **Santé** : `GET /api/v1/health` (Render l'utilise comme health check).
- **Logs** : JSON (`ts`, `level`, `logger`, `msg`, champs) ; chaque requête porte un `X-Request-ID`. Secrets masqués.
- **Tableau de bord** : dernières collectes, état des sources, derniers e-mails, erreurs des 7 derniers jours.
- **Administration → Sources** : exécutions détaillées (lues, créées, mises à jour, ignorées, erreurs, annonces fermées).
- **Alertes → Journal d'envoi** : statut, tentatives, erreur, identifiant Resend.

## Diagnostic

| Symptôme | Piste |
| --- | --- |
| Frontend « API injoignable » | `BACKEND_API_URL` (Vercel), API en veille (plan gratuit, attendre ~1 min), logs Render |
| Boucle vers `/login` | Session expirée/révoquée : le cookie est effacé automatiquement ; vérifier l'horloge et `CORS/FRONTEND_URL` |
| 403 « Origine refusée » | `NEXT_PUBLIC_APP_URL` doit correspondre au domaine servi |
| Health `degraded` | `DATABASE_URL` invalide, base Neon suspendue/limite atteinte |
| Source « en échec » | Admin → Tester : message d'erreur (404 board inconnu, 403 accès refusé, format modifié…) |
| E-mails « Simulé » | `RESEND_API_KEY` / `EMAIL_FROM` absents |
| E-mails « Échec » HTTP 403/422 | Domaine non vérifié dans Resend ou `EMAIL_FROM` invalide |
| Téléversement 503 | `STORAGE_PROVIDER` non configuré |

## Procédures

- **Créer/réinitialiser l'admin** : `python -m app.cli create-admin --email …` (depuis une machine avec
  `DATABASE_URL` de production, ou via l'amorçage si la base est vide). Mot de passe oublié : lien « Mot de passe oublié ».
- **Migration** : créer une branche Neon de sauvegarde, appliquer sur une branche de test, puis déployer.
- **Rotation de `SECRET_KEY`** : sans impact sur les sessions (jetons hachés en SHA-256) ; seules les empreintes de
  limitation par IP changent.
- **Désactiver une source** : Admin → décocher « Active » (effet à la collecte suivante).
- **Pondération du matching** : variables `MATCH_WEIGHT_*`, puis `python -m app.jobs.recompute_matches --force`.
