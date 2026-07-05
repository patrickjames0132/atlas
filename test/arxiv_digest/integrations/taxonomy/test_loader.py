"""loader: parsing + memoizing the bundled taxonomy.json (real file, no network)."""

from __future__ import annotations

from arxiv_digest.integrations.taxonomy import loader


def test_data_returns_the_parsed_document():
    document = loader.data()
    assert isinstance(document, dict)
    assert isinstance(document["groups"], list) and document["groups"]


def test_data_is_memoized():
    # lru_cache returns the same object on repeat calls (parsed once).
    assert loader.data() is loader.data()
