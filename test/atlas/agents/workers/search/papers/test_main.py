"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The paper scout's three lookup channels and the numbering that joins them: a
lexical `search`, a `match_title` that resolves one named paper, a semantic
`more_like` that indexes into what the others found, and the budget all three
spend from — plus the caller filters that bind every one of them.

The tools are exercised as plain functions with a stub context — they touch
nothing but `ctx.deps`, and going through a scripted agent would test
PydanticAI's tool dispatch rather than the scout's own logic (the researcher's
suite already covers the seam above).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlas.agents.workers.search.papers import main as scout


def make_deps(**overrides) -> scout.ScoutDeps:
    """A scouting run's state, with generous budgets unless overridden.

    Args:
        **overrides: ScoutDeps fields to replace.

    Returns:
        The deps object.
    """
    fields = dict(provider="s2", known_ids=set(), searches_left=4, limit=8)
    fields.update(overrides)
    return scout.ScoutDeps(**fields)


def hit(node_id: str, title: str, year: int = 2024) -> dict:
    """One provider entry in the shape traversal hands back.

    Args:
        node_id: The paper's provider id.
        title: The paper's title.
        year: The publication year.

    Returns:
        A `{"node": {...}}` entry.
    """
    return {"node": {"id": node_id, "title": title, "year": year}}


def ctx(deps: scout.ScoutDeps) -> SimpleNamespace:
    """A stand-in RunContext — the tools read `ctx.deps` and nothing else.

    Args:
        deps: The run state to expose.

    Returns:
        The stub context.
    """
    return SimpleNamespace(deps=deps)


def test_results_are_numbered_so_the_model_can_point_at_one(monkeypatch):
    """The handle `more_like` needs. Ids are the obvious alternative and the
    wrong one — a model handed ids starts inventing them — so the scout numbers
    its own finds instead."""
    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [
        hit("p1", "Deep Residual Learning"), hit("p2", "Batch Normalization")
    ])
    deps = make_deps()
    out = scout.search(ctx(deps), "residual networks")
    assert "1. (2024) Deep Residual Learning" in out
    assert "2. (2024) Batch Normalization" in out


def test_the_numbering_continues_across_lookups(monkeypatch):
    """It indexes `found`, which only grows — so a number stays pointing at the
    same paper for the whole run, whichever channel turned it up."""
    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [hit("p1", "First")])
    monkeypatch.setattr(
        scout.traversal, "neighbors", lambda *args, **kwargs: [hit("p2", "Second")]
    )
    deps = make_deps()
    scout.search(ctx(deps), "anything")
    out = scout.more_like(ctx(deps), 1)
    assert "2. (2024) Second" in out
    assert [node["id"] for node in deps.found] == ["p1", "p2"]


def test_more_like_hops_from_the_chosen_paper(monkeypatch):
    """The semantic channel takes a paper id, not a query — which is exactly
    why it can't start a search, and why the scout has to find something
    first."""
    seen = {}

    def fake_neighbors(paper_id, relation, limit, provider="s2"):
        seen.update(paper_id=paper_id, relation=relation, provider=provider)
        return []

    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [
        hit("p1", "First"), hit("p2", "Second")
    ])
    monkeypatch.setattr(scout.traversal, "neighbors", fake_neighbors)
    deps = make_deps(provider="openalex")
    scout.search(ctx(deps), "anything")
    scout.more_like(ctx(deps), 2)
    # 'similar' under OpenAlex is related_works rather than SPECTER2 — same
    # tool, materially different data, resolved down in traversal.
    assert seen == {"paper_id": "p2", "relation": "similar", "provider": "openalex"}


@pytest.mark.parametrize(
    ("provider", "label"), [("s2", "similar to"), ("openalex", "related to")]
)
def test_the_hop_is_traced_in_the_providers_own_word(monkeypatch, provider, label):
    """The two aren't the same relation and the chip shouldn't claim they are:
    S2's is SPECTER2 embedding neighbours, OpenAlex's is `related_works`
    concept and citation overlap. Borrowing each provider's own word keeps the
    trace honest about how strong the claim behind it is.

    This is the only reader-facing string the semantic channel produces — it
    shares the researcher's search trace rather than getting a chip of its own,
    because how the agent found a paper is not the reader's problem."""
    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [hit("p1", "DQN")])
    monkeypatch.setattr(scout.traversal, "neighbors", lambda *args, **kwargs: [])
    deps = make_deps(provider=provider)
    scout.search(ctx(deps), "atari")
    scout.more_like(ctx(deps), 1)
    # No inner quotes — the trace chip adds curly ones of its own.
    assert deps.queries == ["atari", f"{label}: DQN"]


