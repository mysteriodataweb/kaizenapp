"""Prépare une base LOCALE pour les tests end-to-end (jamais la production).

Exécute le vrai pipeline de collecte sur les jeux de données de test (transport HTTP simulé),
puis crée un compte, un profil et calcule les scores.

Usage : DATABASE_URL=postgresql://postgres:postgres@localhost:5432/oi_e2e python -m tests.e2e_seed
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine, session_scope
from app.models import Profile, Source
from app.services import auth as auth_service
from app.services import matching
from app.workers.connectors.registry import seed_sources
from app.workers.ingestion import run_source
from tests.test_ingestion import load, mock_http

E2E_EMAIL = "e2e@example.com"
E2E_PASSWORD = "E2e-Mot-de-passe-2026"


def main() -> int:
    url = get_settings().database_url
    if "localhost" not in url and "127.0.0.1" not in url:
        print("Refus : la base e2e doit être locale.", file=sys.stderr)
        return 1
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")

    with session_scope() as db:
        seed_sources(db)
        user = auth_service.create_user(db, E2E_EMAIL, E2E_PASSWORD, is_admin=True, display_name="Awa")
        gh = db.query(Source).filter_by(key="greenhouse-internships").one()
        gh.config = {"boards": [{"token": "exemple", "organization": "Exemple SA"}]}
        gh.rate_limit_seconds = 1
        em = db.query(Source).filter_by(key="erasmus-mundus-catalogue").one()
        em.config = {"max_pages": 1}
        rss = db.query(Source).filter_by(key="rss-feeds").one()
        rss.config = {
            "feeds": [
                {
                    "url": "https://www.univ-exemple.fr/feed",
                    "type": "auto",
                    "organization": "Université Exemple",
                    "official": True,
                    "countries": ["FR"],
                }
            ]
        }
        db.commit()
        catalogue = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
        run_source(
            db,
            gh,
            http=mock_http({"https://boards-api.greenhouse.io/v1/boards/exemple/jobs": load("greenhouse_jobs.json")}),
            triggered_by="test",
        )
        run_source(db, em, http=mock_http({catalogue: load("erasmus_catalogue.html")}), triggered_by="test")
        # Date limite relative à aujourd'hui pour exercer les rappels et l'urgence.
        deadline = (datetime.now(UTC) + timedelta(days=5)).strftime("%d/%m/%Y")
        feed = load("feed.xml").replace("15 janvier 2027", deadline)
        run_source(db, rss, http=mock_http({"https://www.univ-exemple.fr/feed": feed}), triggered_by="test")
        db.add(
            Profile(
                user_id=user.id,
                full_name="Awa Diop",
                nationalities=["SN"],
                study_level="bachelor",
                field_of_study="Informatique",
                skills=["Python", "SQL", "React"],
                languages=[{"code": "fr", "level": "native"}, {"code": "en", "level": "B2"}],
                target_countries=["DE", "FR"],
                funding_preference="full_or_partial",
                program_types=["internship", "masters_scholarship"],
                version=2,
            )
        )
        db.commit()
        matching.recompute_for_user(db, user)
        db.commit()
    print(f"Base e2e prête. Compte : {E2E_EMAIL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
