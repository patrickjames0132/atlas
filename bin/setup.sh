#!/usr/bin/env bash
# Session bootstrap — run this first thing when a Claude Code session opens.
#
# Installs the pinned toolchain from .tool-versions via mise (python, uv,
# nodejs, trivy), syncs the backend env, and installs + builds the frontend so
# the working tree starts green. Cheap when everything is already current.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v mise >/dev/null 2>&1; then
  mise install
  mise reshim
else
  echo "warning: mise not found — skipping pinned-tool install (https://mise.jdx.dev)" >&2
fi

uv sync
npm install --prefix frontend
npm run build --prefix frontend