def test_a_number_out_of_range_comes_back_as_text(monkeypatch):
    """The worker's half of the researcher's rule: a bad index is information
    the model steers by, never a raise — and it costs no budget."""
    deps = make_deps()
    assert "No result 3" in scout.more_like(ctx(deps), 3)
    assert deps.searches_left == 4


def test_both_channels_spend_the_same_budget(monkeypatch):
    """One pool, deliberately: the scout's value is two or three aimed lookups,
    and a separate allowance for the second channel would just raise the
    ceiling on a run the reader is waiting for."""
    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [hit("p1", "First")])
    monkeypatch.setattr(scout.traversal, "neighbors", lambda *args, **kwargs: [])
    deps = make_deps(searches_left=2)
    scout.search(ctx(deps), "anything")
    scout.more_like(ctx(deps), 1)
    assert deps.searches_left == 0
    assert "budget spent" in scout.more_like(ctx(deps), 1).lower()


def test_the_similar_hop_reports_failure_as_text(monkeypatch):
    """A broken lookup costs the answer its papers, never the answer."""
    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [hit("p1", "First")])

    def explode(*args, **kwargs):
        raise scout.s2.S2Error("upstream down")

    monkeypatch.setattr(scout.traversal, "neighbors", explode)
    deps = make_deps()
    scout.search(ctx(deps), "anything")
    assert "Couldn't find papers similar to" in scout.more_like(ctx(deps), 1)


@pytest.mark.parametrize("channel", ["search", "more_like"])
def test_neither_channel_reports_a_paper_the_caller_already_has(monkeypatch, channel):
    """Deduping is against the CALLER's world, so the scout's summary can't
    claim to have turned up a paper the reader is already looking at."""
    monkeypatch.setattr(scout.traversal, "search", lambda *args, **kwargs: [hit("seed", "Known")])
    monkeypatch.setattr(scout.traversal, "neighbors", lambda *args, **kwargs: [hit("seed", "Known")])
    deps = make_deps(known_ids={"seed"})
    if channel == "search":
        assert "returned nothing new" in scout.search(ctx(deps), "anything")
    else:
        deps.found.append({"id": "other", "title": "Other", "year": 2020})
        assert "Nothing new similar to" in scout.more_like(ctx(deps), 1)
    assert deps.found == [] or [node["id"] for node in deps.found] == ["other"]


# --- binding filters (v7.6.0) ----------------------------------------------------


def test_a_caller_filter_reaches_the_provider_even_when_the_model_asks_for_nothing(
    monkeypatch,
):
    """The whole point of putting filters in deps: the model passes no year at
    all, and the search is still restricted. Nothing it can write gets around
    a value it never sees."""
    seen = {}
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: (
            seen.update(year_from=year_from, year_to=year_to, fields=fields) or []
        ),
    )
    deps = make_deps(year_from=2020, year_to=2024, fields=["Computer Science"])
    scout.search(ctx(deps), "quantum error correction")
    assert seen == {"year_from": 2020, "year_to": 2024, "fields": ["Computer Science"]}


def test_no_filters_means_a_genuinely_unrestricted_search(monkeypatch):
    """The default has to stay free-form — an unfiltered run must search exactly
    as it did before filters existed, not under some invented default window."""
    seen = {}
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: (
            seen.update(year_from=year_from, year_to=year_to, fields=fields) or []
        ),
    )
    scout.search(ctx(make_deps()), "quantum error correction")
    assert seen == {"year_from": None, "year_to": None, "fields": []}


@pytest.mark.parametrize(
    "caller_from,tool_from,expected",
    [
        (2020, 2018, 2020),  # the model may NOT widen out of the caller's floor
        (2020, 2022, 2022),  # but it may narrow inside it
        (None, 2018, 2018),  # with no caller floor its own tactic stands
        (2020, None, 2020),  # and with no tactic the caller's floor still binds
    ],
)
def test_the_narrower_year_floor_wins(monkeypatch, caller_from, tool_from, expected):
    seen = {}
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: (
            seen.update(year_from=year_from) or []
        ),
    )
    scout.search(ctx(make_deps(year_from=caller_from)), "topic", year_from=tool_from)
    assert seen["year_from"] == expected


