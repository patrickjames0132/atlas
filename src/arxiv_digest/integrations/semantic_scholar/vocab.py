"""Semantic Scholar's fields of study — S2's coarse subject vocabulary.

S2's own ~20 top-level fields (Computer Science, Mathematics, …) — what the S2
seed-search filter uses: ``/paper/search`` filters on exactly these
(``fieldsOfStudy``). A fixed, S2-defined vocabulary, small enough to inline as a
tuple (no data file); each value is already its own human-readable label. Title
Case, matching what S2 returns on paper objects and accepts in the filter.

Lives in the ``semantic_scholar`` package because it's S2's vocabulary; arXiv's
parallel (finer) one is ``arxiv.vocab``. See the package README for details.
"""

from __future__ import annotations

# S2's fieldsOfStudy values, alphabetical. If S2 ever changes the vocabulary or
# the casing turns out different live, this one tuple is the only thing to edit.
FIELDS: tuple[str, ...] = (
    "Agricultural and Food Sciences",
    "Art",
    "Biology",
    "Business",
    "Chemistry",
    "Computer Science",
    "Economics",
    "Education",
    "Engineering",
    "Environmental Science",
    "Geography",
    "Geology",
    "History",
    "Law",
    "Linguistics",
    "Materials Science",
    "Mathematics",
    "Medicine",
    "Philosophy",
    "Physics",
    "Political Science",
    "Psychology",
    "Sociology",
)


def fields() -> list[str]:
    """List the S2 fields of study.

    Returns:
        The fields in a stable (alphabetical) order, for populating the search
        filter's picker.
    """
    return list(FIELDS)


def valid_fields() -> frozenset[str]:
    """Collect the valid S2 fields of study.

    Returns:
        A frozenset of the field names, for validating a submitted filter (an
        unknown field can only come from a stale/forged client).
    """
    return frozenset(FIELDS)
