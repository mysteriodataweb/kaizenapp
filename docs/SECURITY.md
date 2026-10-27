# Sécurité

## Authentification et sessions

- Aucune inscription publique ; compte créé par CLI (`create-admin`, mot de passe saisi via `getpass` ou
  `ADMIN_PASSWORD` à l'exécution) ou amorçage unique (`bootstrap-admin`, uniquement si aucun compte n'existe).
  Aucun mot de passe par défaut n'existe dans le code.
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

## E-mails

- Destinataires restreints à l'adresse du compte et aux adresses explicitement autorisées côté serveur.
- E-mail de test sur confirmation explicite ; mode simulation sans clé Resend.

## Points d'attention / améliorations possibles

- `script-src 'unsafe-inline'` reste nécessaire sans nonce (Next.js) ; un CSP à nonce est possible via `proxy.ts`.
- La limitation par IP dépend de l'en-tête transmis par la passerelle ; la limitation par e-mail reste la protection principale.
- Pas de 2FA (single user) : envisageable (TOTP) si l'application devient multi-utilisateur.
