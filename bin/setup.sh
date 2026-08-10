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

# ATLAS_SKIP_TORCH=1 drops torch from the sync. CI sets it: nothing in the gate
# needs torch (sentence-transformers is imported lazily inside
# services/sources/embeddings.py's _get_model, and every test stubs the embedder
# via the stub_embeddings fixture), while on Linux a full sync drags in the
# ~15 nvidia-* CUDA packages the lockfile marks `sys_platform == 'linux'` —
# multiple GB per cold cache. Keeping it an opt-in env var means CI and a local
# bootstrap stay ONE script. Don't set it locally: `atlas serve` needs torch to
# embed anything for real.
sync_args=(--all-groups)
if [ "${ATLAS_SKIP_TORCH:-}" = "1" ]; then
  sync_args+=(--no-install-package torch)
fi
uv sync "${sync_args[@]}"
npm install --prefix frontend
npm run build --prefix frontend
