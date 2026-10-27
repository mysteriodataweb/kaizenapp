"""Recalcul des scores obsolètes. Usage : python -m app.jobs.recompute_matches [--force]"""

from __future__ import annotations

import argparse

from app.jobs._runner import main
from app.services import matching

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Recalcule tous les scores")
    args = parser.parse_args()
    main("recompute_matches", lambda db: {"recomputed": matching.recompute_all(db, force=args.force)})
