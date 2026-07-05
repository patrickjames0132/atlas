"""The Hugging Face Papers client (integrations/huggingface.py): envelope
normalization, item capping, 404-as-miss, and cache behavior.

HTTP is faked at ``_fetch_paper`` (parsers) or ``urllib.request.urlopen``
(the 404 path) — no network. The autouse temp-DB fixture isolates the cache.
"""

from __future__ import annotations

import io
import urllib.error

from arxiv_digest.integrations import huggingface as hf


def _raw_paper(**over):
    raw = {
        "id": "1706.03762",
        "upvotes": 127,
        "githubRepo": "https://github.com/tensorflow/tensor2tensor",
        "githubStars": 15000,
        "linkedModels": [
            {
                "id": f"org/model-{i}",
                "likes": 100 - i,
                "downloads": 1000 * i,
                "pipeline_tag": "text-generation",
            }
            for i in range(8)
        ],
        "linkedDatasets": [{"id": "org/data", "likes": 5, "downloads": 42}],
        "linkedSpaces": [{"id": "org/space", "emoji": "🚀"}],
        "numTotalModels": 254,
        "numTotalDatasets": 7,
        "numTotalSpaces": 356,
    }
    raw.update(over)
    return raw


# --- normalization ---------------------------------------------------------------


def test_code_links_normalizes_full_paper(monkeypatch):
    monkeypatch.setattr(hf, "_fetch_paper", lambda arxiv_id: _raw_paper())
    out = hf.get_code_links("1706.03762v5")  # version suffix stripped
    assert out["available"] is True
    assert out["paper_url"] == "https://huggingface.co/papers/1706.03762"
    assert out["upvotes"] == 127
    assert out["github"] == {
        "url": "https://github.com/tensorflow/tensor2tensor",
        "stars": 15000,
    }
    assert len(out["models"]) == 5  # capped at _MAX_ITEMS
    assert out["models"][0] == {
        "id": "org/model-0",
        "url": "https://huggingface.co/org/model-0",
        "likes": 100,
        "downloads": 0,
        "pipeline_tag": "text-generation",
    }
    assert out["datasets"][0]["url"] == "https://huggingface.co/datasets/org/data"
    assert out["spaces"][0]["url"] == "https://huggingface.co/spaces/org/space"
    assert out["spaces"][0]["emoji"] == "🚀"
    assert out["totals"] == {"models": 254, "datasets": 7, "spaces": 356}


def test_code_links_handles_sparse_paper(monkeypatch):
    # No github link, no linked repos, junk entries dropped.
    monkeypatch.setattr(
        hf,
        "_fetch_paper",
        lambda arxiv_id: {
            "id": "2301.00001",
            "upvotes": None,
            "linkedModels": [{"likes": 3}, "junk"],
            "linkedSpaces": None,
        },
    )
    out = hf.get_code_links("2301.00001")
    assert out["available"] is True
    assert out["github"] is None and out["upvotes"] == 0
    assert out["models"] == [] and out["spaces"] == []
    assert out["totals"] == {"models": 0, "datasets": 0, "spaces": 0}


def test_code_links_rejects_non_github_repo_url(monkeypatch):
    monkeypatch.setattr(
        hf, "_fetch_paper", lambda arxiv_id: _raw_paper(githubRepo="https://evil.example/repo")
    )
    assert hf.get_code_links("1706.03762")["github"] is None


def test_code_links_empty_id():
    assert hf.get_code_links("")["available"] is False


def test_empty_result_shape_has_every_key():
    assert hf.empty_result() == {
        "available": False,
        "paper_url": None,
        "upvotes": 0,
        "github": None,
        "models": [],
        "datasets": [],
        "spaces": [],
        "totals": {"models": 0, "datasets": 0, "spaces": 0},
    }


def test_empty_result_can_be_marked_available():
    assert hf.empty_result(available=True)["available"] is True


# --- 404 + caching ---------------------------------------------------------------


def test_404_is_a_cached_miss(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 404, "nf", {}, io.BytesIO(b""))

    monkeypatch.setattr(hf.urllib.request, "urlopen", fake_urlopen)
    out = hf.get_code_links("math/0211159")
    assert out["available"] is False
    assert "math%2F0211159" in calls[0]  # slash id path-encoded

    # Second lookup is served from the cached miss — no new request.
    assert hf.get_code_links("math/0211159")["available"] is False
    assert len(calls) == 1


def test_hit_is_cached_and_refresh_bypasses(monkeypatch):
    calls = []

    def fake_fetch(arxiv_id):
        calls.append(arxiv_id)
        return _raw_paper()

    monkeypatch.setattr(hf, "_fetch_paper", fake_fetch)
    hf.get_code_links("1706.03762")
    hf.get_code_links("1706.03762")
    assert len(calls) == 1
    hf.get_code_links("1706.03762", refresh=True)
    assert len(calls) == 2
