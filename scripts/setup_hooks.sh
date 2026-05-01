#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

git config core.hooksPath .githooks
VALUE="$(git config --get core.hooksPath || true)"

echo "CORE_HOOKS_PATH=$VALUE"

if [[ "$VALUE" != ".githooks" ]]; then
  echo "CORE_HOOKS_PATH_NOT_SET=$VALUE" >&2
  exit 1
fi

if [[ ! -f ".githooks/pre-commit" ]]; then
  echo "PRE_COMMIT_HOOK_MISSING" >&2
  exit 1
fi

echo "SETUP_HOOKS_OK=1"
