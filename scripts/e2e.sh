#!/usr/bin/env bash
# Tests end-to-end locaux : base PostgreSQL dédiée (jamais la production), API + frontend.
# Prérequis : PostgreSQL local, backend/.venv installé, apps/web/node_modules installé, build Next effectué.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E2E_DB_URL="${E2E_DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/oi_e2e}"
API_PORT="${E2E_API_PORT:-8001}"
WEB_PORT="${E2E_WEB_PORT:-3001}"
PY="${PYTHON:-$ROOT/backend/.venv/bin/python}"
STORAGE="$(mktemp -d)"

cleanup() { kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true; rm -rf "$STORAGE"; }
trap cleanup EXIT

cd "$ROOT/backend"
DATABASE_URL="$E2E_DB_URL" STORAGE_LOCAL_DIR="$STORAGE" "$PY" -m tests.e2e_seed
DATABASE_URL="$E2E_DB_URL" STORAGE_LOCAL_DIR="$STORAGE" ALLOW_REGISTRATION=true CORS_ORIGINS="http://localhost:$WEB_PORT" \
  FRONTEND_URL="http://localhost:$WEB_PORT" SECRET_KEY="e2e-local-secret-key-0123456789abcdef" \
  "$PY" -m uvicorn app.main:app --port "$API_PORT" >/tmp/oi-e2e-api.log 2>&1 &
API_PID=$!

cd "$ROOT/apps/web"
BACKEND_API_URL="http://localhost:$API_PORT" NEXT_PUBLIC_APP_URL="http://localhost:$WEB_PORT" \
  npx next start -p "$WEB_PORT" >/tmp/oi-e2e-web.log 2>&1 &
WEB_PID=$!

for _ in $(seq 1 60); do
  if curl -fs "http://localhost:$API_PORT/api/v1/health" >/dev/null && curl -fs -o /dev/null "http://localhost:$WEB_PORT/login"; then break; fi
  sleep 1
done
E2E_BASE_URL="http://localhost:$WEB_PORT" npx playwright test "$@"
