"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The query side: seed resolution, citation-sorted landmarks, the latest bands,
and graceful fallback when the corpus is absent.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.config import config
from atlas.integrations.semantic_scholar.corpus import source
from atlas.services.graph.model import Node

# The year bounds a real build passes in (``openalex.landmark_max_year(today)`` and
# today's year). Pinned rather than derived from the clock so these tests don't
# start failing on New Year's Day. Against the synthetic corpus this puts BERT
# (2018) and GPT-3 (2020) in the landmark era and the 2026 paper in the bands.
MAX_LANDMARK_YEAR = 2024
CURRENT_YEAR = 2026


def relations(**overrides):
    """``citation_relations`` for the synthetic seed, with a build's boundary args.

    Args:
        **overrides: Any argument to override (e.g. ``landmark_budget=...``).

    Returns:
        Whatever ``citation_relations`` returns — ``(landmark, latest)`` or None.
    """
    kwargs = {
        "max_landmark_year": MAX_LANDMARK_YEAR,
        "current_year": CURRENT_YEAR,
    }
    kwargs.update(overrides)
    return source.citation_relations({"arxiv_id": "1706.03762"}, "1706.03762", **kwargs)


def test_active_source_none_when_corpus_off():
    """With no corpus configured (the autouse default), there's no source."""
    assert config.storage.s2_corpus is None
    assert source.active_source() is None


def test_active_source_survives_deleted_shards(synthetic_corpus):
    """Serving must not depend on the raw shards: CURRENT lives beside the
    Parquet, so a machine whose shards are deleted after ingest keeps serving."""
    import shutil

    from atlas.integrations.semantic_scholar.corpus.paths import release_paths

    shutil.rmtree(release_paths(synthetic_corpus).raw)
    assert source.active_source() is not None
    landmark, _latest = relations()
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2", "CorpusId:4"]


def test_citation_relations_none_without_corpus():
    """The build's entry point returns None (fall back to live) when off."""
    assert relations() is None


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
    landmark, _latest = relations()
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2", "CorpusId:4"]
    assert [entry["node"]["citation_count"] for entry in landmark] == [80000, 50000]
    # The recent paper is in the latest window, not a landmark.
    assert all(entry["node"]["id"] != "CorpusId:3" for entry in landmark)


def test_landmark_carries_influential_flag(synthetic_corpus):
    """The edge's ``isinfluential`` rides through to the entry."""
    landmark, _ = relations()
    by_id = {entry["node"]["id"]: entry for entry in landmark}
    assert by_id["CorpusId:2"]["influential"] is True
    assert by_id["CorpusId:4"]["influential"] is False


def test_payload_guard_trims_least_cited(synthetic_corpus, monkeypatch):
    """The payload guard keeps the most-cited (BERT), drops GPT-3."""
    monkeypatch.setattr(source, "UNBOUNDED_LANDMARK_CAP", 1)
    landmark, _ = relations()
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2"]


def test_landmark_budget_measures_the_whole_ranked_pool(synthetic_corpus, monkeypatch):
    """A supplied budget rule sees the FULL ranking, not a pre-trimmed prefix.

    The point of the v5.11.0 change: the corpus stopped pushing a predicted count
    into the query and started measuring the real pool. So the rule must be handed
    every ranked citer, or it is measuring the very trim it was meant to decide.
    """
    monkeypatch.setattr(source, "UNBOUNDED_LANDMARK_CAP", 1)
    seen: dict[str, object] = {}

    def take_the_second_only(citer_years):
        seen["years"] = list(citer_years)
        return 2

    landmark, _ = relations(landmark_budget=take_the_second_only)
    # It saw both landmarks despite the guard of 1 — the guard is not applied
    # ahead of the rule, which is the whole change. (Citation rank: BERT 2018 with
    # 80k, then GPT-3 2020 with 50k — so the years arrive ranked, not chronological.)
    assert seen["years"] == [2018, 2020]
    # And its count won over the guard: a prefix of the citation ranking.
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2", "CorpusId:4"]


def test_landmark_budget_declining_falls_back_to_the_flat_guard(synthetic_corpus, monkeypatch):
    """A rule returning None (the adaptive toggle is off) yields the guard."""
    monkeypatch.setattr(source, "UNBOUNDED_LANDMARK_CAP", 1)
    landmark, _ = relations(landmark_budget=lambda citer_years: None)
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2"]


def test_latest_split(synthetic_corpus):
    """The recent-window citer lands in ``latest``, not landmarks."""
    _landmark, latest = relations()
    assert [entry["node"]["id"] for entry in latest] == ["CorpusId:3"]


def test_authors_formatted(synthetic_corpus):
    """Multi-author papers format as a comma-joined display string."""
    landmark, _ = relations()
    by_id = {entry["node"]["id"]: entry["node"] for entry in landmark}
    assert by_id["CorpusId:2"]["authors"] == "Devlin, Chang"


def test_emitted_node_satisfies_model(synthetic_corpus):
    """A corpus citer's dict is a valid graph ``Node`` (extra keys forbidden)."""
    landmark, _ = relations()
    node = Node(**landmark[0]["node"], rels=["citation"], is_seed=False)
    assert node.id == "CorpusId:2"
    assert node.arxiv_id == "1810.04805"
    assert node.url == "https://arxiv.org/abs/1810.04805"


def test_non_arxiv_citer_url_uses_corpusid(synthetic_corpus):
    """A citer without an arXiv id gets a CorpusID-based S2 URL."""
    _landmark, latest = relations()
    node = latest[0]["node"]  # the recent paper has no external ids
    assert node["url"] == "https://www.semanticscholar.org/paper/CorpusID:3"
    assert node["arxiv_id"] is None


def test_citers_are_deduped_across_export_batches(synthetic_corpus):
    """S2 re-ships edges across overlapping export batches, so a citer must still
    appear ONCE. Without this the limit counts rows rather than papers and halves
    the relation — DQN's budget of 63 bought ~32 real landmarks."""
    landmark, _latest = relations()
    ids = [entry["node"]["id"] for entry in landmark]
    assert ids == ["CorpusId:2", "CorpusId:4"]  # each once, despite the second batch
    assert len(ids) == len(set(ids))


def test_a_limit_counts_papers_not_duplicate_rows(synthetic_corpus, monkeypatch):
    """The bug this guards: `LIMIT 1` over un-deduped rows could return one row
    that's a *second copy* of a citer — spending the budget on nothing."""
    monkeypatch.setattr(source, "UNBOUNDED_LANDMARK_CAP", 1)
    landmark, _latest = relations()
    assert [entry["node"]["id"] for entry in landmark] == ["CorpusId:2"]  # the most-cited


def test_influential_is_or_ed_across_duplicate_edges(synthetic_corpus):
    """The batches disagree: BERT's edge is influential in the first and not in the
    second. The flag is a claim that *some* record marks it influential, so OR."""
    landmark, _latest = relations()
    by_id = {entry["node"]["id"]: entry for entry in landmark}
    assert by_id["CorpusId:2"]["influential"] is True   # True in batch 1, False in batch 2
    assert by_id["CorpusId:4"]["influential"] is False  # False in both
