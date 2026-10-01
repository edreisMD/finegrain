#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
mkdir -p .gm/deployment
if [ ! -f .gm/deployment/.env ]; then
  python3 scripts/server-env.py .gm/deployment/.env
fi
docker compose --env-file .gm/deployment/.env -f deploy/compose.yaml up --build -d
printf '\nGbrain company dashboard: http://localhost:3131/admin/\nGM Nightly Loop training console: http://localhost:8787\nOwner credential: .gm/deployment/owner-token (private)\n'
