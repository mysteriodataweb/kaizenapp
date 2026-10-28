# Sécurité

## Authentification et sessions

- Compte administrateur créé par CLI (`create-admin`, mot de passe saisi via `getpass` ou `ADMIN_PASSWORD` à
  l'exécution) ou amorçage unique (`bootstrap-admin`, uniquement si aucun compte n'existe). Aucun mot de passe par
  défaut n'existe dans le code.
- Inscription publique **fermée par défaut** (`ALLOW_REGISTRATION=false`). Ouverte, elle impose :
  - une **adresse e-mail confirmée** avant la première connexion (jeton haché, 48 h, usage unique, 3 envois / heure ;
    confirmation par un clic sur la page, pas au simple chargement du lien, pour neutraliser les scanners de messagerie) ;
  - des **réponses identiques** que l'adresse soit libre, en attente ou déjà utilisée (le titulaire d'un compte
    existant est prévenu par e-mail ; son mot de passe ne change jamais) ;
  - une limitation : 5 inscriptions / heure par IP et 30 / heure au total (plafond global, indépendant des en-têtes) ;
  - en production, des **e-mails réels** (Resend) : sans fournisseur, les inscriptions restent fermées ;
  - des comptes **membres** (jamais administrateurs) : sources de veille, collectes et utilisateurs restent réservés à
    l'administrateur, qui peut désactiver un compte (sessions révoquées immédiatement) ;
  - la **suppression de compte** par l'utilisateur (mot de passe + saisie de confirmation) : cascade SQL sur toutes ses
    données et effacement des fichiers stockés. Le dernier administrateur ne peut pas se supprimer.
- Mots de passe : **Argon2id** (argon2-cffi), ré-hachage automatique si les paramètres évoluent ; politique :
  ≥ 12 caractères, pas trop répétitif, ne contient pas l'identifiant ; temps de réponse égalisé pour les comptes inexistants.
- Sessions : jeton aléatoire 256 bits ; **seul son SHA-256 est stocké** ; expiration 14 jours ; révocation à la
  déconnexion, au changement et à la réinitialisation du mot de passe ; « fermer les autres sessions ».
- Limitation de débit persistante (table `auth_attempts`) : 5 échecs / 15 min par e-mail, 20 par IP (empreinte HMAC).
- Réinitialisation : jeton haché, 30 min, usage unique, 3 demandes / heure, réponse identique que le compte existe ou non.

## Navigateur ↔ serveur

