"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
figures: extracting {image, caption} pairs from an ar5iv render, cached.

client.fetch_html is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations.arxiv import client, figures


def test_get_figures_extracts_image_and_caption(monkeypatch):
    html = '<figure><img src="fig1.png"><figcaption>A caption.</figcaption></figure>'
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    result = figures.get_figures("2406.12345")

    assert result["available"] is True
    assert result["figures"] == [
        {"image": f"{client.BASE_URL}/fig1.png", "caption": "A caption."}
    ]


def test_get_figures_skips_figures_without_an_image(monkeypatch):
    html = (
        "<figure><figcaption>No image here.</figcaption></figure>"
        '<figure><img src="fig1.png"><figcaption>Has one.</figcaption></figure>'
    )
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    result = figures.get_figures("2406.12345")

    assert len(result["figures"]) == 1
    assert result["figures"][0]["caption"] == "Has one."


def test_get_figures_math_becomes_delimited_latex_not_tripled_mathml(monkeypatch):
    # ar5iv renders a formula as a <math> whose children are three redundant text
    # renderings (presentation MathML, content-MathML semantics, LaTeX) — stripping
    # tags would yield garbled tripled soup. The alttext LaTeX is what we want.
    math = (
        '<math alttext="V_{*}(s)+\\epsilon_{a}" display="inline"><semantics>'
        "<mrow><msub><mi>V</mi><mo>∗</mo></msub></mrow>"  # presentation glyphs
        "<annotation-xml encoding=\"MathML-Content\">subscriptitalic-ϵa</annotation-xml>"
        '<annotation encoding="application/x-tex">V_{*}(s)+\\epsilon_{a}</annotation>'
        "</semantics></math>"
    )
    html = f'<figure><img src="fig1.png"><figcaption>The error {math} is small.</figcaption></figure>'
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    caption = figures.get_figures("2406.12345")["figures"][0]["caption"]

    # Clean, KaTeX-ready: the alttext LaTeX wrapped in $…$, no MathML soup.
    assert caption == "The error $V_{*}(s)+\\epsilon_{a}$ is small."
    assert "subscript" not in caption
    assert "∗" not in caption


def test_get_figures_math_without_alttext_is_dropped_not_garbled(monkeypatch):
    # A <math> with no alttext contributes nothing rather than leaking its
    # presentation-MathML glyphs into the caption.
    html = (
        '<figure><img src="fig1.png"><figcaption>See <math><mi>x</mi></math> here.'
        "</figcaption></figure>"
    )
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    caption = figures.get_figures("2406.12345")["figures"][0]["caption"]

    assert caption == "See here."


def test_get_figures_a_nested_figure_does_not_corrupt_the_outer_image(monkeypatch):
    html = (
        '<figure><img src="outer.png">'
        '<figure><img src="inner.png"><figcaption>inner</figcaption></figure>'
        "</figure>"
    )
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    result = figures.get_figures("2406.12345")

    assert len(result["figures"]) == 1
    assert result["figures"][0]["image"] == f"{client.BASE_URL}/outer.png"


def test_get_figures_caps_figure_count(monkeypatch):
    html = "".join(f'<figure><img src="fig{index}.png"></figure>' for index in range(20))
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    result = figures.get_figures("2406.12345")

    assert len(result["figures"]) == figures._MAX_FIGS


def test_get_figures_truncates_long_captions(monkeypatch):
    long_caption = "x" * 1000
    html = f'<figure><img src="fig1.png"><figcaption>{long_caption}</figcaption></figure>'
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: html)

    result = figures.get_figures("2406.12345")

    assert len(result["figures"][0]["caption"]) == figures._MAX_CAPTION


def test_get_figures_unavailable_when_ar5iv_has_no_render(monkeypatch):
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: None)
    assert figures.get_figures("2406.12345") == {"available": False, "figures": []}


def test_get_figures_blank_id_short_circuits(monkeypatch):
    monkeypatch.setattr(
        client, "fetch_html", lambda arxiv_id: (_ for _ in ()).throw(AssertionError("no fetch"))
    )
    assert figures.get_figures("") == {"available": False, "figures": []}


def test_get_figures_caches_across_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        client,
        "fetch_html",
        lambda arxiv_id: calls.append(arxiv_id) or '<figure><img src="f.png"></figure>',
    )

    figures.get_figures("2406.12345")
    figures.get_figures("2406.12345")

    assert len(calls) == 1  # second call served from cache


def test_get_figures_refresh_bypasses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        client,
        "fetch_html",
        lambda arxiv_id: calls.append(arxiv_id) or '<figure><img src="f.png"></figure>',
    )

    figures.get_figures("2406.12345")
    figures.get_figures("2406.12345", refresh=True)

    assert len(calls) == 2


def test_abs_url_passes_through_absolute_urls():
    assert figures._abs_url("https://other.example.com/x.png") == "https://other.example.com/x.png"


def test_abs_url_handles_host_relative_path():
    assert figures._abs_url("/assets/x.png") == f"{client.BASE_URL}/assets/x.png"


def test_abs_url_handles_document_relative_path():
    assert figures._abs_url("./x.png") == f"{client.BASE_URL}/x.png"