def test_a_field_filter_switches_off_the_paths_that_cannot_honour_it(monkeypatch):
    """The cache stores no fields of study and a title match can't express one,
    so while a field filter is set both are OFF rather than quietly ignoring it.
    A filter with a hole in it is worse than no filter — the UI promises it."""
    monkeypatch.setattr(
        scout, "cached_nodes",
        lambda *args, **kwargs: pytest.fail("the cache cannot honour a field filter"),
    )
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: [],
    )
    deps = make_deps(fields=["Computer Science"])
    scout.search(ctx(deps), "topic")  # would fail inside cached_nodes if consulted

    out = scout.match_title(ctx(deps), "Attention Is All You Need")
    assert "unavailable while a field filter is set" in out
    assert deps.searches_left == 3  # the refused lookup cost nothing extra


# --- match_title (v7.6.0) --------------------------------------------------------


def test_match_title_numbers_the_paper_like_any_other_find(monkeypatch):
    monkeypatch.setattr(
        scout.s2, "match_title",
        lambda title: {"id": "s2atari", "title": "Playing Atari", "year": 2013},
    )
    deps = make_deps()
    out = scout.match_title(ctx(deps), "Playing Atari with Deep Reinforcement Learning")
    assert "1. (2013) Playing Atari" in out
    assert [node["id"] for node in deps.found] == ["s2atari"]
    assert deps.searches_left == 3  # costs a search, like every other lookup


def test_match_title_outside_the_year_window_is_refused_not_smuggled_in(monkeypatch):
    """Live search used to let a recalled title outrank the filters, on the
    reading that an exact resolution is 'the paper the query means'. Once the
    window is a promise the reader made, a match outside it is a broken promise."""
    monkeypatch.setattr(
        scout.s2, "match_title",
        lambda title: {"id": "s2atari", "title": "Playing Atari", "year": 2013},
    )
    deps = make_deps(year_from=2020)
    out = scout.match_title(ctx(deps), "Playing Atari")
    assert "outside the requested years" in out
    assert deps.found == []


def test_a_title_nothing_matches_says_so_rather_than_inventing(monkeypatch):
    monkeypatch.setattr(scout.s2, "match_title", lambda title: None)
    deps = make_deps()
    assert "No paper matches" in scout.match_title(ctx(deps), "A Paper That Never Was")
    assert deps.found == []


def test_match_title_routes_through_openalex_under_openalex(monkeypatch):
    monkeypatch.setattr(scout.openalex, "resolve_work", lambda arxiv_id, title: {"raw": 1})
    monkeypatch.setattr(
        scout.openalex, "node", lambda work: {"id": "oaW1", "title": "Resolved", "year": 2021}
    )
    monkeypatch.setattr(
        scout.s2, "match_title", lambda title: pytest.fail("S2 must not be used under OpenAlex")
    )
    deps = make_deps(provider="openalex")
    scout.match_title(ctx(deps), "Resolved")
    assert [node["id"] for node in deps.found] == ["oaW1"]


# --- cache-first (v7.6.0) --------------------------------------------------------


def test_a_dead_provider_falls_back_to_papers_already_cached(monkeypatch):
    """Cache-only mode: the search still answers from graphs seen before, which
    is the whole reason the cache lookup lives inside the tool rather than
    being a tool of its own the model could skip."""
    monkeypatch.setattr(
        scout, "cached_nodes",
        lambda *args, **kwargs: [{"id": "cachedA", "title": "A Cached Paper", "year": 2019}],
    )
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda *args, **kwargs: (_ for _ in ()).throw(scout.s2.S2Error("rate limited")),
    )
    deps = make_deps()
    out = scout.search(ctx(deps), "cached")
    assert "unavailable" in out and "A Cached Paper" in out
    assert [node["id"] for node in deps.found] == ["cachedA"]


def test_a_dead_provider_with_an_empty_cache_still_reports_the_failure(monkeypatch):
    monkeypatch.setattr(scout, "cached_nodes", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda *args, **kwargs: (_ for _ in ()).throw(scout.s2.S2Error("rate limited")),
    )
    out = scout.search(ctx(make_deps()), "nothing")
    assert "Couldn't search" in out and "rate limited" in out


def test_a_broken_cache_read_cannot_break_a_working_search(monkeypatch):
    monkeypatch.setattr(
        scout, "cached_nodes",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cache corrupt")),
    )
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: [
            hit("s2live", "A Live Paper")
        ],
    )
    deps = make_deps()
    out = scout.search(ctx(deps), "live")
    assert "A Live Paper" in out
    assert [node["id"] for node in deps.found] == ["s2live"]


