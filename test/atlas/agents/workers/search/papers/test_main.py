"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The paper scout's two lookup channels and the numbering that joins them: a
lexical `search`, a semantic `more_like` that indexes into what the first one
found, and the budget both spend from.

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
