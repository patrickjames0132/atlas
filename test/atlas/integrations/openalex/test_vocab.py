"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
openalex.vocab: the 26 top-level OpenAlex fields (id + name), for the
seed-search filter picker.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations.openalex import vocab


def test_fields_are_id_name_pairs():
    fields = vocab.fields()
    assert len(fields) == 26  # OpenAlex's 26 top-level fields
    assert {"id": "17", "name": "Computer Science"} in fields
    assert all(field["id"] and field["name"] for field in fields)


def test_valid_field_ids_accepts_ids_not_names():
    ids = vocab.valid_field_ids()
    assert "17" in ids  # Computer Science's id
    assert "Computer Science" not in ids  # the name is not a valid filter value
    assert "999" not in ids
