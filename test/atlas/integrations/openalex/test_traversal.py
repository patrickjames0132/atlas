"""Seed resolution and citer traversal: resolve_work, citation_relations,
citations, and the title sanitizer.

client.request is faked directly — no network.
"""

from __future__ import annotations

import datetime
import urllib.parse

from atlas.config import config
from atlas.integrations.openalex import client, traversal


def _work(work_id, *, doi=None, year=2000, date=None, cites=0, title="T"):
    """A minimal raw OpenAlex work object for building fake responses."""
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "publication_date": date,
        "cited_by_count": cites,
        "authorships": [],
        "locations": [],
    }


def _query(url):
    """Parse a works URL's query params into a flat dict."""
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


def test_clean_search_strips_punctuation():
    assert traversal._clean_search("Black hole explosions?") == "Black hole explosions"
    assert traversal._clean_search("A: B, C!  D") == "A B C D"


def test_resolve_work_prefers_arxiv_doi_entity(monkeypatch):
    calls = []

    def fake_request(url):
        calls.append(url)
        return _work("W1", doi="10.48550/arXiv.2101.00001")

    monkeypatch.setattr(client, "request", fake_request)
    work = traversal.resolve_work(arxiv_id="2101.00001", title="whatever")
    assert traversal.bare_work_id(work) == "W1"
    assert len(calls) == 1 and "10.48550/arXiv.2101.00001" in calls[0]  # entity path, no search


def test_resolve_work_falls_back_to_title_search_without_year_filter(monkeypatch):
    def fake_request(url):
        if "/works/" in url and "search" not in url:
            raise client.OpenAlexError("nope", status=404)  # arxiv entity 404
        params = _query(url)
        # No publication_year filter — OpenAlex's year is unreliable, so title +
        # most-cited alone; pinning the year silently misses (data-quality wrinkle).
        assert params["filter"] == "title.search:Black hole explosions"
        assert params["sort"] == "cited_by_count:desc"
        return {"results": [_work("W2065805883", title="Black hole explosions?")]}

    monkeypatch.setattr(client, "request", fake_request)
    work = traversal.resolve_work(arxiv_id="badid", title="Black hole explosions?")
    assert traversal.bare_work_id(work) == "W2065805883"


def test_resolve_work_none_when_no_match(monkeypatch):
    monkeypatch.setattr(client, "request", lambda url: {"results": []})
    assert traversal.resolve_work(arxiv_id=None, title="Nonexistent") is None
    assert traversal.resolve_work(arxiv_id=None, title="   ?!  ") is None


def _split_years():
    """The year boundaries citation_relations derives from today (for asserts)."""
    current_year = datetime.date.today().year
    latest_from = current_year - (traversal._LATEST_YEARS - 1)
    return current_year, latest_from, latest_from - 1  # current, latest_from, landmark_max


