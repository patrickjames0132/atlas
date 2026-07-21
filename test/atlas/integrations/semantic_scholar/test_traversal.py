"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Batch hydration and citation-graph traversal: get_papers/get_paper,
references, citations, recommendations.

client.request is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import datetime

import pytest

from atlas.integrations.semantic_scholar import client, nodes, traversal


def _iso(days_ago: int) -> str:
    """An ISO date ``days_ago`` before today — for placing a citer inside or
    outside the rolling 'latest' window without hardcoding a calendar date."""
    return (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()


def _relations(**kwargs):
    """``citation_relations`` for the test seed, defaulting the year bounds a
    real build passes (``openalex.landmark_max_year`` and today's year) — they
    only matter on the complete-pool branch, which sets them explicitly.

    Args:
        **kwargs: Any ``citation_relations`` keyword to pass or override.

    Returns:
        Whatever ``citation_relations`` returns — ``(landmark, latest)``.
    """
    today = datetime.date.today()
    kwargs.setdefault("max_landmark_year", today.year - 2)
    kwargs.setdefault("current_year", today.year)
    return traversal.citation_relations("p1", **kwargs)


def test_get_papers_chunks_batches_and_skips_nulls(monkeypatch):
    bodies = []

    def fake_request(url, method="GET", body=None, tries=4):
        bodies.append(body["ids"])
        # S2 aligns the response list to the input ids; null = unresolved.
        return [{"paperId": pid} if pid != "ARXIV:bad" else None for pid in body["ids"]]

    monkeypatch.setattr(client, "request", fake_request)
    ids = [f"id{index}" for index in range(501)] + ["", "ARXIV:bad"]  # falsy dropped, bad unresolved
    out = traversal.get_papers(ids)
    assert [len(body) for body in bodies] == [500, 2]  # chunked at the 500-id cap
    assert len(out) == 501 and "ARXIV:bad" not in out
    assert out["id0"]["id"] == "id0"


def test_get_papers_empty_input_no_request(monkeypatch):
    monkeypatch.setattr(client, "request", lambda *args, **kwargs: pytest.fail("should not be called"))
    assert traversal.get_papers(["", None]) == {}


def test_references_shape_and_influential(monkeypatch):
    def fake_request(url, **kw):
        assert "/references" in url
        return {
            "data": [
                {"citedPaper": {"paperId": "r1", "title": "Ref"}, "isInfluential": True},
                {"citedPaper": None},  # unresolved — skipped
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.references("p1", limit=10)
    assert out == [{"node": nodes.node({"paperId": "r1", "title": "Ref"}), "influential": True}]


def test_citations_uses_citing_paper_key(monkeypatch):
    monkeypatch.setattr(
        client,
        "request",
        lambda url, **kw: {"data": [{"citingPaper": {"paperId": "c1"}, "isInfluential": False}]},
    )
    (hit,) = traversal.citations("p1", limit=10)
    assert hit["node"]["id"] == "c1" and hit["influential"] is False


def test_citations_ranked_by_citation_count_not_s2_order(monkeypatch):
    """S2's default order skews toward the most recently published citing
    paper, not the most cited — so a small `limit` must keep the
    highest-citation-count hits (here within one year bucket), not whatever
    S2 lists first."""

    def fake_request(url, **kw):
        assert "limit=1000" in url  # over-fetches the ranking pool regardless of `limit`
        return {
            "data": [
                {"citingPaper": {"paperId": "recent", "citationCount": 0}},
                {"citingPaper": {"paperId": "famous", "citationCount": 5000}},
                {"citingPaper": {"paperId": "mid", "citationCount": 40}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=2)
    assert [hit["node"]["id"] for hit in out] == ["famous", "mid"]  # top 2 by citation count


def test_citation_relations_splits_latest_from_landmark(monkeypatch):
    """The seed-build view splits citers by publication date: recent ones (last
    ~12 months) are `latest`, shipped oldest-first (the reveal slider walks
    toward the present); older ones are `landmark`, most-cited first. The two
    partitions are disjoint."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}  # one page is the whole list here
        return {
            "data": [
                {"citingPaper": {"paperId": "fresh", "citationCount": 2, "publicationDate": _iso(40)}},
                {"citingPaper": {"paperId": "fresher", "citationCount": 1, "publicationDate": _iso(5)}},
                {"citingPaper": {"paperId": "old-giant", "citationCount": 5000, "publicationDate": _iso(2000)}},
                {"citingPaper": {"paperId": "old-mid", "citationCount": 40, "publicationDate": _iso(1500)}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = _relations()
    assert [hit["node"]["id"] for hit in landmark] == ["old-giant", "old-mid"]  # most-cited first
    assert [hit["node"]["id"] for hit in latest] == ["fresh", "fresher"]  # oldest-first


def test_citation_relations_dateless_citer_is_landmark_not_latest(monkeypatch):
    """A citer with neither a date nor a year can't be placed in the rolling
    window, so it competes as a historic landmark rather than being guessed into
    latest."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": "undated", "citationCount": 9999}},
                {"citingPaper": {"paperId": "recent", "citationCount": 1, "publicationDate": _iso(10)}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = _relations()
    assert [hit["node"]["id"] for hit in landmark] == ["undated"]
    assert [hit["node"]["id"] for hit in latest] == ["recent"]


def test_citation_relations_year_settles_a_dateless_citer_inside_the_window(monkeypatch):
    """A citer S2 gave no publicationDate but a year AFTER the cutoff's year is
    unambiguously in the window — it's months old, not a historic landmark.
    Misfiling those was what drew a vertical line at the graph's right edge."""
    next_year = datetime.date.today().year + 1

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {"data": [{"citingPaper": {"paperId": "dateless-but-current",
                                          "citationCount": 3, "year": next_year}}]}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = _relations()
    assert [hit["node"]["id"] for hit in latest] == ["dateless-but-current"]
    assert landmark == []


def test_citation_relations_cutoff_year_stays_a_landmark_when_dateless(monkeypatch):
    """The cutoff's OWN year is genuinely ambiguous without a month (January is
    outside the window, December inside), so it stays a landmark — the
    conservative read."""
    this_year = datetime.date.today().year

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {"data": [{"citingPaper": {"paperId": "ambiguous",
                                          "citationCount": 3, "year": this_year - 1}}]}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = _relations()
    assert [hit["node"]["id"] for hit in landmark] == ["ambiguous"]
    assert latest == []


def test_latest_orders_a_dateless_citer_where_the_timeline_draws_it(monkeypatch):
    """A year-only citer sorts as Jan 1 of its year — exactly where the timeline
    pins it (no month → the year's gridline) — so the reveal slider's order and
    the on-screen left-to-right order agree."""
    next_year = datetime.date.today().year + 1

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": "june", "citationCount": 1, "year": next_year,
                                 "publicationDate": f"{next_year}-06-01"}},
                {"citingPaper": {"paperId": "year-only", "citationCount": 1, "year": next_year}},
                {"citingPaper": {"paperId": "march", "citationCount": 1, "year": next_year,
                                 "publicationDate": f"{next_year}-03-01"}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    _, latest = _relations()
    # Oldest-first: the year-only citer sits at January, ahead of March and June.
    assert [hit["node"]["id"] for hit in latest] == ["year-only", "march", "june"]


def test_truncated_landmarks_trim_to_the_payload_guard(monkeypatch):
    """With no selector injected, the truncated fallback ships a most-cited
    prefix trimmed to the payload guard — never the whole pool. Latest has no
    per-relation cap (the rolling window bounds it structurally)."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": f"old{index}", "citationCount": 100 - index,
                                 "publicationDate": _iso(1000 + index)}}
                for index in range(5)
            ] + [
                {"citingPaper": {"paperId": f"new{index}", "citationCount": 1,
                                 "publicationDate": _iso(index + 1)}}
                for index in range(5)
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(traversal, "UNBOUNDED_LANDMARK_CAP", 2)
    landmark, latest = _relations()
    assert len(landmark) == 2 and len(latest) == 5


def test_citation_relations_ships_everything_under_the_guard(monkeypatch):
    """No per-relation config caps: the whole ranked pool ships for each
    relation (the payload guard is the only ceiling) — so the frontend slider
    can max out to the paper's full count."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": f"old{index}", "citationCount": 100 - index,
                                 "publicationDate": _iso(1000 + index)}}
                for index in range(6)
            ] + [
                {"citingPaper": {"paperId": f"new{index}", "citationCount": 1,
                                 "publicationDate": _iso(index + 1)}}
                for index in range(4)
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = _relations()
    assert len(landmark) == 6 and len(latest) == 4  # every citer, uncapped


def _landmark_pool(monkeypatch, years: list[int]) -> None:
    """Serve one page of older (landmark-era) citers, most-cited first by
    construction — ``years[index]`` is the year of the index-th most-cited citer.
    """

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": f"old{index}", "citationCount": 1000 - index,
                                 "year": year, "publicationDate": _iso(1000 + index)}}
                for index, year in enumerate(years)
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)


