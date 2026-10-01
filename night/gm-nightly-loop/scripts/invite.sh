#!/bin/sh
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
EMPLOYEE=${1:?Usage: scripts/invite.sh employee-id}
case "$EMPLOYEE" in *[!a-zA-Z0-9_-]*|'') printf 'Invalid employee ID\n' >&2; exit 1;; esac
mkdir -p .gm/invites
DEST=".gm/invites/$EMPLOYEE.json"
if [ -e "$DEST" ]; then printf 'Handoff already exists: %s\n' "$DEST" >&2; exit 1; fi
docker compose --env-file .gm/deployment/.env -f deploy/compose.yaml exec -T trainer \
  gm-nightly --config /training/gm-nightly.toml server invite "$EMPLOYEE" --output "/training/$EMPLOYEE.json"
docker compose --env-file .gm/deployment/.env -f deploy/compose.yaml cp "trainer:/training/$EMPLOYEE.json" "$DEST"
chmod 600 "$DEST"
printf 'Private Gbrain handoff saved to %s\n' "$DEST"
