"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Importing the packages that only some installs have.

Three capabilities are optional extras (see ``pyproject.toml``): ``sources``
(sentence-transformers + torch, for searching your own uploads), ``pdf``
(PyMuPDF, for mining figures), and ``corpus`` (DuckDB, for the offline S2
citations corpus). Together they are the difference between a 1.0 GB install
and an 83 MB one, and a reader who only wants the graph and the teacher needs
none of them — see ``docs/first-run.md``.

**Every import of an optional package goes through :func:`require`.** Two rules
follow from that, and both are the point of this module existing:

* **Never at module scope.** An eager import turns a missing extra into a
  failure to *start*, rather than a failure to use one feature. That is exactly
  the bug v7.14.0 fixed for LLM providers, and ``corpus/source.py`` had the
  same shape — it imported ``duckdb`` at module level, and
  ``integrations/semantic_scholar/__init__.py`` imports ``corpus``, so an
  install without the corpus extra could not have served a graph.
* **The error has to name the fix.** A bare ``ModuleNotFoundError: No module
  named 'fitz'`` tells a non-developer nothing. :class:`MissingExtra` says
  which capability was wanted and gives the exact command.

Type annotations are exempt: with ``from __future__ import annotations`` a
``TYPE_CHECKING`` import costs nothing at runtime, so modules keep their real
types.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from types import ModuleType

#: What to install for each extra, and what the reader loses without it. Keyed
#: by the extra name in ``pyproject.toml``'s ``[project.optional-dependencies]``.
EXTRAS: dict[str, str] = {
    "sources": "searching your own uploaded books and PDFs",
    "pdf": "showing figures, tables and algorithm boxes from PDFs",
    "corpus": "the offline Semantic Scholar citations corpus",
}


class MissingExtra(RuntimeError):
    """An optional capability was used on an install that doesn't have it.

    A ``RuntimeError`` rather than an ``ImportError`` on purpose: callers that
    already degrade around a broken feature (the sources retriever, the figure
    miner) catch ``Exception`` and carry on, while an ``ImportError`` reads to
    a maintainer like a packaging mistake instead of a supported configuration.
    """


def require(module_name: str, extra: str) -> ModuleType:
    """Import an optional package, or explain how to install it.

    Args:
        module_name: The importable name (``fitz``, not ``pymupdf``).
        extra: The ``pyproject.toml`` extra that provides it — a key of
            :data:`EXTRAS`.

    Returns:
        The imported module.

    Raises:
        MissingExtra: When the package isn't installed, carrying the install
            command for that extra.
        KeyError: When ``extra`` isn't a declared extra — a typo here would
            otherwise produce a confidently wrong install instruction.
    """
    capability = EXTRAS[extra]
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        raise MissingExtra(
            f"This install doesn't include {capability}. "
            f"Add it with:  uv sync --extra {extra}  "
            f"(or, from a published build:  pip install 'atlas[{extra}]')"
        ) from error


def available(extra: str) -> bool:
    """Whether an optional extra is installed, without importing it for real.

    For the *ask before doing* case — deciding whether to offer a capability at
    all, the way the web scout asks ``supports_web_search`` before prompting a
    model to search. Uses ``find_spec``, so a heavy package (torch) is not
    loaded just to answer the question.

    Args:
        extra: A key of :data:`EXTRAS`.

    Returns:
        True when every module backing that extra can be imported.

    Raises:
        KeyError: When ``extra`` isn't a declared extra.
    """
    _ = EXTRAS[extra]
    modules = {"sources": ("sentence_transformers",), "pdf": ("fitz",), "corpus": ("duckdb",)}
    return all(_importable(name) for name in modules[extra])


def _importable(module_name: str) -> bool:
    """Whether a module could be imported, without importing it.

    Checks ``sys.modules`` before asking the import system: a module that is
    already loaded is available whatever the finders say, and that includes one
    a test injected rather than installed (``test_embeddings.py`` supplies a
    fake ``sentence_transformers`` this way, so that the suite never needs
    torch). ``find_spec`` on such a module reports no spec and would call it
    missing.

    Args:
        module_name: The importable name.

    Returns:
        True when the module is loaded or a spec for it can be found.
    """
    if module_name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False
