"""Seed discovery: a live relevance search across arXiv.

arXiv Atlas doesn't store a paper corpus, so "search" here is simply a thin pass
through to the arXiv API to find the paper you want to drop into the graph. Its
id is then handed to ``graph.build_graph``. (The digest era's hybrid lexical +
semantic search over a local store was retired with the v1.0 pivot.)
"""

from __future__ import annotations

from . import arxiv_client


def arxiv_search(query: str, limit: int = 25) -> list[dict]:
    """Relevance search across all of arXiv to find a seed paper. Accepts keywords,
    a title, an author, or an arXiv id / URL. Returns paper dicts; saves nothing."""
    return arxiv_client.search_arxiv(query, max_results=limit)
