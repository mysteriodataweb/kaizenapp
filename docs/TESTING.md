# Tests

Tous les tests sont reproductibles et **ne dépendent d'aucun site distant** : les connecteurs sont testés
avec des jeux de données reproduisant les formats documentés (`backend/tests/fixtures/`) via un transport HTTP simulé.
Aucun test ne touche la production (garde-fous dans `conftest.py` et `e2e_seed.py`).

## Backend — Pytest sur PostgreSQL réel

```bash
cd backend
createdb oi_test                     # une fois
.venv/bin/pytest                     # ou TEST_DATABASE_URL=postgresql://… .venv/bin/pytest
.venv/bin/pytest --cov=app           # couverture
```

À chaque session : schéma recréé, migrations `upgrade → downgrade → upgrade` (réversibilité), tables vidées entre tests,
client e-mail remplacé par une boîte de simulation.

| Fichier | Couverture |
| --- | --- |
| `test_auth.py` | Santé, connexion, erreurs identiques, limitation de débit, inscriptions fermées par défaut, routes protégées, déconnexion, jetons hachés, Argon2id, mot de passe faible, réinitialisation (usage unique, sessions révoquées), changement de mot de passe, fuseau, admin 403, corps trop volumineux, en-têtes |
| `test_matching.py` | Éligibilité unknown/eligible/ineligible, information manquante ≠ inéligible, langues, bornes du score, fiabilité, pondération adaptée (sans objet), cohérence des scores, domaines bilingues, urgence explicable |
| `test_ingestion.py` | Greenhouse/Lever/Arbeitnow/Erasmus Mundus/RSS, filtre stages, idempotence, détection de changement, annonces disparues fermées, erreurs journalisées, format inattendu, une source en échec n'arrête pas les autres, doublons inter-sources (fusion stricte, pas sur simple similarité), validation, robots.txt, changement de format, CAPTCHA non contourné, essai à blanc sans écriture |
| `test_api_core.py` | Profil (validation, version), catalogue (filtres, recherche, tri, pagination), détail (provenance, explication), favoris, recalcul après changement de profil, cycle de vie d'une candidature (doublon 409, confirmation humaine), tâches, isolation entre utilisateurs, tableau de bord, calendrier |
| `test_documents_ai.py` | Téléversement/téléchargement/versions/suppression, types refusés, taille, confidentialité, liaison même propriétaire (API + contrainte SQL), stockage désactivé, extraction de CV sans enregistrement, assistant désactivé sans clé, assistant limité aux faits du profil |
| `test_registration.py` | Inscription avec confirmation obligatoire, réponses non divulgatrices (compte existant prévenu, mot de passe inchangé), mot de passe faible, plafonds par IP et global, fermeture en production sans e-mail, lien expiré / renvoi / plafond d'envois, réinitialisation qui confirme l'adresse, destinataires (adresse confirmée, liste réservée à l'admin), modération (liste, désactivation, pas d'auto-désactivation), tableau de bord sans erreurs techniques pour les membres, suppression de compte (cascade + fichiers), dernier admin protégé |
| `test_link_import.py` | Lecture sûre sur un web simulé (JSON-LD / HTML / PDF / API Greenhouse et Lever, robots.txt, 403, CAPTCHA, connexion, **SSRF**), **LinkedIn jamais interrogé** (identifiant, intitulé et entreprise tirés de l'adresse, variantes de lien = même offre, enveloppe `safety/go` retirée sans requête, `lnkd.in` suivi sans lire LinkedIn ni la destination en ajout rapide, robots.txt de `lnkd.in`, page intermédiaire, destination privée refusée, lien injoignable → saisie manuelle), texte collé avec **IA simulée** (valeurs absentes du texte écartées, repli sur les règles si l'IA échoue) ou sans IA, **offres privées** (invisibles pour les autres : catalogue, détail, favori, suivi, facettes, tableau de bord, scores ; même lien = copie propre à chacun ; collecte sans effet sur elles), ajout rapide de plusieurs liens (doublons, erreurs, suivi « À explorer », limite), modification/suppression par l'auteur seul (403 / 404 / 409), suppression de compte avec offres personnelles |
| `test_notifications_jobs.py` | Déduplication, destinataires autorisés, préférences, rappels J-n (rattrapage), date inconnue sans rappel, date non vérifiée signalée, favoris, tâches, nouvelles opportunités une seule fois, modifications, périodes de récapitulatif, relances plafonnées, client Resend (succès, 429, idempotence, erreur définitive), e-mail de test confirmé, aperçus sans envoi, verrous de jobs, codes de sortie, nettoyage, job quotidien, protections admin |

## Frontend — Vitest + Testing Library

```bash
cd apps/web && npm test
```

`tests/unit/` : formatage des dates dans le fuseau utilisateur, libellés d'échéance (inconnue / non vérifiée),
client API (passerelle, erreurs normalisées, erreur réseau), composants du design system (accessibilité, statuts
en français, score peu fiable, saisie de listes), formulaire de connexion, **confirmation humaine avant « Envoyée »**,
filtres du catalogue, enregistrement d'offres (plusieurs liens, texte collé + brouillon IA, type obligatoire, offre déjà
enregistrée, lien refusé, charge utile), liste « À postuler » (ordre, une offre à la fois, « Plus tard », confirmation avant
« Envoyée »), inscription (fermée/ouverte, validation, champs envoyés), nouvel envoi du lien de confirmation,
confirmation d'adresse uniquement après un clic.

## End-to-end — Playwright

```bash
npm --prefix apps/web run build
bash scripts/e2e.sh                  # base locale oi_e2e (créée si besoin : createdb oi_e2e)
```

Le script prépare une base dédiée en exécutant **le vrai pipeline de collecte** sur les jeux de test, démarre l'API
(port 8001) et Next.js en mode production (port 3001), puis lance :

- `auth.spec.ts` : redirection des pages privées, mauvais mot de passe, cookie httpOnly illisible en JS, CSRF refusé, déconnexion ;
- `journey.spec.ts` : collecte → matching → catalogue filtré → recherche → détail expliqué → suivi → statut « Envoyée »
  avec confirmation → tâche → Kanban/tableau → préférences d'alertes → aperçu d'e-mail ; profil (validation + enregistrement) ;
  calendrier, téléversement de document, administration des sources ;
- `registration.spec.ts` : inscription → compte en attente → connexion refusée avec nouvel envoi proposé → visible et
  désactivable dans **Utilisateurs** (admin) ; lien de confirmation invalide ;
- `import.spec.ts` (projet `desktop-catalogue-writes`, exécuté après les parcours qui comptent les offres de la base e2e) :
  deux liens LinkedIn enregistrés d'un coup → « À postuler » → « Plus tard » → « J'ai postulé » confirmé ; offre détaillée
  à partir d'un texte collé (domaine `.invalid`, sans IA) → modification → suppression ;
- `responsive.spec.ts` (Pixel 7) : menu mobile et absence de débordement horizontal sur toutes les pages.

## Intégration continue

`.github/workflows/ci.yml` : backend (ruff, `alembic check`, pytest + couverture sur PostgreSQL 16), frontend
(ESLint, TypeScript, Vitest, build), puis e2e Playwright.

## Derniers résultats (environnement de développement)

| Suite | Résultat |
| --- | --- |
| Pytest | 164 tests, tous réussis |
| Vitest | 35 tests réussis |
| Playwright | 13 parcours réussis |
| ESLint / TypeScript / Ruff | aucun problème |
| `next build` | réussi |