def test_citation_relations_landmark_select_picks_the_band(monkeypatch):
    """An injected selector chooses which ranked landmarks ship, and WINS over
    the flat payload guard. It picks by index, so it can skip — which is the
    point: a flat count could only ever keep a prefix."""
    _landmark_pool(monkeypatch, [2020] * 5)
    landmark, _ = _relations(landmark_select=lambda years: [0, 2, 4])
    assert [hit["node"]["id"] for hit in landmark] == ["old0", "old2", "old4"]


def test_citation_relations_landmark_select_reads_the_ranked_years(monkeypatch):
    """The selector sees the citer years in CITATION-RANK order, and its indices
    are read back against that same ranking — a mismatch would ship the wrong
    papers, not merely the wrong number of them."""
    _landmark_pool(monkeypatch, [2018, 2024, 2019, 2024])
    seen: dict[str, object] = {}

    def record(years):
        seen["years"] = list(years)
        return None

    _relations(landmark_select=record)
    assert seen["years"] == [2018, 2024, 2019, 2024]  # most-cited first, not sorted by year


def test_citation_relations_landmark_select_declining_keeps_the_flat_guard(monkeypatch):
    """A selector that returns None (the adaptive toggle off) leaves the flat
    payload guard in charge rather than shipping the whole pool."""
    _landmark_pool(monkeypatch, [2024] * 20)
    monkeypatch.setattr(traversal, "UNBOUNDED_LANDMARK_CAP", 4)
    landmark, _ = _relations(landmark_select=lambda years: None)
    assert len(landmark) == 4


