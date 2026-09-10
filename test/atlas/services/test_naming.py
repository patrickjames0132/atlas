"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Resolving a paper's informal name: the gate that decides whether a model call
happens at all, the model-proposes / provider-verifies order, and the day-cache
that keeps a nickname costing one call rather than one per keystroke.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.services.search import naming


class TestTheGate:
    """`has_exact_title_match` — what decides whether the model runs."""

    def test_an_exact_title_match_suppresses_the_resolve(self):
        assert naming.has_exact_title_match(
            [{"title": "Attention Is All You Need"}], "attention is all you need"
        )

    def test_matching_is_case_and_whitespace_insensitive(self):
        assert naming.has_exact_title_match([{"title": "  DQN  "}], "dqn")

    def test_a_CONTAINS_match_does_not_suppress_it(self):
        """The bug in the first cut, pinned. Typing "dqn" returns a page of
        DQN-titled papers while the paper actually called DQN is absent, so a
        contains-test reported success on a list without the answer in it."""
        assert not naming.has_exact_title_match(
            [
                {"title": "Deep Exploration via Bootstrapped DQN"},
                {"title": "Averaged-DQN: Variance Reduction and Stabilization"},
            ],
            "dqn",
        )

    def test_an_empty_query_suppresses_it(self):
        # Nothing typed, nothing to resolve, and no call worth making.
        assert naming.has_exact_title_match([], "")

    def test_a_missing_title_is_not_a_match(self):
        assert not naming.has_exact_title_match([{"citation_count": 5}], "dqn")


class TestResolving:
    """`paper_by_name` — model proposes, provider verifies, cache remembers."""

    def test_the_provider_verifies_what_the_model_proposed(self, monkeypatch):
        """The order matters. A model asked for a title will usually produce
        one, so without the verification a half-remembered nickname would put
        an INVENTED paper at the top of the reader's list — worse than showing
        them nothing."""
        proposed: list[str] = []

        def fake_match(title):
            proposed.append(title)
            return {"id": "S9", "title": title, "citation_count": 13985}

        monkeypatch.setattr(naming.s2, "match_title", fake_match)
        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name",
            lambda name: "Playing Atari with Deep Reinforcement Learning",
        )
        node = naming.paper_by_name("dqn")
        assert node is not None
        assert node["title"] == "Playing Atari with Deep Reinforcement Learning"
        assert proposed == ["Playing Atari with Deep Reinforcement Learning"]

    def test_a_title_no_paper_matches_resolves_to_nothing(self, monkeypatch):
        """The model was confident and wrong. The reader gets their ordinary
        results rather than a paper that doesn't exist."""
        monkeypatch.setattr(naming.s2, "match_title", lambda title: None)
        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name",
            lambda name: "A Paper That Does Not Exist",
        )
        assert naming.paper_by_name("nonsense") is None

    def test_an_unrecognised_name_never_reaches_the_provider(self, monkeypatch):
        monkeypatch.setattr(
            naming.s2, "match_title",
            lambda title: pytest.fail("nothing to verify when the model declined"),
        )
        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name", lambda name: None
        )
        assert naming.paper_by_name("transformers") is None

    def test_a_hit_is_cached_so_a_nickname_costs_one_model_call(self, monkeypatch):
        calls: list[str] = []

        def once(name):
            calls.append(name)
            return "Playing Atari with Deep Reinforcement Learning"

        monkeypatch.setattr(naming.s2, "match_title", lambda title: {"id": "S9", "title": title})
        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name", once
        )
        first = naming.paper_by_name("dqn")
        second = naming.paper_by_name("DQN")  # same name, different case
        assert first == second
        assert calls == ["dqn"]

    def test_a_MISS_is_cached_too(self, monkeypatch):
        """The important half. "transformers" is not a paper, and asking again
        would not change that — without caching the miss, exactly the queries
        that can never resolve would bill a model call every time."""
        calls: list[str] = []

        def declining(name):
            calls.append(name)
            return None

        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name", declining
        )
        assert naming.paper_by_name("transformers") is None
        assert naming.paper_by_name("transformers") is None
        assert calls == ["transformers"]

    def test_a_provider_failure_is_NOT_cached(self, monkeypatch):
        """The title may well be right and the provider merely unreachable, so
        a retry later deserves a real attempt rather than a day of silence."""
        calls: list[str] = []

        def naming_model(name):
            calls.append(name)
            return "Playing Atari with Deep Reinforcement Learning"

        def boom(title):
            raise RuntimeError("429")

        monkeypatch.setattr(naming.s2, "match_title", boom)
        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name", naming_model
        )
        assert naming.paper_by_name("dqn") is None
        assert naming.paper_by_name("dqn") is None
        assert len(calls) == 2  # tried again, rather than trusting a cached failure

    def test_a_blank_name_resolves_to_nothing_without_a_call(self, monkeypatch):
        monkeypatch.setattr(
            "atlas.agents.orchestrators.summarizer.title_for_paper_name",
            lambda name: pytest.fail("nothing to resolve"),
        )
        assert naming.paper_by_name("   ") is None
