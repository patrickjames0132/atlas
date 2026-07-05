"""taxonomy.s2: the S2 fields-of-study vocabulary (fields + valid_fields)."""

from __future__ import annotations

from arxiv_digest.integrations.taxonomy import s2


def test_fields_are_the_expected_vocabulary():
    listed = s2.fields()
    assert len(listed) == 23  # S2's documented fields of study
    assert "Computer Science" in listed
    assert "Mathematics" in listed
    assert listed == sorted(listed)  # stable alphabetical order for the picker


def test_valid_fields_matches_the_listed_fields_and_rejects_junk():
    valid = s2.valid_fields()
    assert valid == set(s2.fields())
    assert "Computer Science" in valid
    assert "cs.LG" not in valid  # an arXiv code is not an S2 field
    assert "Underwater Basket Weaving" not in valid
