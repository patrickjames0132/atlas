"""ID_RE: recognizing a bare or URL-wrapped arXiv id (now homed in the arxiv package)."""

from __future__ import annotations

import pytest

from arxiv_digest.integrations import arxiv


@pytest.mark.parametrize(
    "text,expected_id",
    [
        ("2406.12345", "2406.12345"),
        ("2406.12345v2", "2406.12345v2"),
        ("hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/abs/2406.12345", "2406.12345"),
        ("https://arxiv.org/pdf/2406.12345v1", "2406.12345v1"),
    ],
)
def test_id_re_matches_bare_and_wrapped_ids(text, expected_id):
    match = arxiv.ID_RE.fullmatch(text)
    assert match is not None and match.group(1) == expected_id


def test_id_re_does_not_match_keywords():
    assert arxiv.ID_RE.fullmatch("attention is all you need") is None