def test_citation_relations_without_a_selector_is_unchanged(monkeypatch):
    """The default (no rule) keeps the flat-guard behavior — the expansion path
    and every pre-existing caller are untouched."""
    _landmark_pool(monkeypatch, [2024] * 20)
    monkeypatch.setattr(traversal, "UNBOUNDED_LANDMARK_CAP", 6)
    landmark, _ = _relations()
    assert len(landmark) == 6


def _complete_pool(monkeypatch, papers: list[dict]) -> None:
    """Serve the given citers as one page with NO continuation — a pool the
    pager finishes, i.e. the seed's complete citation history.
    """

    def fake_request(url, **kw):
        assert _offset_of(url) == 0, "a complete one-page pool should never page deeper"
        return {"data": [{"citingPaper": paper} for paper in papers]}

    monkeypatch.setattr(client, "request", fake_request)


def test_complete_pool_ships_the_corpus_shape(monkeypatch):
    """A pool the pager finished is the seed's whole history, so with a budget
    rule injected it ships the corpus shape: landmarks are a STOP-prefix of the
    all-time ranking (the rule's count), Latest is per-year bands from the
    band_start rule — not the truncated path's SKIP banding + rolling window."""
    this_year = datetime.date.today().year
    _complete_pool(monkeypatch, [
        {"paperId": "giant15", "citationCount": 5000, "year": 2015,
         "publicationDate": "2015-06-01"},
        {"paperId": "giant18", "citationCount": 4000, "year": 2018,
         "publicationDate": "2018-06-01"},
        {"paperId": "mid16", "citationCount": 300, "year": 2016,
         "publicationDate": "2016-06-01"},
        {"paperId": "recent_a", "citationCount": 50, "year": this_year - 1,
         "publicationDate": f"{this_year - 1}-06-01"},
        {"paperId": "recent_b", "citationCount": 5, "year": this_year,
         "publicationDate": f"{this_year}-01-15"},
    ])
    seen: dict[str, object] = {}

    def budget(citer_years):
        seen["years"] = list(citer_years)
        return 2

    landmark, latest = _relations(
        max_landmark_year=this_year - 2, current_year=this_year,
        landmark_budget=budget,
        band_start=lambda landmark_years, max_year: this_year - 1,
    )
    # The rule saw the whole landmark-era ranking, most-cited first.
    assert seen["years"] == [2015, 2018, 2016]
    # Its count trims a citation-ranked PREFIX — not a per-year band.
    assert [hit["node"]["id"] for hit in landmark] == ["giant15", "giant18"]
    # Latest: per-year bands from the band_start year, oldest-first for the
    # reveal slider — the rolling 12-month window doesn't apply (recent_a is
    # ~a year old and still banded).
    assert [hit["node"]["id"] for hit in latest] == ["recent_a", "recent_b"]


