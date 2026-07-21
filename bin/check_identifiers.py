"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Pre-commit hook: no single-letter identifiers, in ``.py`` and ``.ipynb`` alike.

Mechanizes the CLAUDE.md naming convention — every binding is named for what
it holds (``node`` not ``n``, ``query`` not ``q``). Ruff has no
minimum-identifier-length rule (E741 only bans the ambiguous ``l``/``I``/``O``),
so this walks the AST itself and flags every single-character *binding*:
assignments (including walrus), loop and comprehension targets, function/lambda
parameters, ``with``/``except``/import aliases, function and class names,
``global``/``nonlocal`` declarations, ``match`` captures, and PEP 695 type
parameters. Attribute access is deliberately out of scope — external property
names we don't own (a react-force-graph ``node.x``, a paper's ``_s`` field)
are reads, not bindings. The lone allowed single character is ``_``, the
established pure-discard idiom (``for _, chunk in chunk_rows``).

Notebook code cells are parsed individually and reported ruff-style
(``cell N`` = Nth code cell, 1-based); a cell that doesn't parse as plain
Python (e.g. IPython magics) is skipped — ruff's own rules still cover it.

Usage: ``python bin/check_identifiers.py FILE [FILE ...]`` (pre-commit passes
the staged files). Exits 1 if any violation is found.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ALLOWED = {"_"}


def _bindings(tree: ast.AST) -> list[tuple[int, str, str]]:
    """Collect single-letter bindings as (line, name, kind) triples.

    Args:
        tree: Parsed module to walk.

    Returns:
        list[tuple[int, str, str]]: One triple per violation, in source order.
    """
    found: list[tuple[int, str, str]] = []

    def check(name: str | None, line: int, kind: str) -> None:
        """Record ``name`` if it is a disallowed single-character binding.

        Args:
            name: The bound identifier, or None when the construct binds nothing.
            line: 1-based source line of the binding.
            kind: Human-readable binding kind for the report.
        """
        if name is not None and len(name) == 1 and name not in ALLOWED:
            found.append((line, name, kind))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            check(node.id, node.lineno, "assignment")
        elif isinstance(node, ast.arg):
            check(node.arg, node.lineno, "parameter")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            check(node.name, node.lineno, "function name")
        elif isinstance(node, ast.ClassDef):
            check(node.name, node.lineno, "class name")
        elif isinstance(node, ast.ExceptHandler):
            check(node.name, node.lineno, "except alias")
        elif isinstance(node, ast.alias):
            check(node.asname, getattr(node, "lineno", 0), "import alias")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                check(name, node.lineno, "global/nonlocal")
        elif isinstance(node, ast.MatchAs):
            check(node.name, node.lineno, "match capture")
        elif isinstance(node, ast.MatchStar):
            check(node.name, node.lineno, "match capture")
        elif isinstance(node, ast.MatchMapping):
            check(node.rest, node.lineno, "match capture")
        elif isinstance(node, (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)):
            check(node.name, node.lineno, "type parameter")

    return sorted(found)


def _check_python(path: Path) -> list[str]:
    """Check one ``.py`` file.

    Args:
        path: File to parse.

    Returns:
        list[str]: Formatted violation lines, empty when clean.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path}:{line}: single-letter {kind} `{name}` — name it for what it holds"
        for line, name, kind in _bindings(tree)
    ]


def _check_notebook(path: Path) -> list[str]:
    """Check every code cell of one ``.ipynb`` file.

    Args:
        path: Notebook to parse.

    Returns:
        list[str]: Formatted violation lines, empty when clean.
    """
    notebook = json.loads(path.read_text(encoding="utf-8"))
    violations: list[str] = []
    code_cell_number = 0
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        code_cell_number += 1
        source = "".join(cell.get("source", []))
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue  # magics etc. — not plain Python, ruff's cell handling covers it
        violations.extend(
            f"{path}:cell {code_cell_number}:{line}: single-letter {kind} `{name}`"
            f" — name it for what it holds"
            for line, name, kind in _bindings(tree)
        )
    return violations


def main(argv: list[str]) -> int:
    """Check every file named on the command line.

    Args:
        argv: File paths (pre-commit passes the staged ``.py``/``.ipynb`` files).

    Returns:
        int: 0 when clean, 1 when any violation was found.
    """
    violations: list[str] = []
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix == ".ipynb":
            violations.extend(_check_notebook(path))
        else:
            violations.extend(_check_python(path))
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
