"""code_links: envelope normalization, item capping, and cache behavior.

client.fetch_paper is faked directly — no network. The autouse temp-DB
fixture isolates the cache.
"""

from __future__ import annotations

from arxiv_digest.integrations.huggingface import client, code_links


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
    monkeypatch.setattr(client, "fetch_paper", lambda arxiv_id: _raw_paper())
    out = code_links.get_code_links("1706.03762v5")  # version suffix stripped
    assert out["available"] is True
    assert out["paper_url"] == f"{client.BASE_URL}/papers/1706.03762"
    assert out["upvotes"] == 127
    assert out["github"] == {
        "url": "https://github.com/tensorflow/tensor2tensor",
        "stars": 15000,
    }
    assert len(out["models"]) == 5  # capped at _MAX_ITEMS
    assert out["models"][0] == {
        "id": "org/model-0",
        "url": f"{client.BASE_URL}/org/model-0",
        "likes": 100,
        "downloads": 0,
        "pipeline_tag": "text-generation",
    }
    assert out["datasets"][0]["url"] == f"{client.BASE_URL}/datasets/org/data"
    assert out["spaces"][0]["url"] == f"{client.BASE_URL}/spaces/org/space"
    assert out["spaces"][0]["emoji"] == "🚀"
    assert out["totals"] == {"models": 254, "datasets": 7, "spaces": 356}


def test_code_links_handles_sparse_paper(monkeypatch):
    # No github link, no linked repos, junk entries dropped.
    monkeypatch.setattr(
        client,
        "fetch_paper",
        lambda arxiv_id: {
            "id": "2301.00001",
            "upvotes": None,
            "linkedModels": [{"likes": 3}, "junk"],
            "linkedSpaces": None,
        },
    )
    out = code_links.get_code_links("2301.00001")
    assert out["available"] is True
    assert out["github"] is None and out["upvotes"] == 0
    assert out["models"] == [] and out["spaces"] == []
    assert out["totals"] == {"models": 0, "datasets": 0, "spaces": 0}


def test_code_links_rejects_non_github_repo_url(monkeypatch):
    monkeypatch.setattr(
        client, "fetch_paper", lambda arxiv_id: _raw_paper(githubRepo="https://evil.example/repo")
    )
    assert code_links.get_code_links("1706.03762")["github"] is None


def test_code_links_empty_id():
    assert code_links.get_code_links("")["available"] is False


def test_empty_result_shape_has_every_key():
    assert code_links.empty_result() == {
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
    assert code_links.empty_result(available=True)["available"] is True


# --- caching ---------------------------------------------------------------------


def test_miss_is_cached(monkeypatch):
    calls = []

    def fake_fetch(arxiv_id):
        calls.append(arxiv_id)
        return None  # HF has no record (the 404 case, seen from code_links' side)

    monkeypatch.setattr(client, "fetch_paper", fake_fetch)
    assert code_links.get_code_links("math/0211159")["available"] is False
    # Second lookup is served from the cached miss — no new fetch.
    assert code_links.get_code_links("math/0211159")["available"] is False
    assert len(calls) == 1


def test_hit_is_cached_and_refresh_bypasses(monkeypatch):
    calls = []

    def fake_fetch(arxiv_id):
        calls.append(arxiv_id)
        return _raw_paper()

    monkeypatch.setattr(client, "fetch_paper", fake_fetch)
    code_links.get_code_links("1706.03762")
    code_links.get_code_links("1706.03762")
    assert len(calls) == 1
    code_links.get_code_links("1706.03762", refresh=True)
    assert len(calls) == 2