def test_complete_pool_budget_declining_keeps_the_flat_guard(monkeypatch):
    """On the corpus shape, a budget rule answering None (adaptive off) falls
    back to the flat payload guard — still a prefix of the ranking."""
    this_year = datetime.date.today().year
    _complete_pool(monkeypatch, [
        {"paperId": "giant", "citationCount": 5000, "year": 2015,
         "publicationDate": "2015-06-01"},
        {"paperId": "mid", "citationCount": 300, "year": 2016,
         "publicationDate": "2016-06-01"},
    ])
    monkeypatch.setattr(traversal, "UNBOUNDED_LANDMARK_CAP", 1)
    landmark, _ = _relations(
        max_landmark_year=this_year - 2, current_year=this_year,
        landmark_budget=lambda citer_years: None,
    )
    assert [hit["node"]["id"] for hit in landmark] == ["giant"]


def test_complete_pool_bands_cap_each_year_and_exclude_landmarks(monkeypatch):
    """The complete-pool Latest bands mirror the corpus: each band year ships
    its top ``nodes_per_band`` by citations, and a citer already shipped as a
    landmark stays a landmark rather than double-showing."""

    this_year = datetime.date.today().year
    band_year = this_year - 1
    _complete_pool(monkeypatch, [
        # A giant OLD enough to be landmark-era; the band_start reaches below
        # max_landmark_year, so its year is also band-range — it must not double-show.
        {"paperId": "giant", "citationCount": 5000, "year": this_year - 3,
         "publicationDate": f"{this_year - 3}-06-01"},
        {"paperId": "band_top", "citationCount": 90, "year": band_year,
         "publicationDate": f"{band_year}-03-01"},
        {"paperId": "band_mid", "citationCount": 80, "year": band_year,
         "publicationDate": f"{band_year}-04-01"},
        {"paperId": "band_dreg", "citationCount": 1, "year": band_year,
         "publicationDate": f"{band_year}-05-01"},
    ])
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 2)
    landmark, latest = _relations(
        max_landmark_year=this_year - 2, current_year=this_year,
        landmark_budget=lambda citer_years: 1,
        band_start=lambda landmark_years, max_year: this_year - 3,
    )
    assert [hit["node"]["id"] for hit in landmark] == ["giant"]
    # band_year ships its top 2 by citations; the giant's year band would hold
    # the giant, but it's already a landmark — excluded, not double-shown.
    assert [hit["node"]["id"] for hit in latest] == ["band_top", "band_mid"]


