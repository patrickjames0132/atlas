"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed resolution and citer traversal: resolve_work, resolve_seed_work,
references, citation_relations, citations, and the title sanitizer.

client.request is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import datetime
import urllib.parse

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
    return {key: values[0] for key, values in
            urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


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


def test_landmark_is_all_time_latest_is_uniform_year_bands(monkeypatch):
    """Field Landmarks = the all-time cited_by_count query only. Latest = one
    cited_by_count query per year, from the band start up to the CURRENT year
    (no separate newest-date window), shipped oldest-first so the reveal slider
    walks toward the present — and a recent paper that's also an all-time giant
    stays a landmark, excluded from latest (not double-shown)."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 3)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    current, _, landmark_max = _split_years()  # bands: (landmark_max-2) .. current
    band_years = []

    def fake_request(url):
        params = _query(url)
        filter_clause = params["filter"]
        # No newest-date window any more: latest is publication_year bands only.
        assert params["sort"] != "publication_date:desc"
        if "publication_year:" in filter_clause:  # a 1-year band
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
    landmark, latest = traversal.citation_relations("W5")

    # Bands span from the fixed start up to and INCLUDING the current year.
    assert band_years == list(range(landmark_max - 2, current + 1))
    # Landmark = all-time only (old + recent giant); no band-only papers.
    assert {entry["node"]["id"] for entry in landmark} == {"DOI:10/giant", "DOI:10/rg"}
    latest_ids = [entry["node"]["id"] for entry in latest]
    assert "DOI:10/rg" not in latest_ids  # the recent giant stays a landmark
    assert f"DOI:10/b{landmark_max}" in latest_ids and f"DOI:10/b{current}" in latest_ids
    # Oldest-first: the earliest band year leads, the current year ends.
    assert latest[0]["node"]["id"] == f"DOI:10/b{landmark_max - 2}"
    assert latest[-1]["node"]["id"] == f"DOI:10/b{current}"
    assert latest[0]["influential"] is False


def test_latest_is_year_bands_with_no_date_window(monkeypatch):
    """Latest is built purely from ``publication_year`` bands — no
    ``from_publication_date``/``publication_date:desc`` window at all — robust to
    OpenAlex's coarse year-only (``<year>-01-01``) dates, and the bands run right
    up to the current year (the ex-window years are just more bands now)."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 1)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    current, _, landmark_max = _split_years()
    filters = []

    def fake_request(url):
        params = _query(url)
        # A date window would sort by publication_date or use from_publication_date.
        assert params["sort"] != "publication_date:desc"
        assert "from_publication_date" not in params["filter"]
        if "publication_year:" in params["filter"]:
            filters.append(int(params["filter"].split("publication_year:")[1]))
        return {"results": [], "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citation_relations("W5")
    # band_years=1 → fixed start is landmark_max; bands cover landmark_max..current.
    assert filters == list(range(landmark_max, current + 1))


def test_latest_ships_oldest_first(monkeypatch):
    """The banded citers ship oldest-first — the enumeration rank drives the
    reveal slider, which walks toward the present."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 1)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    current_year, latest_from, _ = _split_years()

    def fake_request(url):
        params = _query(url)
        filter_clause = params["filter"]
        if f"publication_year:{current_year}" in filter_clause:  # the newest band
            return {"results": [
                _work("Wnew", doi="10/new", year=current_year, date=f"{current_year}-06-01"),
                _work("Wmid", doi="10/mid", year=current_year, date=f"{current_year}-02-01"),
            ], "meta": {"next_cursor": None}}
        if f"publication_year:{latest_from}" in filter_clause:  # an older band
            return {"results": [_work("Wold", doi="10/old", year=latest_from,
                                      date=f"{latest_from}-03-01")], "meta": {"next_cursor": None}}
        return {"results": [], "meta": {"next_cursor": None}}  # other bands + landmarks empty

    monkeypatch.setattr(client, "request", fake_request)
    _, latest = traversal.citation_relations("W5")
    # Nothing trims: all three ship, running oldest → newest.
    assert [entry["node"]["id"] for entry in latest] == ["DOI:10/old", "DOI:10/mid", "DOI:10/new"]


def test_band_start_callable_places_the_band_span(monkeypatch):
    """A supplied band_start chooser places the first band year per-seed from the
    landmark distribution — it's fed the shipped landmarks' years and the
    landmark-max year, and its return is used directly (no only-widen clamp), so
    it can place the start earlier OR later than the fixed number_of_bands."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 2)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    current, _, landmark_max = _split_years()
    band_years = []
    seen_args = {}

    def fake_request(url):
        params = _query(url)
        filter_clause = params["filter"]
        if "publication_year:" in filter_clause:
            band_years.append(int(filter_clause.split("publication_year:")[1]))
            return {"results": [], "meta": {"next_cursor": None}}
        # landmarks: an old cluster (years drive the chooser)
        return {"results": [_work("Wg", doi="10/g", year=2001, cites=900)],
                "meta": {"next_cursor": None}}

    def band_start(landmark_years, lm_max):
        seen_args["years"] = landmark_years
        seen_args["lm_max"] = lm_max
        return landmark_max - 4  # place the start well back from the fixed 2-year span

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citation_relations("W5", band_start=band_start)
    # The chooser saw the landmark year and the max year (no fixed-start arg now).
    assert seen_args["years"] == [2001]
    assert seen_args["lm_max"] == landmark_max
    # Bands run from the chooser's start up to the current year, used directly.
    assert band_years == list(range(landmark_max - 4, current + 1))


def test_band_start_none_keeps_the_fixed_span(monkeypatch):
    """When the chooser returns None (or isn't supplied), the band span is the
    fixed number_of_bands — the non-adaptive fallback behavior is unchanged."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 3)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    current, _, landmark_max = _split_years()
    band_years = []

    def fake_request(url):
        params = _query(url)
        if "publication_year:" in params["filter"]:
            band_years.append(int(params["filter"].split("publication_year:")[1]))
        return {"results": [], "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citation_relations("W5", band_start=lambda years, lm_max: None)
    # None → the fixed 3-year start, bands running up to the current year.
    assert band_years == list(range(landmark_max - 2, current + 1))


def test_band_start_callable_can_place_a_later_start(monkeypatch):
    """With no only-widen clamp, a chooser may start the bands LATER than the
    fixed span too — a young seed whose landmark cluster edge is recent gets a
    tight recent frontier, not the full fixed span."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 5)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    current, _, landmark_max = _split_years()
    band_years = []

    def fake_request(url):
        params = _query(url)
        if "publication_year:" in params["filter"]:
            band_years.append(int(params["filter"].split("publication_year:")[1]))
        return {"results": [], "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    # Fixed span would start at landmark_max-4; the chooser places it LATER.
    traversal.citation_relations("W5", band_start=lambda years, lm_max: landmark_max)
    assert band_years == list(range(landmark_max, current + 1))  # tight, no widening back


def test_payload_guard_caps_all_time_query(monkeypatch):
    """The payload guard caps the (only) all-time landmark query."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 1)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    monkeypatch.setattr(traversal, "UNBOUNDED_LANDMARK_CAP", 2)

    def fake_request(url):
        params = _query(url)
        if params["sort"] == "publication_date:desc" or "publication_year:" in params["filter"]:
            return {"results": [], "meta": {"next_cursor": None}}
        assert params["per-page"] == "2"  # the guard of 2 caps the all-time query's page
        return {"results": [_work("Wa", doi="10/a", cites=900),
                            _work("Wb", doi="10/b", cites=800)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, _ = traversal.citation_relations("W5")
    assert [entry["node"]["citation_count"] for entry in landmark] == [900, 800]  # top 2 kept


def test_landmark_budget_computes_from_a_one_page_probe(monkeypatch):
    """With a landmark_budget rule, the landmark band is a STOP-prefix computed
    from ONE ranked page: the rule sees the probe's years most-cited first, and
    its count trims the band — no model, no second request when the rule stops
    inside the probe."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 1)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    landmark_queries = []
    seen: dict[str, object] = {}

    def fake_request(url):
        params = _query(url)
        if "publication_year:" in params["filter"]:
            return {"results": [], "meta": {"next_cursor": None}}
        landmark_queries.append(params)
        return {"results": [_work("Wa", doi="10/a", year=1999, cites=900),
                            _work("Wb", doi="10/b", year=2004, cites=800),
                            _work("Wc", doi="10/c", year=1999, cites=700)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)

    def budget(citer_years):
        seen["years"] = list(citer_years)
        return 2

    landmark, _ = traversal.citation_relations("W5", landmark_budget=budget)
    assert seen["years"] == [1999, 2004, 1999]  # the ranked probe, most-cited first
    assert [entry["node"]["id"] for entry in landmark] == ["DOI:10/a", "DOI:10/b"]  # a prefix
    assert len(landmark_queries) == 1  # the probe was conclusive — one request
    assert landmark_queries[0]["per-page"] == "200"  # a full page, not a predicted N


def test_landmark_budget_probe_extends_when_nothing_overflows(monkeypatch):
    """A seed whose top-200 never overflows a year is the one case the probe
    can't settle — the fetch extends to the ceiling and the rule re-measures
    over the longer ranking."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 1)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)
    landmark_calls = []

    def fake_request(url):
        params = _query(url)
        if "publication_year:" in params["filter"]:
            return {"results": [], "meta": {"next_cursor": None}}
        landmark_calls.append(params)
        # First (probe) call: exactly 200 works — the ranking may continue.
        # The extension's call: 250 works, the whole pool.
        count = 200 if len(landmark_calls) == 1 else 250
        return {"results": [_work(f"W{index}", doi=f"10/{index}", year=1900 + index, cites=999)
                            for index in range(count)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)

    def budget(citer_years):
        # Spread years never overflow: the rule admits everything it sees.
        return len(list(citer_years))

    landmark, _ = traversal.citation_relations("W5", landmark_budget=budget)
    assert len(landmark_calls) == 2  # probe, then the ceiling-sized refetch
    assert len(landmark) == 250  # measured over the full ranking


def test_landmark_budget_declining_keeps_the_flat_cap(monkeypatch):
    """A budget rule answering None (the adaptive toggle off) leaves the flat
    payload guard in charge — same fallback contract as the corpus source."""
    monkeypatch.setattr(traversal, "LATEST_NUMBER_OF_BANDS", 1)
    monkeypatch.setattr(traversal, "LATEST_NODES_PER_BAND", 40)

    def fake_request(url):
        params = _query(url)
        if "publication_year:" in params["filter"]:
            return {"results": [], "meta": {"next_cursor": None}}
        return {"results": [_work("Wa", doi="10/a", cites=900),
                            _work("Wb", doi="10/b", cites=800),
                            _work("Wc", doi="10/c", cites=700)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(traversal, "UNBOUNDED_LANDMARK_CAP", 2)
    landmark, _ = traversal.citation_relations("W5",
                                               landmark_budget=lambda citer_years: None)
    assert [entry["node"]["id"] for entry in landmark] == ["DOI:10/a", "DOI:10/b"]


def test_citations_single_relation_sorted_and_cursor_pages(monkeypatch):
    """The single-relation expansion view is a global sorted cites: query,
    cursor-paged (exercises the cursor loop)."""
    pages = {
        "*": {"results": [_work(f"W{index}", doi=f"10/{index}", cites=200 - index)
                          for index in range(200)],
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


def test_references_use_cited_by_filter_sorted(monkeypatch):
    """references() = the seed's own bibliography, a server-sorted ``cited_by:``
    query (the outbound direction), most-cited first."""
    def fake_request(url):
        params = _query(url)
        assert params["filter"] == "cited_by:W5"  # outbound: works the seed cites
        assert params["sort"] == "cited_by_count:desc"
        return {"results": [_work("Wr1", doi="10/r1", cites=50),
                            _work("Wr2", doi="10/r2", cites=10)],
                "meta": {"next_cursor": None}}

    monkeypatch.setattr(client, "request", fake_request)
    refs = traversal.references("W5", limit=10)
    assert [entry["node"]["id"] for entry in refs] == ["DOI:10/r1", "DOI:10/r2"]
    assert all(entry["influential"] is False for entry in refs)  # OpenAlex has no such flag


def test_resolve_seed_work_by_openalex_id(monkeypatch):
    """A bare ``W…`` id resolves through the free entity path, with the DETAIL
    select so the seed carries its (inverted-index) abstract."""
    calls = []

    def fake_request(url):
        calls.append(url)
        return _work("W7", doi="10/x")

    monkeypatch.setattr(client, "request", fake_request)
    work = traversal.resolve_seed_work("W7")
    assert traversal.bare_work_id(work) == "W7"
    assert "/works/W7" in calls[0]
    assert "abstract_inverted_index" in urllib.parse.unquote(calls[0])  # DETAIL select


def test_resolve_seed_work_by_doi_prefix(monkeypatch):
    """A ``DOI:<doi>`` node id resolves through the free DOI entity path."""
    calls = []
    monkeypatch.setattr(client, "request", lambda url: calls.append(url) or _work("W8"))
    traversal.resolve_seed_work("DOI:10.1/paper")
    assert "/works/doi:10.1/paper" in urllib.parse.unquote(calls[0])


def test_resolve_seed_work_by_arxiv_id_and_arxiv_node_id(monkeypatch):
    """Both a bare arXiv id and an ``ARXIV:`` node id resolve via the arXiv-DOI
    entity (the resolve_work path)."""
    calls = []
    monkeypatch.setattr(
        client, "request",
        lambda url: calls.append(url) or _work("W9", doi="10.48550/arXiv.2101.00001"),
    )
    traversal.resolve_seed_work("2101.00001")
    traversal.resolve_seed_work("ARXIV:2101.00001")
    assert len(calls) == 2
    assert all("10.48550/arXiv.2101.00001" in urllib.parse.unquote(url) for url in calls)


def test_resolve_seed_work_falls_back_to_arxiv_title(monkeypatch):
    """A bare arXiv id that misses the arXiv-DOI path (a published paper's
    canonical OpenAlex record isn't aliased to it — the AIAYN bug) resolves via
    the arXiv title → an OpenAlex title search."""
    def fake_request(url):
        if "/works/doi:" in url:  # the arXiv-DOI entity lookup misses
            raise client.OpenAlexError("nope", status=404)
        params = _query(url)  # the title search
        assert params["filter"] == "title.search:Attention Is All You Need"
        return {"results": [_work("W123", doi="10/aiayn", title="Attention Is All You Need")]}

    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(traversal.arxiv, "get_title", lambda arxiv_id: "Attention Is All You Need")
    work = traversal.resolve_seed_work("1706.03762")
    assert traversal.bare_work_id(work) == "W123"


def test_resolve_seed_work_none_when_arxiv_title_also_missing(monkeypatch):
    """The arXiv-DOI misses AND arXiv has no title → None (no infinite fallback)."""
    monkeypatch.setattr(
        client, "request",
        lambda url: (_ for _ in ()).throw(client.OpenAlexError("nope", status=404)),
    )
    monkeypatch.setattr(traversal.arxiv, "get_title", lambda arxiv_id: None)
    assert traversal.resolve_seed_work("1706.03762") is None


def test_resolve_seed_work_blank_is_none():
    assert traversal.resolve_seed_work("") is None
    assert traversal.resolve_seed_work("   ") is None


def test_related_works_reads_ids_then_batch_hydrates(monkeypatch):
    """related_works pulls the work's related_works id list, then batch-hydrates
    them via the openalex_id OR filter."""
    def fake_request(url):
        unquoted = urllib.parse.unquote(url)
        if "/works/W5" in url:  # the seed work lookup (select id,related_works)
            assert "related_works" in unquoted
            return {"id": "https://openalex.org/W5",
                    "related_works": ["https://openalex.org/W1", "https://openalex.org/W2"]}
        params = _query(url)  # the batch hydrate
        assert params["filter"] == "openalex_id:W1|W2"
        return {"results": [_work("W1", doi="10/a"), _work("W2", doi="10/b")]}

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.related_works("W5", limit=10)
    assert [entry["node"]["id"] for entry in out] == ["DOI:10/a", "DOI:10/b"]


def test_related_works_empty_when_the_work_has_none(monkeypatch):
    monkeypatch.setattr(client, "request", lambda url: {"id": "https://openalex.org/W5"})
    assert traversal.related_works("W5", limit=10) == []


def test_get_paper_hydrates_a_node(monkeypatch):
    """get_paper resolves a ref to a work and normalizes it to a detail node."""
    monkeypatch.setattr(client, "request", lambda url: _work("W7", doi="10/x", title="Hi"))
    node = traversal.get_paper("W7")
    assert node is not None and node["id"] == "DOI:10/x" and node["title"] == "Hi"


def test_get_paper_none_when_unresolvable(monkeypatch):
    """An unresolvable ref (404) yields None, not an error."""
    def not_found(url):
        raise client.OpenAlexError("nope", status=404)

    monkeypatch.setattr(client, "request", not_found)
    assert traversal.get_paper("W404") is None