def test_landmark_is_all_time_latest_is_window_plus_year_bands(monkeypatch):
    """Field Landmarks = the all-time cited_by_count query only. Latest = the
    newest date window PLUS one cited_by_count query per recent year (below the
    window), shipped oldest-first so the reveal slider walks toward the present
    — and a recent paper that's also an all-time giant stays a landmark,
    excluded from latest (not double-shown)."""
    monkeypatch.setattr(config.graph, "latest_band_years", 3)
    monkeypatch.setattr(config.graph, "latest_per_year", 40)
    _, latest_from, landmark_max = _split_years()
    band_years = []

    def fake_request(url):
        params = _query(url)
        filter_clause = params["filter"]
        if params["sort"] == "publication_date:desc":  # newest window
            assert filter_clause == f"cites:W5,from_publication_date:{latest_from}-01-01"
            return {"results": [_work("Wwin", doi="10/win", year=latest_from,
                                      date=f"{latest_from}-06-01")], "meta": {"next_cursor": None}}
        if "publication_year:" in filter_clause:  # a recent 1-year band
            assert params["per-page"] == "40"
            year = int(filter_clause.split("publication_year:")[1])
            band_years.append(year)
            results = [_work(f"Wb{year}", doi=f"10/b{year}", year=year, cites=year)]
            if year == landmark_max:  # this band ALSO returns the recent giant
                results.append(_work("Wrg", doi="10/rg", year=landmark_max, cites=99999))
            return {"results": results, "meta": {"next_cursor": None}}
        # all-time landmarks: an old giant + a recent giant (year == landmark_max)
        assert filter_clause == f"cites:W5,to_publication_date:{landmark_max}-12-31"
        return {"results": [_work("Wgiant", doi="10/giant", year=1999, cites=90000),
                            _work("Wrg", doi="10/rg", year=landmark_max, cites=99999)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = traversal.citation_relations("W5", landmark_limit=None, latest_limit=None)

    assert band_years == [landmark_max - 2, landmark_max - 1, landmark_max]  # 3 years to landmark_max
    # Landmark = all-time only (old + recent giant); no window/band-only papers.
    assert {entry["node"]["id"] for entry in landmark} == {"DOI:10/giant", "DOI:10/rg"}
    latest_ids = [entry["node"]["id"] for entry in latest]
    assert "DOI:10/rg" not in latest_ids  # the recent giant stays a landmark
    assert "DOI:10/win" in latest_ids and f"DOI:10/b{landmark_max}" in latest_ids
    # Oldest-first: the earliest band year leads, the newest window paper ends.
    assert latest[0]["node"]["id"] == f"DOI:10/b{landmark_max - 2}"
    assert latest[-1]["node"]["id"] == "DOI:10/win"
    assert latest[0]["influential"] is False


def test_latest_uses_year_window_not_exact_date(monkeypatch):
    """The latest window filters from Jan 1 of the first latest year — robust to
    OpenAlex's coarse year-only (``<year>-01-01``) dates, not a mid-year cutoff."""
    monkeypatch.setattr(config.graph, "latest_band_years", 1)
    monkeypatch.setattr(config.graph, "latest_per_year", 40)
    _, latest_from, _ = _split_years()
    windows = []

    def fake_request(url):
        params = _query(url)
        if params["sort"] == "publication_date:desc":
            windows.append(params["filter"])
        return {"results": [], "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citation_relations("W5", landmark_limit=None, latest_limit=None)
    assert windows == [f"cites:W5,from_publication_date:{latest_from}-01-01"]


def test_latest_limit_keeps_newest_but_ships_oldest_first(monkeypatch):
    """A latest_limit trims to the NEWEST N citers (the frontier is what the
    relation is for), but the survivors ship oldest-first — the enumeration
    rank drives the reveal slider, which walks toward the present."""
    monkeypatch.setattr(config.graph, "latest_band_years", 1)
    monkeypatch.setattr(config.graph, "latest_per_year", 40)
    current_year, latest_from, _ = _split_years()

    def fake_request(url):
        params = _query(url)
        if params["sort"] == "publication_date:desc":  # newest window
            return {"results": [
                _work("Wnew", doi="10/new", year=current_year, date=f"{current_year}-06-01"),
                _work("Wmid", doi="10/mid", year=current_year, date=f"{current_year}-02-01"),
                _work("Wold", doi="10/old", year=latest_from, date=f"{latest_from}-03-01"),
            ], "meta": {"next_cursor": None}}
        return {"results": [], "meta": {"next_cursor": None}}  # bands + landmarks empty

    monkeypatch.setattr(client, "request", fake_request)
    _, latest = traversal.citation_relations("W5", landmark_limit=None, latest_limit=2)
    # Wold (the oldest) is trimmed away; the kept two run oldest → newest.
    assert [entry["node"]["id"] for entry in latest] == ["DOI:10/mid", "DOI:10/new"]


def test_landmark_limit_caps_all_time_query(monkeypatch):
    """landmark_limit caps the (only) all-time landmark query."""
    monkeypatch.setattr(config.graph, "latest_band_years", 1)
    monkeypatch.setattr(config.graph, "latest_per_year", 40)

    def fake_request(url):
        params = _query(url)
        if params["sort"] == "publication_date:desc" or "publication_year:" in params["filter"]:
            return {"results": [], "meta": {"next_cursor": None}}
        assert params["per-page"] == "2"  # landmark_limit=2 caps the all-time query's page
        return {"results": [_work("Wa", doi="10/a", cites=900),
                            _work("Wb", doi="10/b", cites=800)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, _ = traversal.citation_relations("W5", landmark_limit=2, latest_limit=None)
    assert [entry["node"]["citation_count"] for entry in landmark] == [900, 800]  # top 2 kept


def test_citations_single_relation_sorted_and_cursor_pages(monkeypatch):
    """The single-relation expansion view is a global sorted cites: query,
    cursor-paged (exercises the cursor loop)."""
    pages = {
        "*": {"results": [_work(f"W{i}", doi=f"10/{i}", cites=200 - i) for i in range(200)],
              "meta": {"next_cursor": "PAGE2"}},
        "PAGE2": {"results": [_work("Wlast", doi="10/last", cites=1)],
                  "meta": {"next_cursor": None}},
    }

    def fake_request(url):
        params = _query(url)
        assert params["filter"] == "cites:W5"
        assert params["sort"] == "cited_by_count:desc"
        return pages[params["cursor"]]

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("W5", limit=201)
    assert len(out) == 201 and out[0]["node"]["id"] == "DOI:10/0"
