"""Recognizing arXiv ids: ID_RE, extraction from pasted text (extract_id),
and whole-string discrimination (looks_arxiv)."""

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


def test_extract_id_strips_url_wrapping_and_version():
    assert arxiv.extract_id("https://arxiv.org/abs/1312.5602v2") == "1312.5602"
    assert arxiv.extract_id("  1312.5602  ") == "1312.5602"
    assert arxiv.extract_id("attention is all you need") is None
    assert arxiv.extract_id("") is None


def test_looks_arxiv_discriminates_ids_from_paperids():
    assert arxiv.looks_arxiv("1312.5602") is True
    assert arxiv.looks_arxiv("1312.5602v2") is True
    assert arxiv.looks_arxiv("649def34f8be52c8b66281af98ae884c09aef38b") is False
    assert arxiv.looks_arxiv("https://arxiv.org/abs/1312.5602") is True
