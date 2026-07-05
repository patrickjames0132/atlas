"""Semantic Scholar's fields of study — S2's coarse subject vocabulary.

Where the sibling ``arxiv`` module holds arXiv's ~155 fine-grained codes, this
holds S2's own much coarser ~20 top-level fields (Computer Science, Mathematics,
…). It's what powers the S2 seed-search filter: S2's ``/paper/search`` filters
on exactly these (``fieldsOfStudy``).

Fixed, S2-defined vocabulary, small enough to inline (no bundled JSON like the
arXiv side). Each value is already human-readable — the field *is* its own label
— so there's no ``code → name`` mapping. Title Case with spaces, matching what
S2 returns on a paper's ``fieldsOfStudy`` and accepts in the filter.
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
