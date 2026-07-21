"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
OpenAlex's top-level fields — its coarse subject vocabulary for the seed-search
filter (the OpenAlex counterpart of ``semantic_scholar.vocab``).

OpenAlex classifies works with a four-level topic hierarchy (domain → field →
subfield → topic). The **field** tier is the coarse level worth filtering on — 26
Scopus-derived subjects, the natural analogue of S2's ~20 fields of study. Each
field has a numeric OpenAlex id (``fields/17`` = Computer Science); the search
filter is ``topics.field.id:fields/<id>``. A fixed, OpenAlex-defined list, small
enough to inline (no data file, no live ``/fields`` call).

Unlike S2's fields (where the display name *is* the filter value), an OpenAlex
field has a distinct **id** (sent to the API) and **name** (shown to the user), so
this vocabulary is id→name pairs.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

# OpenAlex field ids (the numeric part of ``fields/<id>``) → display name. The 26
# top-level fields of OpenAlex's topic hierarchy. If OpenAlex ever revises them,
# this one mapping is the only thing to edit.
FIELDS: tuple[tuple[str, str], ...] = (
    ("11", "Agricultural and Biological Sciences"),
    ("12", "Arts and Humanities"),
    ("13", "Biochemistry, Genetics and Molecular Biology"),
    ("14", "Business, Management and Accounting"),
    ("15", "Chemical Engineering"),
    ("16", "Chemistry"),
    ("17", "Computer Science"),
    ("18", "Decision Sciences"),
    ("19", "Earth and Planetary Sciences"),
    ("20", "Economics, Econometrics and Finance"),
    ("21", "Energy"),
    ("22", "Engineering"),
    ("23", "Environmental Science"),
    ("24", "Immunology and Microbiology"),
    ("25", "Materials Science"),
    ("26", "Mathematics"),
    ("27", "Medicine"),
    ("28", "Neuroscience"),
    ("29", "Nursing"),
    ("30", "Pharmacology, Toxicology and Pharmaceutics"),
    ("31", "Physics and Astronomy"),
    ("32", "Psychology"),
    ("33", "Social Sciences"),
    ("34", "Veterinary"),
    ("35", "Dentistry"),
    ("36", "Health Professions"),
)


def fields() -> list[dict[str, str]]:
    """List the OpenAlex fields as ``{id, name}`` pairs.

    Returns:
        The fields in a stable order (by id), each ``{"id": ..., "name": ...}``,
        for populating the search filter's picker — the id is the filter value,
        the name the label.
    """
    return [{"id": field_id, "name": name} for field_id, name in FIELDS]


def valid_field_ids() -> frozenset[str]:
    """Collect the valid OpenAlex field ids.

    Returns:
        A frozenset of the field ids, for validating a submitted filter (an
        unknown id can only come from a stale/forged client).
    """
    return frozenset(field_id for field_id, _name in FIELDS)
