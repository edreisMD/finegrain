#!/bin/sh
set -eu
# Canonical upstream distribution, pinned to the version verified with Finegrain.
if ! command -v bun >/dev/null 2>&1; then
  printf 'Install Bun first: https://bun.com/docs/installation\n' >&2
  exit 1
fi
if command -v gbrain >/dev/null 2>&1; then
  printf 'Using your existing Gbrain installation.\n'
  gbrain --version
else
  bun install -g github:garrytan/gbrain#e78f1c38b947b053f3a46881340f74f316be855a
fi
