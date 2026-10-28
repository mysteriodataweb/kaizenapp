# Connecteurs de collecte

Code : `backend/app/workers/connectors/`. Chaque connecteur interroge **une** source publique et autorisée et
produit des dictionnaires validés par `NormalizedOpportunity` (URL officielle obligatoire, champs bornés).
Le pipeline (`workers/ingestion.py`) se charge de la validation, du dédoublonnage, de l'enregistrement idempotent,
de la provenance et du journal (`ingestion_runs`).

## Sources fournies

| Clé | Connecteur | Type | Officielle ? | Format | Statut de vérification |
| --- | --- | --- | --- | --- | --- |
| `erasmus-mundus-catalogue` | `erasmus_mundus` | Bourses de master | Oui (EACEA, Commission européenne) | Page HTML publique (composants ECL), pagination `?page=N`, robots.txt respecté | **Non vérifié en conditions réelles** : structure HTML supposée (ECL) ; erreur « format non reconnu » journalisée si elle diffère |
| `greenhouse-internships` | `greenhouse` | Stages | Oui (boards des entreprises) | [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html) `GET /v1/boards/{token}/jobs?content=true` | Format documenté ; **boards par défaut (Cloudflare, Datadog, MongoDB) à confirmer** via « Tester » |
| `lever-internships` | `lever` | Stages | Oui (pages carrières) | [Lever Postings API](https://github.com/lever/postings-api) `GET /v0/postings/{site}?mode=json` | Format documenté ; **sites par défaut (Spotify, Palantir, Mistral AI) à confirmer** |
| `arbeitnow-internships` | `arbeitnow` | Stages (Allemagne) | Non (agrégateur → annonces « non vérifiées ») | [Arbeitnow API](https://www.arbeitnow.com/api) `GET /api/job-board-api` paginée | Format documenté, non vérifié en conditions réelles |
| `rss-feeds` | `rss` | Auto / configurable | Selon le flux (`official`) | RSS 2.0 / Atom (feedparser) | Vide par défaut : ajoutez vos flux |

**Toutes les sources sont créées désactivées.** Depuis l'environnement de développement, le réseau sortant
bloquait ces domaines : aucun connecteur n'a pu être exécuté contre la source réelle. Après déploiement, l'écran
**Administration → Sources de veille → Tester (à blanc)** interroge la source, valide les annonces sans rien
enregistrer et affiche un échantillon et les erreurs ; un test réussi marque la source « vérifiée ».

DAAD, EURAXESS : non retenus pour le MVP faute de format exploitable vérifiable (pas d'API/flux documenté
identifié) ; un flux RSS officiel peut être ajouté au connecteur `rss` s'il existe.

## Configuration (JSON, éditable dans l'admin)

```jsonc
// greenhouse
{"boards": [{"token": "cloudflare", "organization": "Cloudflare"}], "extra_keywords": ["apprentice"]}
// lever (region: "eu" pour api.eu.lever.co)
{"sites": [{"site": "mistral", "organization": "Mistral AI", "region": "global"}]}
// arbeitnow
{"max_pages": 5}
// erasmus_mundus
{"max_pages": 15}
// rss — type: internship | masters_scholarship | auto ; keywords : filtre facultatif
{"feeds": [{"url": "https://…/feed.xml", "type": "auto", "organization": "Université X", "official": true, "countries": ["FR"], "keywords": ["master"]}]}
```

Le token Greenhouse est le segment d'URL `boards.greenhouse.io/<token>` ; le site Lever, `jobs.lever.co/<site>`.

## Règles de collecte

- Client `PoliteClient` : User-Agent identifiable (`COLLECTOR_USER_AGENT`), délai minimal par hôte
  (`rate_limit_seconds`, 0,5–60 s), 2 nouvelles tentatives sur 429/5xx/timeout en respectant `Retry-After`.
- Pages HTML : `robots.txt` vérifié avant toute requête.
- **Aucun contournement** : 401/403, CAPTCHA ou refus robots.txt ⇒ arrêt de la source et erreur journalisée.
- Nombre d'annonces plafonné par source (`max_items`).
- Une source en échec n'interrompt jamais les autres ; une annonce invalide n'interrompt pas la source.
- Après 3 échecs consécutifs : source « en échec » et e-mail à l'administrateur (dédupliqué par série d'échecs).

## Normalisation

- Stages détectés par mots-clés de titre (intern, internship, stage, stagiaire, trainee, praktikum, werkstudent,
  alternance… avec frontières de mots : « International » ou « Backstage » ne sont pas des stages).
- Pays détectés prudemment (noms FR/EN/DE, grandes villes) ; rien n'est deviné si inconnu.
- HTML converti en texte ; paramètres de suivi retirés des URL canoniques.
- Dates limites : seulement si publiées ; une date extraite d'un texte libre (RSS) est marquée **non vérifiée** ;
  sinon **inconnue** — jamais inventée.

## Dédoublonnage

1. `(source, external_id)` ;
2. URL officielle normalisée (`canonical_url`, unique) ;
3. même titre, organisme, type, **date limite et localisation** normalisés, et uniquement depuis une **autre**
   source — jamais sur une simple similarité ; la source alternative est conservée dans `opportunity_sources` ;
4. empreinte de contenu (`content_hash`) : mise à jour + horodatage ; les changements significatifs (date limite,
   financement, critères, titre, lien, statut) déclenchent une alerte pour les opportunités suivies.

Une source non officielle n'écrase jamais les données d'une source officielle. Pour les sources à liste complète
(Greenhouse, Lever), une annonce disparue lors d'un passage complet sans erreur est **fermée** (jamais supprimée).

## Offres personnelles (ajout par lien)

Pour les offres que la collecte ne couvre pas, chaque utilisateur peut les enregistrer à partir de leur lien
(**Opportunités → Enregistrer des offres**). Ce n'est pas un connecteur : rien n'est collecté automatiquement, et les
offres ainsi ajoutées sont **privées** (colonne `owner_user_id`) : visibles, modifiables et supprimables par leur seul auteur,
jamais rattachées ni modifiées par la collecte.

| Lien | Méthode | Données |
| --- | --- | --- |
| LinkedIn (`/jobs/view/…`, `/comm/jobs/view/…`, `?currentJobId=…`) | **Aucune requête** (connexion requise, robots.txt) : adresse du lien | identifiant (URL canonique `linkedin.com/jobs/view/{id}`), intitulé et entreprise lorsqu'ils figurent dans l'adresse |
| `boards.greenhouse.io/{board}/jobs/{id}` | API publique Greenhouse (offre unique) | titre, organisme, lieu, pays, description, départements |
| `jobs.lever.co/{site}/{uuid}` (et `jobs.eu.lever.co`) | API publique Lever (offre unique) | titre, lieu, pays, télétravail, description, équipe |
| Page avec données structurées schema.org `JobPosting` | JSON-LD | titre, organisme, lieu/pays, date limite (`validThrough`), type (`INTERN`), rémunération, description |
| Autre page HTML | Contenu de la page | titre (`og:title`, `h1`, `<title>`), organisme (`og:site_name`), description, date limite repérée |
| PDF (appel à candidatures) | Texte du document | première ligne comme titre, description, date limite repérée |
| **Texte collé** par l'utilisateur | IA si configurée (`AI_PROVIDER`), sinon règles | IA : intitulé, entreprise, lieu, pays, type, date limite, durée, documents, critères — chaque valeur est **vérifiée dans le texte** et écartée sinon. Règles : description, date limite, type |

Deux façons d'enregistrer :
- **Plusieurs liens d'un coup** (jusqu'à 50) : aucune page lue ; chaque offre est créée avec ce que contient son lien
  (sinon « Offre LinkedIn n° … » / « À préciser », à compléter plus tard) et ajoutée à « À explorer ».
- **Une offre détaillée** : lien + texte facultatif → brouillon relu et complété avant enregistrement.

La liste **À postuler** présente les offres suivies non envoyées, une à la fois (échéance la plus proche d'abord, puis sans
date dans l'ordre d'ajout, puis échéances dépassées), avec « Ouvrir l'offre », « J'ai postulé » (confirmation humaine),
« Plus tard » et « Retirer ».

## Ajouter un connecteur

1. Créer une classe héritant de `Connector` (`name`, `official`, `complete_listing`, méthode `fetch()`).
2. L'enregistrer dans `registry.CONNECTORS` (+ éventuellement `DEFAULT_SOURCES`).
3. Ajouter un jeu de test au format réel dans `tests/fixtures/` et des tests dans `test_ingestion.py`.
4. Vérifier les conditions d'utilisation de la source et documenter ici.
