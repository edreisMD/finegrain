#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
./scripts/install-gbrain.sh
if ! command -v uv >/dev/null 2>&1; then
  printf 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/\n' >&2
  exit 1
fi
uv tool install --python 3.12 --force .
finegrain employee install "$@"
if [ "$(uname -s)" = Darwin ]; then
  ./scripts/build-macos.sh
  mkdir -p "$HOME/Applications"
  ditto dist/Finegrain.app "$HOME/Applications/Finegrain.app"
  open "$HOME/Applications/Finegrain.app"
fi
