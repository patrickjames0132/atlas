"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The optional-extras seam: helpful errors, and the invariant that keeps a lean
install able to start.

The last test here is the important one. Everything else checks a message; that
one walks the whole source tree and fails if any module imports an optional
package at module scope, which is the mistake that would silently make a
core-only install unable to boot again.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

from atlas import optional

#: The importable names behind each extra, and the extra that supplies them.
OPTIONAL_MODULES = {"sentence_transformers": "sources", "fitz": "pdf", "duckdb": "corpus"}


def test_require_returns_the_module_when_it_is_installed():
    """The happy path is a plain import — no wrapper, no proxy."""
    assert optional.require("json", "pdf") is __import__("json")


def test_a_missing_extra_names_the_capability_and_the_command(monkeypatch):
    """The whole reason this module exists.

    A bare ``ModuleNotFoundError: No module named 'fitz'`` tells a reader who
    installed Atlas nothing at all, so the message has to say what they lost
    and exactly how to get it.
    """
    monkeypatch.setitem(sys.modules, "nonexistent_pkg", None)
    with pytest.raises(optional.MissingExtra) as caught:
        optional.require("definitely_not_installed_xyz", "pdf")
    message = str(caught.value)
    assert "figures" in message  # what they lost, in their words not ours
    assert "uv sync --extra pdf" in message  # and the exact command


def test_an_undeclared_extra_is_a_loud_mistake():
    """A typo must not produce a confidently wrong install instruction."""
    with pytest.raises(KeyError):
        optional.require("json", "sorces")


def test_available_sees_a_module_that_was_injected_rather_than_installed():
    """`find_spec` alone would call an injected module missing.

    Not hypothetical: `test_embeddings.py` supplies a fake
    ``sentence_transformers`` exactly this way so the suite never needs torch,
    and an `available()` that missed it would disable semantic search under
    test.
    """
    fake = types.ModuleType("sentence_transformers")
    original = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = fake
    try:
        assert optional.available("sources") is True
    finally:
        if original is None:
            del sys.modules["sentence_transformers"]
        else:
            sys.modules["sentence_transformers"] = original


def test_available_is_false_for_something_that_is_not_there():
    """The other half — and it must not raise."""
    assert optional._importable("definitely_not_installed_xyz") is False


def _module_scope_imports(tree: ast.Module) -> set[str]:
    """Every module imported at module scope, ignoring `if TYPE_CHECKING:`.

    A type-only import costs nothing at runtime (every module here uses
    ``from __future__ import annotations``), so it is allowed and skipped.

    Args:
        tree: The parsed module.

    Returns:
        The top-level names imported unconditionally at module scope.
    """
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.If):
            continue  # `if TYPE_CHECKING:` and friends — not executed on import
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_no_module_imports_an_optional_package_at_module_scope():
    """The invariant that lets a core-only install start.

    An eager import turns a missing extra into a failure to *start* rather than
    a failure to use one feature — the same shape as the keyless-startup crash
    fixed in v7.14.0, and `corpus/source.py` really did have it: it imported
    duckdb at module level, and `integrations/semantic_scholar/__init__.py`
    imports corpus, so an install without that extra could not serve a graph.

    Import it inside the function that needs it, through `optional.require`.
    """
    root = Path(optional.__file__).parent
    offenders = []
    for source in sorted(root.rglob("*.py")):
        imported = _module_scope_imports(ast.parse(source.read_text(encoding="utf-8")))
        for name in sorted(imported & OPTIONAL_MODULES.keys()):
            offenders.append(f"{source.relative_to(root)} imports {name} at module scope")
    assert offenders == []
