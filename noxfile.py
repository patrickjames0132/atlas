"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Quality gate for arXiv Atlas — run every check with ``uv run nox``.

Five sessions, all run by default: ``precommit`` (pre-commit hooks, incl. ruff
and the frontend's prettier/oxlint), ``mypy`` (type checks), ``tests``
(pytest), ``vitest`` (the frontend suite in ``frontend/test``), and
``security`` (a Trivy filesystem scan). Sessions reuse the active uv
environment (``venv_backend="none"``) rather than building their own, so
``uv run nox`` needs no per-session installs — the Python tools come from the
``dev`` dependency group; vitest comes from ``frontend/node_modules`` (the
session-start ``bin/setup`` installs it).

Trivy is an external binary (not a Python package); the ``security`` session
skips itself cleanly when ``trivy`` isn't on PATH (as ``vitest`` does without
npm), so ``uv run nox`` stays green on machines that don't have it installed.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import shutil

import nox

# Reuse the uv-managed env; don't spin up a venv per session.
nox.options.default_venv_backend = "none"
# Bare `uv run nox` runs all five gates, in this order.
nox.options.sessions = ["precommit", "mypy", "tests", "vitest", "security"]


@nox.session
def precommit(session: nox.Session) -> None:
    """Run every pre-commit hook (file hygiene + ruff lint) over the whole tree."""
    session.run("pre-commit", "run", "--all-files", external=True)


@nox.session
def mypy(session: nox.Session) -> None:
    """Type-check the backend package (config in ``pyproject.toml``)."""
    session.run("mypy")


@nox.session
def tests(session: nox.Session) -> None:
    """Run the unit-test suite (``test/``), passing through any extra args."""
    session.run("pytest", *session.posargs)


@nox.session
def vitest(session: nox.Session) -> None:
    """Run the frontend test suite (``frontend/test``, Vitest; skipped without npm).

    Args:
        session: The nox session (pass-through args go to vitest).
    """
    if shutil.which("npm") is None:
        session.skip("npm not on PATH — install Node to enable the frontend tests")
    session.run(
        "npm", "run", "test", "--prefix", "frontend", "--silent", "--", *session.posargs,
        external=True,
    )


@nox.session
def security(session: nox.Session) -> None:
    """Scan the repo for known vulnerabilities with Trivy (skipped if absent)."""
    if shutil.which("trivy") is None:
        session.skip("trivy not on PATH — install it to enable the security scan")
    session.run("trivy", "fs", "--scanners", "vuln,secret", ".", external=True)
