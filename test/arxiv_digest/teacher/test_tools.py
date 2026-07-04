"""The agentic tool runners (teacher/tools.py): budgets, visited-sets, and the
shapes of the trace/discovery payloads the frontend consumes.

Runners take the tool_use block's ``input`` via ``getattr``, so a plain
SimpleNamespace stands in for the SDK block. S2 / ar5iv / the library are
monkeypatched at the tools module's own imports — no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from arxiv_digest.teacher import tools


def block(**tool_input) -> SimpleNamespace:
    """A stand-in tool_use block carrying ``input``."""
    return SimpleNamespace(input=tool_input)


def node(i: int, **extra) -> dict:
    """A numbered node like _number_nodes produces."""
    return {"id": f"p{i}", "idx": i, "title": f"Paper {i}", "year": 2000 + i,
            "abstract": f"Abstract {i}", "tldr": f"TLDR {i}", **extra}


# --- _node_by_idx --------------------------------------------------------------

@pytest.mark.parametrize("idx", [None, "1", 1.0, True, 99])
def test_node_by_idx_rejects_non_indices(idx):
    """Bools, floats, strings, and out-of-range ints resolve to None, never raise."""
    assert tools._node_by_idx([node(1)], idx) is None


def test_node_by_idx_finds_by_idx_key():
    numbered = [node(1), node(2)]
    assert tools._node_by_idx(numbered, 2)["id"] == "p2"


# --- read_paper -----------------------------------------------------------------

def test_read_invalid_index():
    text, trace, node_id = tools._run_read(block(index=99), [node(1)], {"summary": 5, "full": 5}, {})
    assert "No paper at index 99" in text
    assert trace == {"action": "read", "ok": False, "index": 99, "title": None, "detail": "summary"}
    assert node_id is None


def test_read_decrements_budget_and_caches():
    budgets = {"summary": 2, "full": 2}
    cache: dict = {}
    numbered = [node(1)]
    text, trace, node_id = tools._run_read(block(index=1, detail="summary"), numbered, budgets, cache)
    assert "TLDR 1" in text and "Abstract 1" in text
    assert trace["ok"] and node_id == "p1"
    assert budgets["summary"] == 1
    # A repeat read serves from cache without spending budget.
    tools._run_read(block(index=1, detail="summary"), numbered, budgets, cache)
    assert budgets["summary"] == 1


def test_read_full_downgrades_to_summary_when_spent():
    budgets = {"summary": 5, "full": 0}
    text, trace, _ = tools._run_read(block(index=1, detail="full"), [node(1)], budgets, {})
    assert trace["detail"] == "summary"
    assert budgets["summary"] == 4


def test_read_budget_exhausted_still_names_the_paper():
    budgets = {"summary": 0, "full": 0}
    text, trace, node_id = tools._run_read(block(index=1), [node(1)], budgets, {})
    assert "budget exhausted" in text.lower()
    assert trace["ok"] is False
    assert node_id == "p1"  # still cited — the agent tried to ground on it


# --- expand_node ----------------------------------------------------------------

@pytest.fixture()
def fake_neighbors(monkeypatch):
    """Patch the (cached) S2 hop with canned neighbors; returns the setter."""
    def install(hits):
        monkeypatch.setattr(tools, "_s2_neighbors", lambda pid, rel: hits)
    return install


def test_expand_invalid_relation():
    text, trace, disc = tools._run_expand(block(index=1, relation="nonsense"), [node(1)], set(), set(), {"left": 5})
    assert "Invalid expand_node" in text
    assert trace["ok"] is False and disc is None


def test_expand_discovery_shape_and_edge_direction(fake_neighbors):
    fake_neighbors([
        {"node": {"id": "new1", "title": "New One", "year": 2020}, "influential": True},
    ])
    numbered = [node(1)]
    known = {"p1"}
    hops = {"left": 2}
    text, trace, disc = tools._run_expand(
        block(index=1, relation="references"), numbered, known, set(), hops)
    assert hops["left"] == 1
    assert trace == {"action": "expand", "ok": True, "index": 1, "title": "Paper 1",
                     "relation": "references", "found": 1}
    # reference edge points seed -> ancestor; discovered node is flagged + numbered.
    assert disc["edges"] == [{"source": "p1", "target": "new1", "type": "reference", "influential": True}]
    (d,) = disc["nodes"]
    assert d["discovered"] is True and d["rels"] == ["reference"] and d["idx"] == 2
    assert numbered[-1]["id"] == "new1"  # appended in place for next-turn reads
    assert "new1" in known


def test_expand_citation_edge_points_at_expanded_paper(fake_neighbors):
    fake_neighbors([{"node": {"id": "citer", "title": "Citer", "year": 2024}, "influential": False}])
    _, _, disc = tools._run_expand(
        block(index=1, relation="citations"), [node(1)], {"p1"}, set(), {"left": 1})
    assert disc["edges"][0] == {"source": "citer", "target": "p1", "type": "citation", "influential": False}


def test_expand_known_node_adds_edge_but_not_node(fake_neighbors):
    """A neighbor already on the graph contributes its edge, no duplicate node."""
    fake_neighbors([{"node": {"id": "p2", "title": "Paper 2"}, "influential": False}])
    numbered = [node(1), node(2)]
    text, trace, disc = tools._run_expand(
        block(index=1, relation="references"), numbered, {"p1", "p2"}, set(), {"left": 1})
    assert trace["found"] == 0
    assert disc["nodes"] == [] and len(disc["edges"]) == 1
    assert "already on the graph" in text


def test_expand_visited_set_kills_repeat(fake_neighbors):
    fake_neighbors([{"node": {"id": "new1", "title": "N"}, "influential": False}])
    numbered, known, seen, hops = [node(1)], {"p1"}, set(), {"left": 5}
    tools._run_expand(block(index=1, relation="references"), numbered, known, seen, hops)
    text, trace, disc = tools._run_expand(block(index=1, relation="references"), numbered, known, seen, hops)
    assert "Already expanded" in text and disc is None
    assert hops["left"] == 4  # the repeat spent no budget


def test_expand_budget_exhausted():
    text, trace, disc = tools._run_expand(
        block(index=1, relation="references"), [node(1)], {"p1"}, set(), {"left": 0})
    assert "budget exhausted" in text.lower() and disc is None


def test_expand_s2_failure_reported_not_raised(monkeypatch):
    from arxiv_digest.integrations import semantic_scholar as s2

    def boom(pid, rel):
        raise s2.S2Error("429 city")
    monkeypatch.setattr(tools, "_s2_neighbors", boom)
    text, trace, disc = tools._run_expand(
        block(index=1, relation="references"), [node(1)], {"p1"}, set(), {"left": 1})
    assert "Couldn't expand" in text and disc is None and trace["ok"] is False


# --- search_papers ----------------------------------------------------------------

def test_search_empty_query():
    text, trace, disc = tools._run_search(block(query="  "), [node(1)], {"p1"}, set(), {"left": 3})
    assert "Invalid" in text and disc is None


def test_search_discovery_has_search_rel_and_no_edges(monkeypatch):
    monkeypatch.setattr(tools, "_s2_search",
                        lambda q, yf, yt: [{"node": {"id": "hit1", "title": "Hit", "year": 2026}}])
    numbered = [node(1)]
    searches = {"left": 3}
    text, trace, disc = tools._run_search(
        block(query="latest transformers", year_from=2026), numbered, {"p1"}, set(), searches)
    assert searches["left"] == 2
    assert disc["edges"] == []  # topical hits float — no verified link
    (d,) = disc["nodes"]
    assert d["rels"] == ["search"] and d["discovered"] is True
    assert trace["year_from"] == 2026 and trace["found"] == 1
    assert "(since 2026)" in text


def test_search_repeat_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(tools, "_s2_search", lambda q, yf, yt: [])
    seen: set = set()
    searches = {"left": 3}
    tools._run_search(block(query="BERT models"), [node(1)], {"p1"}, seen, searches)
    text, _, _ = tools._run_search(block(query="bert MODELS"), [node(1)], {"p1"}, seen, searches)
    assert "Already searched" in text
    assert searches["left"] == 2


# --- search_sources ----------------------------------------------------------------

def test_search_sources_user_scope_overrides_agent_choice(monkeypatch):
    calls = {}

    def fake_search(query, source_ids=None):
        calls["source_ids"] = source_ids
        return [{"source_id": "s1", "source_title": "Book", "page": 3, "text": "hit"}]
    monkeypatch.setattr(tools.sources, "search", fake_search)

    # The agent asked for source "sneaky", but the user pinned scope to s1/s2.
    text, trace = tools._run_search_sources(
        block(query="adam", source_id="sneaky"), {"left": 5}, scope=["s1", "s2"])
    assert calls["source_ids"] == ["s1", "s2"]
    assert trace["found"] == 1 and "Book" in text


def test_search_sources_agent_choice_when_unscoped(monkeypatch):
    calls = {}

    def fake_search(query, source_ids=None):
        calls["ids"] = source_ids
        return []
    monkeypatch.setattr(tools.sources, "search", fake_search)
    tools._run_search_sources(block(query="q", source_id="s9"), {"left": 5}, scope=None)
    assert calls["ids"] == ["s9"]


def test_search_sources_budget_and_failure(monkeypatch):
    text, trace = tools._run_search_sources(block(query="q"), {"left": 0})
    assert "budget exhausted" in text.lower() and trace["ok"] is False

    def boom(query, source_ids=None):
        raise RuntimeError("db locked")
    monkeypatch.setattr(tools.sources, "search", boom)
    text, trace = tools._run_search_sources(block(query="q"), {"left": 1})
    assert "Couldn't search your sources" in text and trace["ok"] is False


# --- show_figure ----------------------------------------------------------------

@pytest.fixture()
def fake_figures(monkeypatch):
    def install(figs):
        monkeypatch.setattr(tools.figures_mod, "get_figures",
                            lambda arxiv_id: {"available": True, "figures": figs})
    return install


def test_show_figure_happy_path_proxies_image_and_assigns_slot(fake_figures):
    fake_figures([{"image": "https://ar5iv.labs.arxiv.org/x.png", "caption": "The architecture"},
                  {"image": "https://ar5iv.labs.arxiv.org/y.png", "caption": "Results"}])
    numbered = [node(1, arxiv_id="1706.03762")]
    budget = {"left": 3}
    shown: dict = {}
    text, trace, fig = tools._run_show_figure(block(index=1, figure=1), numbered, shown, budget)
    assert budget["left"] == 2 and trace["ok"] is True
    assert fig["image"].startswith("/api/figure_proxy?src=")
    assert "ar5iv" in fig["image"] and fig["caption"] == "The architecture"
    assert fig["slot"] == 1
    # The result teaches the model where to put the inline marker.
    assert "Attached Figure 1" in text and "<<FIG 1>>" in text
    # A second attachment gets the next slot.
    _, _, fig2 = tools._run_show_figure(block(index=1, figure=2), numbered, shown, budget)
    assert fig2["slot"] == 2


def test_show_figure_repeat_is_noop_and_restates_marker(fake_figures):
    fake_figures([{"image": "https://ar5iv.labs.arxiv.org/x.png", "caption": "c"}])
    numbered = [node(1, arxiv_id="1706.03762")]
    shown: dict = {}
    budget = {"left": 3}
    tools._run_show_figure(block(index=1, figure=1), numbered, shown, budget)
    text, trace, fig = tools._run_show_figure(block(index=1, figure=1), numbered, shown, budget)
    assert "already shown" in text and fig is None
    assert "<<FIG 1>>" in text  # the original marker, so the model can still place it
    assert budget["left"] == 2  # repeat spends nothing


def test_show_figure_out_of_range_and_no_arxiv(fake_figures):
    fake_figures([{"image": "https://ar5iv.labs.arxiv.org/x.png", "caption": "c"}])
    numbered = [node(1, arxiv_id="1706.03762"), node(2)]  # node 2: no arxiv_id
    text, _, fig = tools._run_show_figure(block(index=1, figure=5), numbered, {}, {"left": 3})
    assert "only 1 figure(s)" in text and fig is None
    text, _, fig = tools._run_show_figure(block(index=2, figure=1), numbered, {}, {"left": 3})
    assert "no arXiv figures" in text and fig is None


@pytest.mark.parametrize("figure", [0, -1, True, "1", None])
def test_show_figure_invalid_figure_number(figure):
    text, trace, fig = tools._run_show_figure(
        block(index=1, figure=figure), [node(1, arxiv_id="x")], {}, {"left": 3})
    assert "Invalid show_figure" in text and fig is None
