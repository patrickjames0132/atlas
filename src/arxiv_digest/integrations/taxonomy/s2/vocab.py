"""The Semantic Scholar fields-of-study list and its accessors.

The implementation behind the ``taxonomy.s2`` package. See the package
``__init__`` for the what/why.
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
