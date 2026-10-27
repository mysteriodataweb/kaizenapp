# État d'avancement et critères d'acceptation du MVP

Date de l'évaluation : 27/10/2026. Environnement de développement : conteneur cloud **sans accès réseau sortant
aux sources ni aux services d'hébergement** (Neon, Render, Vercel, Resend, sites d'annonces bloqués par la politique
réseau) et sans CLI Neon/Vercel/Render. Les statuts ci-dessous reflètent uniquement ce qui a été **prouvé**.

Légende : **PASS** (preuve par test automatisé ou exécution) · **FAIL** · **BLOCKED** (dépend d'une action/accès
extérieur) · **NOT TESTED**.

## Produit

| Critère | Statut | Preuve / commentaire |
| --- | --- | --- |
| Le profil est modifiable | PASS | `test_profile_roundtrip_and_validation`, e2e « profil » |
| Le catalogue affiche des opportunités **réelles** provenant de sources vérifiées | BLOCKED | Pipeline complet prouvé sur jeux de test (e2e « collecte → catalogue ») ; sources réelles injoignables depuis cet environnement. À valider après déploiement via « Tester » puis collecte |
| Les annonces ont une provenance | PASS | Contrainte SQL + `test_detail_has_provenance_and_explanation`, page détail (e2e) |
| Les filtres fonctionnent | PASS | `test_catalogue_filters_sort_pagination`, e2e (type, recherche) |
| Le matching affiche les explications | PASS | Tests moteur + e2e détail |
| L'inéligibilité est distincte de l'incertitude | PASS | `test_missing_profile_info_gives_unknown_not_ineligible`, `test_ineligible_only_on_explicit_incompatibility` |
| Le pipeline de candidatures est opérationnel | PASS | `test_application_lifecycle`, e2e (suivi → statut avec confirmation → tâche → Kanban/tableau) |
| Les documents sont privés | PASS (stockage local) / NOT TESTED (S3 réel) | `test_documents_are_private`, contrainte SQL propriétaire ; bucket S3 réel non disponible |
| Les deadlines apparaissent dans le tableau de bord | PASS | `test_dashboard_and_calendar` |
| Les préférences d'alertes sont modifiables | PASS | `test_preferences_api_rejects_unauthorized_recipient`, e2e alertes |

## Automatisation

| Critère | Statut | Preuve / commentaire |
| --- | --- | --- |
| Connecteurs ré-exécutables sans doublons | PASS | `test_rerun_is_idempotent`, `test_cross_source_duplicate_is_linked_not_duplicated` |
| Erreurs journalisées | PASS | `test_source_error_is_logged_and_counted`, `ingestion_runs`, logs JSON |
| Tâches planifiées indépendantes du navigateur | PASS (local) / BLOCKED (Render) | Commandes `python -m app.jobs.*` exécutées localement (code 0) ; Cron Jobs Render à créer |
| Alertes dédupliquées | PASS | `test_dispatch_is_deduplicated`, rappels/changes « duplicate » |
| Rappels sans fausses certitudes sur les dates non vérifiées | PASS | `test_no_reminder_for_unknown_deadline_and_flag_unverified` |
| Fonctionne sans fournisseur IA | PASS | `test_assistant_disabled_without_key`, e2e (bannière « Fonction désactivée ») |
| Envoi réel d'e-mails Resend | BLOCKED | Clé absente, `api.resend.com` injoignable ici ; client Resend testé contre un transport simulé |

## Sécurité

| Critère | Statut | Preuve / commentaire |
| --- | --- | --- |
| Aucun secret dans Git | PASS | `.gitignore` strict, recherche de motifs de secrets avant commit (aucun résultat) |
| Routes privées protégées | PASS | `test_private_routes_require_auth`, e2e redirection |
| Accès vérifié côté serveur | PASS | `test_users_are_isolated` (user_id du client ignoré) |
| Fichiers dans un espace privé | PASS | Accès authentifié uniquement, URL signées 5 min (S3) |
| Opérations administratives protégées | PASS | `test_admin_routes_forbidden_for_non_admin`, limitation de collecte |
| Les erreurs ne divulguent pas de secrets | PASS | Réponses génériques, masquage dans les logs |
| Entrées utilisateur validées | PASS | Pydantic/Zod, tests de validation, signature binaire des fichiers |
| CSRF / cookie httpOnly | PASS | e2e `auth.spec.ts` |

## Déploiement

| Critère | Statut | Commentaire |
| --- | --- | --- |
| Dépôt GitHub accessible | PASS | Branche `claude/magical-sagan-50inw2` poussée sur `mysteriodataweb/kaizenapp` |
| Intégration continue | PASS | GitHub Actions run #1 (commit `44d5070`) : Backend, Frontend et End-to-end réussis |
| Frontend Vercel avec URL vérifiée | BLOCKED | Projet à créer (racine `apps/web`) — voir DEPLOYMENT.md §3 |
| Backend Render avec URL vérifiée | BLOCKED | Blueprint `render.yaml` prêt — voir DEPLOYMENT.md §2 |
| Neon accessible depuis le backend | BLOCKED | Projet Neon à créer ; connexion compatible pooler testée en local (PostgreSQL 16) |
| Migrations appliquées | PASS (local) / BLOCKED (Neon) | `alembic upgrade head` + `alembic check` sans dérive ; appliquées automatiquement au démarrage Render |
| Health check répond | PASS (local) / BLOCKED (Render) | `/api/v1/health` → 200 |
| Tâches planifiées configurées | PASS (configuration) / désactivées par choix | Cron Jobs commentés dans `render.yaml` (payants) ; `oi-daily` prêt à activer |
| Logs permettent de diagnostiquer | PASS (local) | Logs JSON, X-Request-ID, journal des collectes et des e-mails |

## Reste à faire (actions de l'utilisateur)

1. Créer le projet Neon et récupérer les chaînes pooled/direct.
2. Créer le Blueprint Render et renseigner le groupe d'environnement (dont l'amorçage admin) — **les Cron Jobs sont payants**.
3. Créer le projet Vercel (racine `apps/web`) avec `BACKEND_API_URL` et `NEXT_PUBLIC_APP_URL`.
4. Mettre à jour `FRONTEND_URL`/`CORS_ORIGINS` sur Render.
5. Tester puis activer les sources ; lancer une première collecte.
6. Facultatif : Resend (domaine vérifié), stockage S3-compatible, clé IA.