- Jeton dans un cookie **httpOnly, Secure (production), SameSite=Lax** posé par Next.js : inaccessible au JavaScript (test e2e).
- **CSRF** : toute requête non-GET via la passerelle doit provenir de la même origine (`Origin`/`Referer`) — 403 sinon (test e2e).
- `/api/auth/login` n'est jamais relayé par la passerelle générique (le jeton ne transite jamais vers le navigateur).
- En-têtes : CSP stricte en production (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`…),
  HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`.
- L'aperçu des e-mails est rendu dans une `iframe sandbox` sans script.

## Autorisation et isolation des données

- L'identité provient exclusivement du jeton vérifié côté serveur ; un `user_id` fourni par le client est ignoré (test).
- Toutes les requêtes métier filtrent par `user_id` ; une ressource d'un autre utilisateur renvoie 404 (tests).
- Intégrité en base : clés étrangères composites `(id, user_id)` empêchant de lier le document d'un autre utilisateur (test).
- Routes `/admin/*` réservées à `is_admin` (403 sinon) ; collecte manuelle limitée (1 / 10 min, verrou, 409 si en cours) ;
  test de source limité à 1 / minute.

## Fichiers

- Contrôle du **type réel par signature binaire** (PDF, PNG, JPEG, DOCX, texte) ; refus si le type annoncé ne correspond pas.
- Taille limitée (4 Mo par défaut) avec rejet précoce des corps trop volumineux (413).
- Stockage hors base, bucket **privé** ; téléchargement par URL signée de 5 min (S3) ou flux authentifié
  `Content-Disposition: attachment`, `Cache-Control: no-store`.
- Noms de fichiers assainis ; clés de stockage générées (`users/<uuid>/<uuid>.ext`) ; protection contre la traversée de chemin (local).

## Secrets

- Aucun secret dans Git (`.gitignore` strict, `.env.example` vide) ; aucune valeur réelle dans `render.yaml`.
- Logs JSON avec **masquage** des chaînes de connexion, jetons Bearer, clés `re_…`/`sk-…`.
- Erreurs génériques côté client (500 « Erreur interne ») ; détails uniquement dans les logs.
- `check-config` affiche seulement « défini / absent ».
- La production refuse de démarrer sans `SECRET_KEY` robuste ou avec une base `localhost`.

## Collecte responsable

- Uniquement des sources publiques et autorisées ; `robots.txt` respecté pour les pages HTML ; délai minimal par hôte ;
  `Retry-After` respecté ; arrêt immédiat sur 401/403/CAPTCHA (**aucun contournement**) ; User-Agent identifiable.

## Ajout d'une offre par lien (URL fournie par l'utilisateur)

- **Protection SSRF** : http/https uniquement, ports 80/443, pas d'identifiants dans l'URL ; le nom d'hôte est résolu
  et **toutes** les adresses doivent être publiques (refus du bouclage, des réseaux privés, link-local dont
  `169.254.169.254`, adresses réservées, IPv6 locales et IPv4 encapsulées) ; contrôle répété **à chaque redirection**
  (5 au plus) ; 3 Mo lus au plus ; délai de 15 s ; types de contenu limités (HTML, JSON, PDF).
- Limite connue : entre la vérification DNS et la connexion, un domaine piégé pourrait changer d'adresse (DNS rebinding).
  Le risque est réduit (aucune réponse brute renvoyée au client, seuls des champs extraits) ; une connexion épinglée sur
  l'adresse vérifiée serait l'étape suivante si nécessaire.
- Mêmes règles que la collecte : `robots.txt` respecté, arrêt sur 401/403, page de connexion ou vérification anti-robot,
  **aucun contournement** ; l'utilisateur complète alors lui-même le formulaire.
- **LinkedIn n'est jamais interrogé** (connexion requise, robots.txt restrictif) : seule l'adresse du lien est analysée ;
  le reste vient du texte que l'utilisateur copie lui-même depuis sa session.
- Rien n'est inventé : champ introuvable = vide ; date trouvée = « à vérifier » tant que l'utilisateur ne la confirme pas ;
  avec l'IA, le texte collé est traité comme une **donnée** (balises dédiées, sortie JSON contrainte par schéma) et chaque
  valeur extraite (intitulé, entreprise, lieu, date via son extrait, durée, documents, critères) doit **figurer dans le texte**,
  sinon elle est écartée — une injection de consignes dans le texte ne peut donc pas introduire de fausse information.
- **Offres personnelles privées** (`owner_user_id`) : filtrées partout (catalogue, détail, favoris, suivi, facettes, tableau
  de bord, calcul des scores, assistant) ; l'offre d'un autre utilisateur répond 404. Modification et suppression réservées à
  l'auteur ; la collecte ne les rattache ni ne les modifie jamais ; supprimées avec le compte.
- Abus limités : 30 analyses / heure et 200 ajouts / jour par utilisateur (les offres privées ne concernent que leur
  auteur) ; la description est affichée comme texte (aucun HTML interprété).

## E-mails

- Destinataires restreints à l'adresse **confirmée** du compte ; les adresses supplémentaires autorisées côté serveur
  (`ALERT_RECIPIENT`, `EMAIL_ALLOWED_RECIPIENTS`) ne sont utilisables que par un administrateur.
- E-mail de test sur confirmation explicite ; mode simulation sans clé Resend.

## Points d'attention / améliorations possibles

- `script-src 'unsafe-inline'` reste nécessaire sans nonce (Next.js) ; un CSP à nonce est possible via `proxy.ts`.
- La limitation par IP dépend de l'en-tête transmis par la passerelle ; la limitation par e-mail reste la protection principale.
- Pas de 2FA : envisageable (TOTP), recommandé pour le compte administrateur si les inscriptions sont ouvertes.
- Pas de CAPTCHA : les plafonds d'inscription limitent l'abus ; un CAPTCHA respectueux (ex. Cloudflare Turnstile)
  peut être ajouté si des inscriptions automatisées apparaissent.
- Ouvrir le service à d'autres personnes implique des obligations (RGPD : information, mentions légales, durée de
  conservation) qui relèvent de l'exploitant ; l'application fournit la suppression de compte et l'isolation des données.
