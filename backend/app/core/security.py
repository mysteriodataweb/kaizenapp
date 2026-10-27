"""Hachage des mots de passe (Argon2id) et jetons opaques."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id, paramètres recommandés par argon2-cffi

MIN_PASSWORD_LENGTH = 12
# Hachage factice pour équilibrer le temps de réponse quand l'utilisateur n'existe pas.
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, email: str | None = None) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Au moins {MIN_PASSWORD_LENGTH} caractères requis.")
    if len(password) > 256:
        problems.append("256 caractères maximum.")
    if password.strip() != password:
        problems.append("Pas d'espace au début ou à la fin.")
    if email and email.split("@")[0].lower() in password.lower() and len(email.split("@")[0]) >= 4:
        problems.append("Le mot de passe ne doit pas contenir votre identifiant e-mail.")
    if len(set(password)) < 6:
        problems.append("Mot de passe trop répétitif.")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def keyed_hash(secret_key: str, value: str) -> str:
    """Empreinte HMAC (ex. adresse IP) pour limiter le débit sans stocker la donnée brute."""
    return hmac.new(secret_key.encode() or b"dev", value.encode(), hashlib.sha256).hexdigest()