def test_truncated_pool_still_skips_never_prefixes(monkeypatch):
    """A pool the offset ceiling cut off is a recency sliver: even with a budget
    rule supplied, the SKIP selector picks the band and the budget is never
    consulted — the corpus shape needs a COMPLETE history."""
    calls: list[str] = []

    def fake_request(url, method="GET", body=None, **kw):
        offset = _offset_of(url)
        return {"data": [{"citingPaper": {"paperId": f"c{offset}", "citationCount": 100,
                                          "year": 2020, "publicationDate": _iso(2000)}}],
                "next": offset + 1000}  # always more — the ceiling ends the walk

    monkeypatch.setattr(client, "request", fake_request)

    def budget(citer_years):
        calls.append("budget")
        return 1

    def select(citer_years):
        calls.append("select")
        return [0]

    landmark, _ = _relations(landmark_select=select, landmark_budget=budget)
    assert calls == ["select"]  # the budget never ran
    assert [hit["node"]["id"] for hit in landmark] == ["c0"]


def test_a_short_page_with_a_next_pointer_keeps_paging(monkeypatch):
    """A page short of the request size mid-list (S2 skipped unresolvable
    papers) is NOT the end of the list — S2's ``next`` says the walk continues,
    and the pool only counts as complete when it ends without one."""
    this_year = datetime.date.today().year
    pages = {
        0: {"data": [{"citingPaper": {"paperId": "a", "citationCount": 10, "year": 2015,
                                      "publicationDate": "2015-06-01"}},
                     {"citingPaper": None}],  # unresolvable — skipped, page runs short
            "next": 1000},
        1000: {"data": [{"citingPaper": {"paperId": "b", "citationCount": 5000, "year": 2016,
                                         "publicationDate": "2016-06-01"}}]},  # no next: the end
    }

    def fake_request(url, **kw):
        return pages[_offset_of(url)]

    monkeypatch.setattr(client, "request", fake_request)
    landmark, _ = _relations(
        max_landmark_year=this_year - 2, current_year=this_year,
        landmark_budget=lambda citer_years: 2,
    )
    # Both pages were walked (the short first page didn't end it), and the pool
    # counted as complete — the budget prefix spans both pages' citers.
    assert [hit["node"]["id"] for hit in landmark] == ["b", "a"]  # most-cited first


def test_a_failed_deep_page_means_completeness_is_unknowable(monkeypatch):
    """A deep page S2 refuses leaves the walk unable to say the list ended —
    the pool must NOT claim the corpus shape, so the SKIP path serves it."""
    calls: list[str] = []

    def fake_request(url, **kw):
        offset = _offset_of(url)
        if offset > 0:
            raise client.S2Error("deep page refused")
        return {"data": [{"citingPaper": {"paperId": "only", "citationCount": 7,
                                          "year": 2015, "publicationDate": "2015-06-01"}}],
                "next": 1000}

    monkeypatch.setattr(client, "request", fake_request)

    def budget(citer_years):
        calls.append("budget")
        return 1

    landmark, _ = _relations(
        landmark_select=lambda citer_years: [0], landmark_budget=budget,
    )
    assert calls == []  # never claimed completeness
    assert [hit["node"]["id"] for hit in landmark] == ["only"]


def test_references_default_returns_all_fetched(monkeypatch):
    """The build's default (no limit) returns the whole fetched (ranked)
    reference page."""

    def fake_request(url, **kw):
        return {"data": [{"citedPaper": {"paperId": f"r{index}", "citationCount": index}}
                         for index in range(7)]}

    monkeypatch.setattr(client, "request", fake_request)
    assert len(traversal.references("p1")) == 7


