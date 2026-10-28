# API REST `/api/v1`

Documentation interactive OpenAPI en développement : `http://localhost:8000/docs` (désactivée en production).

- **Authentification** : `Authorization: Bearer <jeton>` (obtenu par `POST /auth/login`). Dans l'application
  web, le jeton n'est jamais exposé au navigateur : la passerelle Next.js l'ajoute à partir du cookie httpOnly.
- **Erreurs** (format unique) : `{"error": {"code": "…", "message": "…", "details": …}}`
  — `401 unauthorized`, `403 forbidden`, `404 not_found`, `409 conflict|application_exists|integrity_error`,
  `413 file_too_large|payload_too_large`, `415 unsupported_type`, `422 validation_error|…`, `429 rate_limited`,
  `503 storage_disabled|ai_*`.
- **Logs** structurés JSON avec `X-Request-ID`.

## Santé

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/health` | État de l'API, de la base, révision Alembic, mode e-mail, IA, stockage (503 si base injoignable) |

## Authentification

| Méthode | Chemin | Description |
| --- | --- | --- |
| POST | `/auth/login` | `{email, password}` → `{token, expires_at, user}` ; 5 échecs/15 min par e-mail, 20 par IP → 429 |
| POST | `/auth/logout` | Révoque la session courante |
| POST | `/auth/logout-all` | Révoque toutes les autres sessions |
| GET / PATCH | `/auth/me` | Compte courant / nom affiché, fuseau horaire (IANA) |
| POST | `/auth/change-password` | Vérifie l'ancien mot de passe, révoque les autres sessions |
| POST | `/auth/password-reset/request` | 202 identique que le compte existe ou non ; e-mail avec lien 30 min |
| POST | `/auth/password-reset/confirm` | `{token, new_password}` ; usage unique, révoque toutes les sessions |

| GET | `/auth/config` | Public : `{registration_open}` |
| POST | `/auth/register` | Public si `ALLOW_REGISTRATION` : `{email, password, display_name?}` → 202 identique dans tous les cas ; 403 `registration_closed`, 422 `weak_password`, 429 |
| POST | `/auth/verify-email` | `{token}` ; usage unique, 48 h ; 400 `invalid_verification_token` |
| POST | `/auth/verify-email/resend` | `{email}` → 202 identique que le compte existe ou non |
| POST | `/auth/delete-account` | `{password}` ; suppression définitive (409 `last_admin` pour le dernier administrateur) |

Connexion d'un compte non confirmé : 403 `email_not_verified` (uniquement si le mot de passe est correct).
Comptes administrateurs : `python -m app.cli create-admin` ou amorçage `bootstrap-admin`.

## Profil

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/profile` | Profil + complétude + champs manquants |
| PUT | `/profile` | Remplace le profil (validation stricte : codes ISO pays/langues, CECRL, dates AAAA-MM…), incrémente la version, recalcule les scores en arrière-plan |
| POST | `/profile/cv-extract` | PDF (multipart `file`) → suggestions + extraits justificatifs ; **n'enregistre rien** |

