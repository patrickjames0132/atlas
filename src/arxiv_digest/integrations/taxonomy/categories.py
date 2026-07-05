"""Query the arXiv category taxonomy: the areas tree and the set of valid codes.

Thin domain layer over ``loader.data()`` — the two things the rest of the app
actually asks of the taxonomy: "what areas/categories exist" (to populate a
picker or label a paper's tags) and "is this a real code" (to validate input).
"""

from __future__ import annotations

from functools import lru_cache

from . import loader


def groups() -> list[dict]:
    """List the taxonomy's top-level areas.

    Returns:
        Categories grouped by top-level area; each category is
        ``{"code", "name"}``.
    """
    return loader.data()["groups"]


@lru_cache(maxsize=1)
def valid_codes() -> frozenset[str]:
    """Collect every valid category code.

    Returns:
        A frozenset of all category codes, for validating user selections.
    """
    return frozenset(
        category["code"]
        for group in loader.data()["groups"]
        for category in group["categories"]
    )