def test_recommendations_none_limit_requests_s2_max(monkeypatch):
    """A None limit asks S2 for its max recommendations page (500)."""
    seen = {}

    def fake_request(url, **kw):
        seen["url"] = url
        return {"recommendedPapers": []}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.recommendations("p1", None)
    assert "limit=500" in seen["url"]


def _offset_of(url: str) -> int:
    import re

    match = re.search(r"offset=(\d+)", url)
    return int(match.group(1)) if match else 0


def test_citation_relations_pages_past_the_latest_window(monkeypatch):
    """The fallback build pages the WHOLE reachable list, not just the latest
    window. A page holding no in-window citer used to stop it — which gutted the
    landmark relation, since the landmarks are exactly what lives further down
    (DQN: the window ends by offset 2000, the list runs back to 2019)."""
    seen_offsets = []

    def fake_request(url, method="GET", body=None, **kw):
        offset = _offset_of(url)
        seen_offsets.append(offset)
        if offset == 0:
            return {"data": [{"citingPaper": {"paperId": "new0", "citationCount": 1,
                                              "year": 2026, "publicationDate": _iso(10)}}],
                    "next": 1000}
        if offset >= 4000:
            return {"data": []}  # the citation list ends here
        # Everything from offset 1000 on is past the 12-month window — and is
        # precisely the landmark material the old stop condition threw away.
        return {"data": [{"citingPaper": {"paperId": f"old{offset}", "citationCount": 5000,
                                          "year": 2020, "publicationDate": _iso(2000)}}],
                "next": offset + 1000}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = _relations()
    # Kept paging past the first out-of-window page (1000) to the list's end.
    assert seen_offsets == [0, 1000, 2000, 3000, 4000]
    assert {hit["node"]["id"] for hit in latest} == {"new0"}  # the window is unaffected
    assert {hit["node"]["id"] for hit in landmark} == {"old1000", "old2000", "old3000"}


def test_deep_paging_stops_at_the_offset_ceiling(monkeypatch):
    """A seed whose citer list outruns S2's servable offset window stops at
    _MAX_OFFSET rather than paging forever — S2 400s past it (verified live)."""
    seen_offsets = []

    def fake_request(url, method="GET", body=None, **kw):
        offset = _offset_of(url)
        seen_offsets.append(offset)
        return {"data": [{"citingPaper": {"paperId": f"c{offset}", "citationCount": 1,
                                          "year": 2020, "publicationDate": _iso(2000)}}],
                "next": offset + 1000}

    monkeypatch.setattr(client, "request", fake_request)
    _relations()
    assert seen_offsets[-1] == traversal._MAX_OFFSET  # never requests past the ceiling
    assert seen_offsets == list(range(0, traversal._MAX_OFFSET + 1, 1000))


def test_citations_expansion_fetches_one_newest_page(monkeypatch):
    """The single-relation expansion view fetches exactly ONE newest page
    (offset 0) — the recent tip, fast; no deep paging, no mining (retired)."""
    offsets = []

    def fake_request(url, method="GET", body=None, **kw):
        offsets.append(_offset_of(url))
        return {"data": [{"citingPaper": {"paperId": "c1", "year": 2026, "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citations("p1", limit=5)
    assert offsets == [0]  # exactly one page at offset 0


def test_citations_propagates_a_fetch_outage(monkeypatch):
    """If the newest-page fetch fails, that's a real outage and propagates —
    not silently swallowed."""

    def boom(url, **kw):
        raise client.S2Error("S2 down")

    monkeypatch.setattr(client, "request", boom)
    with pytest.raises(client.S2Error):
        traversal.citations("p1", limit=5)


def test_recommendations_pool_in_url(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"recommendedPapers": [{"paperId": "s1"}]}

    monkeypatch.setattr(client, "request", fake_request)
    (hit,) = traversal.recommendations("p1", limit=5)
    assert "from=all-cs" in urls[0]  # the "recent" pool returns nothing for old seeds
    assert hit == {"node": nodes.node({"paperId": "s1"})}
