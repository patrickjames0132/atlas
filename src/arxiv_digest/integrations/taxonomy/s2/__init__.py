"""Semantic Scholar's fields of study — S2's coarse subject vocabulary.

Where the sibling ``arxiv`` package holds arXiv's ~155 fine-grained codes, this
holds S2's own much coarser ~20 top-level fields (Computer Science, Mathematics,
…). It's what powers the S2 seed-search filter: S2's ``/paper/search`` filters
on exactly these (``fieldsOfStudy``).

Fixed, S2-defined vocabulary, small enough to inline (no bundled JSON like the
arXiv side). Each value is already human-readable — the field *is* its own label
— so there's no ``code → name`` mapping. Title Case with spaces, matching what
S2 returns on a paper's ``fieldsOfStudy`` and accepts in the filter.

The list + accessors live in ``vocab.py``; this package re-exports its public API.
"""

from __future__ import annotations

from .vocab import fields, valid_fields

__all__ = ["fields", "valid_fields"]
