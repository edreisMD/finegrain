#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
mkdir -p .finegrain/deployment
if [ ! -f .finegrain/deployment/.env ]; then
  python3 scripts/server-env.py .finegrain/deployment/.env
fi
docker compose --env-file .finegrain/deployment/.env -f deploy/compose.yaml up --build -d
printf '\nGbrain company dashboard: http://localhost:3131/admin/\nFinegrain training console: http://localhost:8787\nOwner credential: .finegrain/deployment/owner-token (private)\n'