def test_live_hits_lead_and_the_cache_only_adds_what_the_search_missed(monkeypatch):
    monkeypatch.setattr(
        scout, "cached_nodes",
        lambda *args, **kwargs: [
            {"id": "s2live", "title": "A Live Paper", "year": 2024},  # already live
            {"id": "cachedB", "title": "Only In Cache", "year": 2019},
        ],
    )
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: [
            hit("s2live", "A Live Paper")
        ],
    )
    deps = make_deps()
    scout.search(ctx(deps), "papers")
    assert [node["id"] for node in deps.found] == ["s2live", "cachedB"]


# --- the filter briefing ---------------------------------------------------------


def test_the_briefing_is_empty_when_nothing_is_filtered():
    assert scout._filter_briefing(make_deps()) == ""


def test_the_briefing_states_the_filters_so_a_thin_result_is_reported_honestly():
    """Not enforcement — that's in the tools. This exists so the scout doesn't
    report 'nothing indexed after 2021' as a finding about the literature when
    it was a finding about the reader's own filter."""
    briefing = scout._filter_briefing(make_deps(year_from=2020, fields=["Computer Science"]))
    assert "2020" in briefing and "Computer Science" in briefing
    assert "cannot search outside it" in briefing


# --- streaming progress (v7.6.0) -------------------------------------------------


def test_a_lookup_is_announced_when_issued_and_counted_when_it_lands(monkeypatch):
    """Two calls per lookup, and both matter. The first is what puts a chip on
    screen while the provider call is still in flight; the second carries the
    count, without which the chip renders "nothing new" — which made every
    lookup look like a miss, including the one that found everything."""
    seen: list[tuple[str, list | None]] = []
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: [
            hit("s2a", "One"), hit("s2b", "Two")
        ],
    )
    monkeypatch.setattr(scout, "cached_nodes", lambda *args, **kwargs: [])
    deps = make_deps(on_lookup=lambda label, found: seen.append((label, found)))
    scout.search(ctx(deps), "deep q-network")
    assert [label for label, _ in seen] == ["deep q-network", "deep q-network"]
    assert seen[0][1] is None  # announced: issued, nothing to show yet
    # The papers themselves come back, not a count — that is what lets the
    # caller grow its list lookup by lookup instead of waiting for the run.
    assert [node["id"] for node in seen[1][1]] == ["s2a", "s2b"]


def test_a_repeat_lookup_reports_zero_rather_than_going_silent(monkeypatch):
    """Zero is a real answer, and a common one once the good query has already
    run — the reader should see the scout tried and found nothing new, not a
    chip stuck pending forever."""
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda query, limit, year_from, year_to, provider, fields=None: [hit("s2a", "One")],
    )
    monkeypatch.setattr(scout, "cached_nodes", lambda *args, **kwargs: [])
    seen: list[tuple[str, list | None]] = []
    deps = make_deps(known_ids={"s2a"}, on_lookup=lambda label, found: seen.append((label, found)))
    scout.search(ctx(deps), "already have it")
    assert seen[-1] == ("already have it", [])


def test_a_failed_lookup_still_reports_so_its_chip_resolves(monkeypatch):
    monkeypatch.setattr(scout, "cached_nodes", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        scout.traversal, "search",
        lambda *args, **kwargs: (_ for _ in ()).throw(scout.s2.S2Error("rate limited")),
    )
    seen: list[tuple[str, list | None]] = []
    deps = make_deps(on_lookup=lambda label, found: seen.append((label, found)))
    scout.search(ctx(deps), "doomed")
    assert seen == [("doomed", None), ("doomed", [])]


def test_a_title_match_and_a_semantic_hop_announce_themselves_too(monkeypatch):
    monkeypatch.setattr(
        scout.s2, "match_title",
        lambda title: {"id": "s2atari", "title": "Playing Atari", "year": 2013},
    )
    monkeypatch.setattr(
        scout.traversal, "neighbors",
        lambda node_id, relation, limit, provider: [hit("s2near", "A Neighbour")],
    )
    seen: list[tuple[str, list | None]] = []
    deps = make_deps(on_lookup=lambda label, found: seen.append((label, found)))
    scout.match_title(ctx(deps), "Playing Atari")
    scout.more_like(ctx(deps), 1)
    assert [(label, None if papers is None else [node["id"] for node in papers])
            for label, papers in seen] == [
        ("title: Playing Atari", None),
        ("title: Playing Atari", ["s2atari"]),
        ("similar to: Playing Atari", None),
        ("similar to: Playing Atari", ["s2near"]),
    ]