## Opportunités et matching

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/opportunities` | Filtres : `q, type, country, field, organization, study_level, funding (full/partial/full_or_partial), deadline_within_days, include_closed, eligibility, min_score, application_status, tracked, favorites_only` ; tri `sort` (`-score`, `deadline`, `-deadline`, `recent`, `title`) ; `page`, `page_size` ≤ 100 |
| GET | `/opportunities/facets` | Pays, domaines, organismes, types disponibles |
| POST | `/opportunities/import/preview` | `{url}` → brouillon pré-rempli (`draft`), méthode (`greenhouse-api`, `lever-api`, `json-ld`, `html`, `pdf`, `none`), remarques, `existing_opportunity_id` si l'offre existe déjà. **Rien n'est enregistré.** 422 `invalid_link` (adresse non publique, port, identifiants), 429 au-delà de 30 analyses / heure |
| POST | `/opportunities/import` | Offre relue (`type`, `title`, `organization`, `official_url` obligatoires ; `deadline_date` + `deadline_confirmed`, `follow`…) → `{opportunity_id, created, application_id}`. Jamais d'écrasement d'une offre existante ; 20 ajouts / jour / utilisateur |
| GET | `/opportunities/{id}` | Détail, provenance (`sources`), explication complète (`match_detail`) |
| POST / DELETE | `/opportunities/{id}/favorite` | Ajouter / retirer des favoris (idempotent) |
| GET | `/matches` | Comme `/opportunities` mais limité aux opportunités évaluées, avec raisons (satisfaits, non satisfaits, inconnus, à compléter) |
| POST | `/matches/recompute?force=false` | Recalcule les scores obsolètes (ou tous) de l'utilisateur |

## Candidatures et tâches

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/applications?status=` | Liste avec urgence explicable, score, éligibilité, documents, tâches ouvertes |
| POST | `/applications` | `{opportunity_id, status?, notes?}` ; 409 `application_exists` si déjà suivie |
| GET / PATCH / DELETE | `/applications/{id}` | Passer à `submitted`/`selection`/`accepted` exige `confirm_submission: true` la première fois (sinon 422 `submission_confirmation_required`) |
| GET | `/applications/{id}/events` | Historique |
| POST | `/applications/{id}/documents` | `{document_id, role?}` — document du même propriétaire uniquement |
| DELETE | `/applications/{id}/documents/{document_id}` | Retirer le lien |
| POST | `/applications/{id}/tasks` | Créer une tâche liée |
| GET | `/tasks` | Filtres `status, application_id, due_before, due_after, overdue, include_done` |
| POST | `/tasks` | Créer une tâche |
| PATCH / DELETE | `/tasks/{id}` | Modifier (statut `done` horodaté) / supprimer |

## Documents

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/documents?doc_type=` | Liste (avec candidatures associées) |
| POST | `/documents` | Multipart : `file`, `doc_type`, `title?`, `notes?`, `replaces?` (nouvelle version) ; type réel vérifié par signature |
| PATCH / DELETE | `/documents/{id}` | Métadonnées / suppression (fichier et liens) |
| GET | `/documents/{id}/download` | `{mode: "redirect", url}` (URL signée 5 min, S3) ou `{mode: "proxy", url}` |
| GET | `/documents/{id}/content` | Flux authentifié (`Content-Disposition: attachment`, `no-store`) |

## Notifications

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET / PUT | `/notifications/preferences` | Préférences ; l'adresse doit être celle du compte (confirmée) ou, pour un administrateur, une adresse autorisée (`ALERT_RECIPIENT`, `EMAIL_ALLOWED_RECIPIENTS`) |
| GET | `/notifications/logs?limit=` | Journal d'envoi |
| GET | `/notifications/preview?kind=digest|new_matches|deadline` | Aperçu HTML/texte, rien n'est envoyé |
| POST | `/notifications/test` | `{confirm: true}` obligatoire ; simulé sans Resend |

## Tableau de bord et calendrier

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/dashboard` | Indicateurs, échéances 7/30 j, tâches en retard, sources, collectes, e-mails, erreurs |
| GET | `/calendar?start=&end=` | Échéances (candidatures, favoris), tâches, prochaines actions, relances (≤ 400 jours) |

## Assistant IA (facultatif)

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/assist/status` | `{enabled}` |
| POST | `/assist/generate` | `{kind: cover_letter|cv_tailoring|application_answers|email_draft|interview_prep, opportunity_id, instructions?, questions?}` → brouillon modifiable + informations manquantes ; `enabled: false` sans configuration |

## Administration (administrateur uniquement — 403 sinon)

| Méthode | Chemin | Description |
| --- | --- | --- |
| GET | `/admin/sources` | Sources et état |
| PATCH | `/admin/sources/{id}` | `enabled`, `config`, `rate_limit_seconds` (0,5–60), `max_items` |
| POST | `/admin/sources/{id}/test` | Essai à blanc (aucune écriture d'annonce), 1/min par source |
| POST | `/admin/collect?source_id=` | Collecte en arrière-plan : 202 ; 429 si une collecte manuelle date de moins de 10 min ; 409 si une collecte tourne |
| GET | `/admin/runs` | Exécutions de collecte |
| POST | `/admin/jobs/check-deadlines` | Rappels/tâches/modifications maintenant (dédupliqués) |
| POST | `/admin/jobs/recompute-matches` | Recalcul global |
| GET | `/admin/connectors` | Connecteurs disponibles |
| GET | `/admin/users` | Comptes : rôle, adresse confirmée, actif, inscription, dernière connexion (jamais le hachage) |
| PATCH | `/admin/users/{id}` | `{is_active}` ; la désactivation révoque les sessions ; 409 sur son propre compte |
