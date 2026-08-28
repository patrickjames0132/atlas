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

# The heavy capabilities are optional extras since v7.15.0 (see
# docs/first-run.md): `sources` (sentence-transformers + torch), `pdf`
# (PyMuPDF) and `corpus` (DuckDB). A local bootstrap installs all of them, so
# `atlas serve` is fully functional — that is what a developer expects here.
#
# ATLAS_SKIP_TORCH=1 drops the `sources` extra, which is where torch lives. CI
# sets it: nothing in the gate needs torch (sentence-transformers is imported
# lazily inside services/sources/embeddings.py's _get_model, and the embedding
# tests inject a fake module), while on Linux installing it drags in the 37
# nvidia-* CUDA packages the lockfile resolves there — multiple GB per cold
# cache. `pdf` and `corpus` are installed either way: their tests build real
# PDFs and query real Parquet, so the gate genuinely needs them, and together
# they are ~100 MB rather than ~900. Keeping it an opt-in env var means CI and
# a local bootstrap stay ONE script.
sync_args=(--all-groups --extra pdf --extra corpus)
if [ "${ATLAS_SKIP_TORCH:-}" != "1" ]; then
  sync_args+=(--extra sources)
fi
uv sync "${sync_args[@]}"
npm install --prefix frontend
npm run build --prefix frontend
