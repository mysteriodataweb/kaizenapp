# Base de données

PostgreSQL (Neon en production). Schéma versionné par Alembic (`backend/migrations`). Identifiants UUID
(`gen_random_uuid()`), dates `timestamptz` stockées en **UTC**, statuts en `VARCHAR` + contraintes `CHECK`
(plus simples à faire évoluer que des ENUM natifs).

## Tables

| Table | Rôle | Isolation |
| --- | --- | --- |
| `users` | Comptes (e-mail unique insensible à la casse, hachage Argon2id, fuseau, dernière visite) | — |
| `auth_sessions` | Sessions opaques (seul le SHA-256 du jeton est stocké), expiration, révocation | utilisateur |
| `password_reset_tokens` | Jetons de réinitialisation hachés, 30 min, usage unique | utilisateur |
| `auth_attempts` | Tentatives de connexion (limitation de débit persistante, clés hachées) | — |
| `profiles` | Profil (1 par utilisateur) ; listes éditées d'un bloc en JSONB validé ; `version` déclenche le recalcul | utilisateur |
| `documents` | Métadonnées des fichiers privés (binaire dans le stockage objet), versions par `group_id` | utilisateur |
| `sources` | Sources de collecte (connecteur, configuration JSONB, débit, état de vérification, échecs consécutifs) | catalogue |
| `opportunities` | Annonces normalisées, provenance, échéance + statut de la date, empreinte de contenu, recherche plein texte (colonne `tsvector` générée) | catalogue commun |
| `opportunity_sources` | Toutes les sources ayant publié une annonce (sources alternatives conservées), données brutes | catalogue |
| `favorites` | Favoris | utilisateur |
| `matches` | Éligibilité, score 0–100, fiabilité, explication JSONB, versions de calcul, notification | utilisateur |
| `applications` | Candidatures (1 par utilisateur et opportunité), statut, dates, contact, notes, preuve de confirmation humaine | utilisateur |
| `application_documents` | Lien candidature ↔ document, **même propriétaire garanti par clés étrangères composites** | utilisateur |
| `application_events` | Historique immuable des modifications | utilisateur |
| `tasks` | Tâches (liées ou non à une candidature) | utilisateur |
| `notification_preferences` | Préférences d'alertes | utilisateur |
| `notification_logs` | Journal d'envoi ; `(user_id, dedup_key)` unique = jamais deux fois la même notification | utilisateur |
| `ingestion_runs` | Journal des collectes (compteurs, erreurs, annonces fermées) | — |
| `job_locks` | Verrous à bail des jobs planifiés | — |

## Contraintes d'intégrité notables

- `uq_applications_user_opportunity` : une candidature par utilisateur et opportunité.
- `uq_notification_logs_dedup` : une notification logique n'est envoyée qu'une fois.
- `fk_application_documents_*_owner` : `(application_id, user_id)` et `(document_id, user_id)` référencent
  `(id, user_id)` — un document ne peut être lié qu'à une candidature **du même propriétaire**.
- `ck_opportunities_official_url_present`, `ck_opportunity_sources_source_url_present` : provenance obligatoire.
- `ck_opportunities_deadline_consistent` : pas de date ⇔ statut de date `unknown`.
- `ck_matches_score_range` (0–100), `ck_matches_confidence_range` (0–1).
- `ck_applications_submitted_requires_date` : une candidature envoyée a une date d'envoi.
- `uq_opportunities_canonical_url` et index unique partiel `(primary_source_id, external_id)`.

## Index

Échéances (`opportunities.deadline_at`, `applications.deadline_at`, `next_action_at`), statuts
(`type,status`, `user_id,status`), tâches `(user_id, status, due_at)`, GIN sur `search_vector` et `countries`,
`matches (user_id, score)`, dédoublonnage `(organization_norm, title_norm)`.

## Migrations

```bash
cd backend
.venv/bin/alembic upgrade head                              # appliquer
.venv/bin/alembic revision --autogenerate -m "description"  # créer (relire le fichier généré !)
.venv/bin/alembic check                                     # vérifier l'absence de dérive modèle/schéma
```

- En production, Alembic utilise `DATABASE_MIGRATION_URL` (connexion **directe** Neon) si défini, sinon `DATABASE_URL`.
- Les migrations sont appliquées au démarrage du service Render (`alembic upgrade head`, idempotent).
- Les tests appliquent `upgrade → downgrade base → upgrade` à chaque exécution : la migration initiale est réversible.
- **Jamais de migration destructive en production sans sauvegarde et confirmation** (voir ci-dessous).

## Sauvegarde et restauration (Neon)

- Neon conserve un historique (« point-in-time restore ») selon le plan ; avant toute migration risquée,
  créer une **branche** Neon de sauvegarde (console Neon → Branches → Create branch, ou `neonctl branches create`).
- Export logique ponctuel : `pg_dump "$DATABASE_MIGRATION_URL" -Fc -f sauvegarde.dump` (ne jamais versionner ce fichier).
- Restauration : `pg_restore --clean --no-owner -d "<URL cible>" sauvegarde.dump` sur une branche de test d'abord.
