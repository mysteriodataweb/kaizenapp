"""CLI d'administration.

python -m app.cli create-admin --email moi@example.com     # mot de passe demandé (getpass) ou ADMIN_PASSWORD
python -m app.cli bootstrap-admin                           # idempotent : BOOTSTRAP_ADMIN_EMAIL/PASSWORD, seulement si aucun compte
python -m app.cli seed-sources                              # crée les sources par défaut manquantes (désactivées)
python -m app.cli test-source --key greenhouse-internships  # essai à blanc d'une source
python -m app.cli check-config                              # variables présentes (jamais leurs valeurs)
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import session_scope
from app.models import Source, User
from app.services import auth as auth_service
from app.workers.connectors.registry import seed_sources
from app.workers.ingestion import dry_run_source


def cmd_create_admin(args: argparse.Namespace) -> int:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Mot de passe (12 caractères min.) : ")
    if not os.environ.get("ADMIN_PASSWORD") and getpass.getpass("Confirmation : ") != password:
        print("Les mots de passe ne correspondent pas.", file=sys.stderr)
        return 1
    with session_scope() as db:
        try:
            user = auth_service.create_user(db, args.email, password, is_admin=True, display_name=args.name)
        except AppError as exc:
            print(f"Erreur : {exc.message} {exc.details or ''}", file=sys.stderr)
            return 1
        print(f"Compte administrateur créé : {user.email}")
    return 0


def cmd_bootstrap_admin(_: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as db:
        count = db.scalar(select(func.count()).select_from(User)) or 0
        if count:
            print("Amorçage ignoré : un compte existe déjà.")
            if settings.bootstrap_admin_password:
                print("Conseil : supprimez BOOTSTRAP_ADMIN_PASSWORD de l'environnement.")
            return 0
        if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
            print("Aucun compte et BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD absents : amorçage ignoré.")
            return 0
        try:
            auth_service.create_user(
                db, settings.bootstrap_admin_email, settings.bootstrap_admin_password, is_admin=True
            )
        except AppError as exc:
            print(f"Amorçage impossible : {exc.message} {exc.details or ''}", file=sys.stderr)
            return 1
        print("Compte administrateur amorcé. Supprimez maintenant BOOTSTRAP_ADMIN_PASSWORD de l'environnement.")
    return 0


def cmd_seed_sources(_: argparse.Namespace) -> int:
    with session_scope() as db:
        print(f"{seed_sources(db)} source(s) créée(s).")
    return 0


def cmd_test_source(args: argparse.Namespace) -> int:
    with session_scope() as db:
        src = db.scalar(select(Source).where(Source.key == args.key))
        if src is None:
            print("Source inconnue.", file=sys.stderr)
            return 1
        result = dry_run_source(src)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["ok"] else 2


def cmd_check_config(_: argparse.Namespace) -> int:
    names = [
        "DATABASE_URL",
        "DATABASE_MIGRATION_URL",
        "APP_ENV",
        "SECRET_KEY",
        "CORS_ORIGINS",
        "FRONTEND_URL",
        "RESEND_API_KEY",
        "EMAIL_FROM",
        "ALERT_RECIPIENT",
        "AI_PROVIDER",
        "AI_API_KEY",
        "STORAGE_PROVIDER",
        "STORAGE_BUCKET",
        "STORAGE_ACCESS_KEY",
        "STORAGE_SECRET_KEY",
        "BOOTSTRAP_ADMIN_EMAIL",
        "BOOTSTRAP_ADMIN_PASSWORD",
    ]
    for name in names:
        print(f"{name:28} {'défini' if os.environ.get(name) else 'absent'}")
    problems = get_settings().check_production_ready()
    for p in problems:
        print(f"PROBLÈME : {p}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    configure_logging("WARNING")
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default=None)
    p.set_defaults(func=cmd_create_admin)
    sub.add_parser("bootstrap-admin").set_defaults(func=cmd_bootstrap_admin)
    sub.add_parser("seed-sources").set_defaults(func=cmd_seed_sources)
    p = sub.add_parser("test-source")
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_test_source)
    sub.add_parser("check-config").set_defaults(func=cmd_check_config)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
