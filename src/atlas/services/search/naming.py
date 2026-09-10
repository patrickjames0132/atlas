"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Resolving a paper's informal name — "DQN", "the ResNet paper" — to the paper
itself, for the composer's ``@`` lookup.

**Why this exists, measured rather than assumed.** Nothing in text can get from
``dqn`` to *Playing Atari with Deep Reinforcement Learning*: S2's free-text
search cannot reach that paper for that query even at limit 30,
``match_title('dqn')`` returns nothing, and no field of the cached node —
title, authors, abstract, tldr, venue — contains the string, because the 2013
paper predates the name. The mapping is world knowledge. So one model call
supplies the real title and a provider lookup verifies it exists.

Two things keep that affordable in a path that runs while somebody types:
the caller only reaches here when no candidate's title *is* what was typed
(:func:`has_exact_title_match`), and the answer is **cached for a day per name**,
so a nickname costs one model call rather than one per keystroke. The cache
stores misses too — "transformers" is not a paper, and asking a second time
would not change that.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging

from ...config import config
from ...integrations import openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from ..graph import Provider

log = logging.getLogger(__name__)

#: Cache-key prefix for a resolved name. Carries a schema version like the
#: graph snapshots do, so the day of entries written by an older rule become
#: unreadable rather than wrong if the shape here changes.
_NAME_PREFIX = "papername:v1:"

#: The sentinel a cached miss stores. A plain ``None`` is indistinguishable
#: from "not cached", which would re-run the model on every keystroke for
#: exactly the queries that can never resolve.
_NO_MATCH = {"miss": True}


def has_exact_title_match(nodes: list[dict], query: str) -> bool:
    """Whether a candidate's title **is** what the reader typed.

    The gate on the model call below, and the strictness is the whole point.
    The obvious gate — "does any title *contain* the query?" — was tried and
    is wrong: typing ``dqn`` returns a page of papers with "DQN" in the title
    (*Bootstrapped DQN*, *Averaged-DQN*, *Multi-DQN*), so a contains-test
    reports success while the paper the reader actually means is absent
    entirely. Text matching finding *something* is not the same as finding the
    thing.

    Equality is the one condition under which the resolve genuinely has
    nothing to add: the reader typed a paper's full title and it came back.
    Everything else — an acronym, a nickname, a half-typed title — is a case
    where world knowledge might beat the word index, and the answer is cached
    per name, so being generous here costs one call per distinct name rather
    than one per keystroke.

    Args:
        nodes: The candidates found so far.
        query: What the reader typed after ``@``.

    Returns:
        True when some candidate's title equals the query.
    """
    wanted = (query or "").strip().lower()
    if not wanted:
        return True
    return any(wanted == (node.get("title") or "").strip().lower() for node in nodes)


def paper_by_name(name: str, provider: Provider = "s2") -> dict | None:
    """Resolve an informal paper name to a real paper node, cached for a day.

    Two steps, in this order for a reason: the model proposes a title, and the
    **provider verifies it**. A model asked for a title will usually produce
    one, so without the verification a half-remembered nickname would put an
    invented paper at the top of the reader's list — the one outcome worse than
    showing them nothing.

    Args:
        name: The informal name typed after ``@``.
        provider: The active backend, so the resolved paper's id is in the same
            id space as the graph the reader is on.

    Returns:
        The paper's node dict, or None when the name isn't a paper's, the model
        isn't sure, the provider can't confirm the title, or anything fails.
        None is an ordinary outcome here, never an error: the reader keeps the
        search results they already had.
    """
    wanted = (name or "").strip()
    if not wanted:
        return None
    key = f"{_NAME_PREFIX}{provider}:{wanted.lower()}"
    cached = cache.get(key, config.graph.cache_ttl)
    if cached is not None:
        return None if cached.get("miss") else cached

    # Imported here, not at module scope: `services` does not depend on
    # `agents` anywhere else, and this module is the single exception — a
    # top-level import would make every consumer of the search service
    # construct an agent.
    from ...agents.orchestrators import summarizer

    title = summarizer.title_for_paper_name(wanted)
    if not title:
        cache.set(key, _NO_MATCH)
        return None
    try:
        if provider == "openalex":
            work = openalex.resolve_work(arxiv_id=None, title=title)
            node = openalex.node(work) if work else None
        else:
            node = s2.match_title(title)
    except Exception:
        # Not cached: the title may well be right and the provider merely
        # unreachable, so a retry later deserves a real attempt.
        log.warning("name resolution: verifying %r failed", title, exc_info=True)
        return None
    if not node:
        log.info("name resolution: %r -> %r, which no paper matches", wanted, title)
        cache.set(key, _NO_MATCH)
        return None
    cache.set(key, node)
    return node
