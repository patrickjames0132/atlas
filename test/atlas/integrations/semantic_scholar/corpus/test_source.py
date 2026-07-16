"""The query side: seed resolution, citation-sorted landmarks, the latest split,
and graceful fallback when the corpus is absent.
"""

from __future__ import annotations

from atlas.config import config
from atlas.integrations.semantic_scholar.corpus import source
from atlas.services.graph.model import Node


def test_active_source_none_when_corpus_off():
    """With no corpus configured (the autouse default), there's no source."""
    assert config.storage.s2_corpus_dir is None
    assert source.active_source() is None


def test_citation_relations_none_without_corpus():
    """The build's entry point returns None (fall back to live) when off."""
    assert source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    ) is None


def test_active_source_present_with_corpus(synthetic_corpus):
    """An ingested, activated release yields a ready source."""
    assert source.active_source() is not None


def test_resolve_corpus_id_via_arxiv(synthetic_corpus):
    """A seed's arXiv id resolves to its corpus id through the arXiv index."""
    src = source.active_source()
    assert src.resolve_corpus_id("1706.03762", "1706.03762") == 1


def test_resolve_corpus_id_via_corpusid_ref(synthetic_corpus):
    """A ``CorpusId:<n>`` re-seed resolves without an arXiv id."""
    src = source.active_source()
    assert src.resolve_corpus_id(None, "CorpusId:1") == 1
    assert src.resolve_corpus_id(None, "corpusid:4") == 4


def test_resolve_corpus_id_unresolvable(synthetic_corpus):
    """A raw S2 paperId hash (not in the corpus) can't resolve locally."""
    src = source.active_source()
    assert src.resolve_corpus_id(None, "0f1e2d3c-hash") is None
    assert src.resolve_corpus_id("9999.99999", "9999.99999") is None


def test_landmark_citers_are_citation_sorted(synthetic_corpus):
    """Landmarks come back most-cited first — the fix the live API can't give."""
    landmark, _latest = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2", "CorpusId:4"]
    assert [entry["node"]["citation_count"] for entry in landmark] == [80000, 50000]
    # The recent paper is in the latest window, not a landmark.
    assert all(entry["node"]["id"] != "CorpusId:3" for entry in landmark)


def test_landmark_carries_influential_flag(synthetic_corpus):
    """The edge's ``isinfluential`` rides through to the entry."""
    landmark, _ = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    by_id = {entry["node"]["id"]: entry for entry in landmark}
    assert by_id["CorpusId:2"]["influential"] is True
    assert by_id["CorpusId:4"]["influential"] is False


def test_landmark_limit_trims_least_cited(synthetic_corpus):
    """A landmark limit keeps the most-cited (BERT), drops GPT-3."""
    landmark, _ = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=1, latest_limit=None
    )
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2"]


def test_latest_split(synthetic_corpus):
    """The recent-window citer lands in ``latest``, not landmarks."""
    _landmark, latest = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    assert [entry["node"]["id"] for entry in latest] == ["CorpusId:3"]


def test_authors_formatted(synthetic_corpus):
    """Multi-author papers format as a comma-joined display string."""
    landmark, _ = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    by_id = {entry["node"]["id"]: entry["node"] for entry in landmark}
    assert by_id["CorpusId:2"]["authors"] == "Devlin, Chang"


def test_emitted_node_satisfies_model(synthetic_corpus):
    """A corpus citer's dict is a valid graph ``Node`` (extra keys forbidden)."""
    landmark, _ = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    node = Node(**landmark[0]["node"], rels=["citation"], is_seed=False)
    assert node.id == "CorpusId:2"
    assert node.arxiv_id == "1810.04805"
    assert node.url == "https://arxiv.org/abs/1810.04805"


def test_non_arxiv_citer_url_uses_corpusid(synthetic_corpus):
    """A citer without an arXiv id gets a CorpusID-based S2 URL."""
    _landmark, latest = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    node = latest[0]["node"]  # the recent paper has no external ids
    assert node["url"] == "https://www.semanticscholar.org/paper/CorpusID:3"
    assert node["arxiv_id"] is None


def test_citers_are_deduped_across_export_batches(synthetic_corpus):
    """S2 re-ships edges across overlapping export batches, so a citer must still
    appear ONCE. Without this the limit counts rows rather than papers and halves
    the relation — DQN's budget of 63 bought ~32 real landmarks."""
    landmark, _latest = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    ids = [entry["node"]["id"] for entry in landmark]
    assert ids == ["CorpusId:2", "CorpusId:4"]  # each once, despite the second batch
    assert len(ids) == len(set(ids))


def test_a_limit_counts_papers_not_duplicate_rows(synthetic_corpus):
    """The bug this guards: `LIMIT 1` over un-deduped rows could return one row
    that's a *second copy* of a citer — spending the budget on nothing."""
    landmark, _latest = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=1, latest_limit=None
    )
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2"]  # the most-cited


def test_influential_is_or_ed_across_duplicate_edges(synthetic_corpus):
    """The batches disagree: BERT's edge is influential in the first and not in the
    second. The flag is a claim that *some* record marks it influential, so OR."""
    landmark, _latest = source.citation_relations(
        {"arxiv_id": "1706.03762"}, "1706.03762", landmark_limit=None, latest_limit=None
    )
    by_id = {entry["node"]["id"]: entry for entry in landmark}
    assert by_id["CorpusId:2"]["influential"] is True   # True in batch 1, False in batch 2
    assert by_id["CorpusId:4"]["influential"] is False  # False in both
