"""AI teacher: streaming lecture + grounded Q&A over the on-screen graph.

Phase 3a — narration is grounded **only** in the papers currently visible on the
user's graph (the seed plus its references / citations / similar work). There is
no agentic traversal or full-text reading yet; the teacher cannot jump to papers
that aren't on screen. That agentic layer — a tool-use loop with a hop budget and
a visited-set to kill reference cycles — is Phase 3b.

Two Claude backends (set via TEACHER_BACKEND): the Anthropic API (``anthropic``
SDK) or the ``claude`` CLI under a Pro/Max subscription (no API billing). Both are
consumed here as a **stream** of text so the frontend can reveal the lecture
beat-by-beat and light up graph nodes in sync with the story.

Two products:
  * ``lecture_beats(...)`` — an ordered sequence of *beats*. Each beat is a short
    paragraph bound to a set of graph nodes to highlight. The model emits
    newline-delimited JSON, so we can parse and stream one beat at a time.
  * ``answer_stream(...)`` — a conversational reply to a question, grounded in the
    visible graph, streamed token-by-token, ending with the nodes it cited.

To keep node references robust, the model never handles the long Semantic Scholar
paperIds: we present the visible papers as a numbered list and the model refers
to them by index, which we map back to ids on the way out.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from typing import Iterator, Optional

from . import cache, config, fulltext, sources
from . import semantic_scholar as s2

log = logging.getLogger(__name__)

# Sentinel the Q&A model prints after its prose, followed by the JSON list of
# node indices it drew from. Kept out of the visible answer.
_CITED = "<<CITED>>"


# --- Streaming backends ------------------------------------------------------
def _stream_api(system: str, messages: list[dict], max_tokens: int) -> Iterator[str]:
    """Stream text deltas from the Anthropic API."""
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "TEACHER_BACKEND=api but ANTHROPIC_API_KEY is not set. Add it to .env "
            "or set TEACHER_BACKEND=claude_cli to use your Pro/Max subscription."
        )
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    with client.messages.stream(
        model=config.TEACHER_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def _flatten(messages: list[dict]) -> str:
    """Collapse a message list into one prompt string for the headless CLI.

    A lecture is a single user turn; a Q&A carries prior turns, which we label so
    the model still sees the conversation."""
    if len(messages) == 1:
        return messages[0]["content"]
    parts = []
    for m in messages:
        who = "User" if m["role"] == "user" else "Assistant"
        parts.append(f"{who}: {m['content']}")
    parts.append("Assistant:")
    return "\n\n".join(parts)


def _stream_cli(system: str, messages: list[dict], max_tokens: int) -> Iterator[str]:
    """Stream text deltas from the ``claude`` CLI (subscription, no API billing).

    Parses the CLI's ``stream-json`` events (``content_block_delta`` with a
    ``text_delta``); skips thinking deltas. Runs in a throwaway temp cwd so the
    CLI doesn't load this repo's CLAUDE.md / project context (which would bloat
    every call by thousands of cached tokens and muddy the output)."""
    cmd = [
        config.CLAUDE_CLI_PATH,
        "-p",
        _flatten(messages),
        "--system-prompt",
        system,
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if config.TEACHER_CLI_MODEL:
        cmd += ["--model", config.TEACHER_CLI_MODEL]

    # Use the subscription login, not API billing (mirrors summarizer.py).
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    with tempfile.TemporaryDirectory() as tmp:
        stderr_f = tempfile.TemporaryFile(mode="w+")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_f,
            text=True,
            env=env,
            cwd=tmp,
        )
        saw_text = False
        result_fallback: Optional[str] = None
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                if etype == "stream_event":
                    e = evt.get("event", {})
                    if e.get("type") == "content_block_delta":
                        d = e.get("delta", {})
                        if d.get("type") == "text_delta" and d.get("text"):
                            saw_text = True
                            yield d["text"]
                elif etype == "result":
                    # Emitted once at the end; keep as a fallback if no deltas
                    # streamed (e.g. partial messages disabled by a CLI update).
                    if isinstance(evt.get("result"), str):
                        result_fallback = evt["result"]
            proc.wait(timeout=config.TEACHER_CLI_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode not in (0, None):
            stderr_f.seek(0)
            err = stderr_f.read().strip()
            raise RuntimeError(
                f"claude CLI failed (exit {proc.returncode}): {err[:300]}"
            )
        if not saw_text and result_fallback:
            yield result_fallback


def _stream(system: str, messages: list[dict], max_tokens: int) -> Iterator[str]:
    """Stream a completion, trying the primary backend then the fallback.

    Fallback only helps for failures **before the first token** (missing key, CLI
    not on PATH, spawn error) — the common case. Once streaming has begun we can't
    cleanly switch, so a mid-stream failure surfaces.
    """
    primary = config.TEACHER_BACKEND
    fallback = config.TEACHER_FALLBACK_BACKEND or None
    backends = [primary]
    if fallback and fallback != primary:
        backends.append(fallback)

    last_err: Optional[Exception] = None
    for backend in backends:
        fn = _stream_api if backend == "api" else _stream_cli
        try:
            gen = fn(system, messages, max_tokens)
            first = next(gen)  # trips init/spawn errors before we commit
        except StopIteration:
            return  # backend produced nothing, but didn't error
        except Exception as exc:  # noqa: BLE001 — try the fallback
            last_err = exc
            log.warning("teacher backend %r failed to start: %s", backend, exc)
            continue
        yield first
        yield from gen
        return
    raise RuntimeError(f"all teacher backends failed ({last_err})")


# --- Shared node formatting --------------------------------------------------
def _number_nodes(nodes: list[dict]) -> list[dict]:
    """Attach a 1-based ``idx`` to each visible node (input order preserved)."""
    return [{**n, "idx": i + 1} for i, n in enumerate(nodes)]


def _node_lines(numbered: list[dict]) -> str:
    """Render the numbered papers for the prompt. One line per paper: index,
    year, title, citation count, and a summary snippet when we have one."""
    lines = []
    for n in numbered:
        year = n.get("year") or "n.d."
        cites = n.get("citation_count")
        cite_str = f", {cites} citations" if isinstance(cites, int) else ""
        summary = n.get("tldr") or n.get("abstract") or ""
        if summary:
            summary = " — " + summary.strip().replace("\n", " ")[:240]
        rels = ",".join(n.get("rels", [])) or "?"
        lines.append(f"[{n['idx']}] ({year}{cite_str}; {rels}) {n.get('title', '')}{summary}")
    return "\n".join(lines)


def _idx_to_id(numbered: list[dict], indices: object) -> list[str]:
    """Map model-emitted 1-based indices back to Semantic Scholar node ids,
    ignoring anything out of range or non-integer."""
    out: list[str] = []
    if not isinstance(indices, list):
        return out
    by_idx = {n["idx"]: n["id"] for n in numbered if n.get("id")}
    for i in indices:
        if isinstance(i, bool):
            continue
        if isinstance(i, int) and i in by_idx:
            out.append(by_idx[i])
    return out


# --- Lecture -----------------------------------------------------------------
_LECTURE_SYSTEM = (
    "You are an expert teacher narrating the intellectual history and intuition of "
    "a research area to a curious graduate student. You are given a SEED paper and "
    "the papers currently visible on an interactive citation graph (its references, "
    "citations, and similar work), presented as a numbered list. Produce a short, "
    "vivid lecture as an ordered sequence of BEATS. Each beat is one tight paragraph "
    "(2–4 sentences) that advances the story and points at specific papers so they "
    "can light up on the graph as you speak.\n\n"
    "OUTPUT FORMAT: emit ONE JSON object per line (newline-delimited JSON) and "
    "NOTHING else — no prose, no markdown, no code fences, no wrapping array. Each "
    'object is exactly: {"heading": "<3–6 word signpost>", "text": "<the narration '
    'paragraph>", "nodes": [<indices from the numbered list this beat is about>]}\n\n'
    "RULES:\n"
    "- 5–9 beats total.\n"
    "- 'nodes' must be integer indices from the numbered list; reference 1–4 papers "
    "per beat. Use [] only for a pure framing/closing beat.\n"
    "- Explain intuition and significance in plain English; avoid hype and jargon; "
    "do not merely list titles.\n"
    "- Ground claims in the titles, years, and summaries provided. Don't invent "
    "specifics the data doesn't support."
)

_MODE_INTENT = {
    "history": (
        "Mode: HOW WE GOT HERE. Tell the story chronologically — from the oldest "
        "roots among the references, through the key ideas that made each next step "
        "possible, to the SEED paper and the work it went on to spawn (its citations)."
    ),
    "intuition": (
        "Mode: INTUITION OF THIS PAPER. Center the SEED paper: what problem it "
        "solved, the core idea, and why it works — using the surrounding papers only "
        "for context and contrast."
    ),
    "bridge": (
        "Mode: BRIDGE. Build a conceptual bridge between the SEED paper and the "
        "TARGET paper, tracing the ideas that connect two areas that may look "
        "unrelated at first."
    ),
}


def _lecture_prompt(
    seed: dict, numbered: list[dict], mode: str, target: Optional[dict]
) -> str:
    intent = _MODE_INTENT.get(mode, _MODE_INTENT["history"])
    seed_title = seed.get("title", "(the seed paper)")
    header = f"SEED paper: {seed_title}"
    if mode == "bridge" and target:
        header += f"\nTARGET paper: {target.get('title', '')}"
    return (
        f"{intent}\n\n"
        f"{header}\n\n"
        f"Papers on the graph (numbered):\n{_node_lines(numbered)}\n\n"
        f"Now deliver the lecture as newline-delimited JSON beats."
    )


def _parse_beat(line: str, numbered: list[dict]) -> Optional[dict]:
    """Parse one JSONL line into a beat dict, or None if it isn't a valid beat.

    Tolerates stray code fences / blank lines the model might emit around the
    JSONL despite instructions."""
    line = line.strip().strip("`").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    text = obj.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return {
        "heading": (obj.get("heading") or "").strip(),
        "text": text.strip(),
        "node_ids": _idx_to_id(numbered, obj.get("nodes")),
    }


def lecture_beats(
    seed: dict, nodes: list[dict], mode: str = "history", target: Optional[dict] = None
) -> Iterator[dict]:
    """Yield lecture beats ``{heading, text, node_ids}`` one at a time as the model
    streams newline-delimited JSON."""
    numbered = _number_nodes(nodes)
    prompt = _lecture_prompt(seed, numbered, mode, target)
    messages = [{"role": "user", "content": prompt}]

    buf = ""
    for chunk in _stream(_LECTURE_SYSTEM, messages, config.TEACHER_MAX_TOKENS):
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            beat = _parse_beat(line, numbered)
            if beat:
                yield beat
    beat = _parse_beat(buf, numbered)
    if beat:
        yield beat


# --- Q&A ---------------------------------------------------------------------
_QA_SYSTEM = (
    "You are a sharp, friendly research teacher answering a student's question, "
    "grounded ONLY in the papers currently visible on their citation graph (the "
    "numbered list below). Answer conversationally and concretely, in a few short "
    "paragraphs at most. If the answer isn't supported by the visible papers, say "
    "so briefly and suggest where on the graph to look — do NOT invent facts or "
    "cite papers that aren't listed.\n\n"
    "After your answer, on a new final line, emit exactly " + _CITED + " followed "
    "by a JSON array of the indices of the papers you drew from, e.g. "
    + _CITED + " [1, 4]. Use " + _CITED + " [] if you cited none. Output nothing "
    "after that line."
)


def _qa_context(seed: dict, numbered: list[dict]) -> str:
    return (
        f"SEED paper: {seed.get('title', '')}\n\n"
        f"Papers on the graph (numbered):\n{_node_lines(numbered)}"
    )


def answer_stream(
    question: str,
    seed: dict,
    nodes: list[dict],
    history: Optional[list[dict]] = None,
) -> Iterator[tuple[str, object]]:
    """Answer a question grounded in the visible graph.

    Yields ``("token", text)`` events as the prose streams, then a final
    ``("cited", node_ids)`` event. The ``<<CITED>>`` sentinel and everything after
    it is stripped from the visible answer and parsed into node ids.
    """
    numbered = _number_nodes(nodes)
    messages: list[dict] = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    # The graph context rides on the current question so it always reflects the
    # latest on-screen neighborhood, even as the user pans/expands between turns.
    messages.append(
        {"role": "user", "content": f"{_qa_context(seed, numbered)}\n\nQuestion: {question}"}
    )

    buf = ""
    full = ""
    cut = False  # once we hit the sentinel, stop emitting prose
    # Hold back a tail so a sentinel split across chunks never leaks to the user.
    hold = len(_CITED)
    for chunk in _stream(_QA_SYSTEM, messages, config.TEACHER_MAX_TOKENS):
        full += chunk
        if cut:
            continue
        buf += chunk
        if _CITED in buf:
            visible, _ = buf.split(_CITED, 1)
            if visible:
                yield ("token", visible)
            cut = True
            buf = ""
            continue
        # Emit everything except a trailing window that might start the sentinel.
        if len(buf) > hold:
            emit, buf = buf[:-hold], buf[-hold:]
            if emit:
                yield ("token", emit)
    if not cut and buf:
        yield ("token", buf)

    yield ("cited", _parse_citations(full, numbered))


def _parse_citations(full: str, numbered: list[dict]) -> list[str]:
    """Pull the ``<<CITED>> [..]`` index list out of the full answer text."""
    if _CITED not in full:
        return []
    tail = full.split(_CITED, 1)[1].strip()
    start = tail.find("[")
    end = tail.find("]", start)
    if start == -1 or end == -1:
        return []
    try:
        indices = json.loads(tail[start : end + 1])
    except json.JSONDecodeError:
        return []
    return _idx_to_id(numbered, indices)


def _emit_hiding_sentinel(chunks: Iterator[str], full_box: list[str]) -> Iterator[str]:
    """Yield the visible prose from `chunks`, withholding the ``<<CITED>>`` sentinel
    and everything after it (holding back a tail so a split sentinel never leaks).
    Appends the complete raw text to ``full_box[0]`` for citation parsing."""
    buf = ""
    cut = False
    hold = len(_CITED)
    for chunk in chunks:
        full_box[0] += chunk
        if cut:
            continue
        buf += chunk
        if _CITED in buf:
            visible = buf.split(_CITED, 1)[0]
            if visible:
                yield visible
            cut = True
            buf = ""
        elif len(buf) > hold:
            out, buf = buf[:-hold], buf[-hold:]
            yield out
    if not cut and buf:
        yield buf


# --- Agentic Q&A (Phase 3b) --------------------------------------------------
# The agent answers by READING the visible papers (tool use) and can EXPAND the
# graph to papers not yet shown (Phase 3b.2) — one hop of references / citations
# / similar work from a paper it already knows about. Guardrails (config.AGENT_*):
# a total-step cap, per-kind read budgets, a hop budget for expansion, and a
# wall-clock ceiling. Requires the Anthropic API — the claude CLI can't take our
# custom tools, so the CLI backend falls back to answer_stream.
_AGENT_SYSTEM = (
    "You are a sharp, friendly research teacher answering a student's question "
    "about the papers on their citation graph (numbered below). You have tools to "
    "READ those papers and to EXPAND the graph to papers not yet shown, so answer "
    "from real content and pull in outside papers when the visible ones don't have "
    "what you need.\n\n"
    "Use read_paper to pull in what you need: detail='summary' for a quick "
    "abstract + TL;DR, detail='full' for the full text when the question needs "
    "specifics (methods, results, numbers). Use expand_node(index, relation) to "
    "fetch a paper's references, citations, or similar work when the answer needs "
    "a paper that isn't on the graph yet — the papers it finds get numbered and "
    "added, so you can read_paper them right after. Use search_papers(query, "
    "year_from?, year_to?) when the answer needs work not connected to the graph "
    "at all — recent or topical papers that citation and similarity hops can't "
    "reach (e.g. \"the latest approach to X in 2026\"); pass year_from to bias "
    "toward recent work. Its hits also get numbered and added for you to read. "
    "Read, expand, and search only what you need — each has its own limited "
    "budget. Do NOT narrate that you're about to use a tool; just call it. When "
    "you have enough, write the answer in at most a few short paragraphs, grounded "
    "in what you read. Begin with the answer itself — do NOT preface it with "
    "remarks about your reading process (no \"I found the sections\"). If nothing "
    "you can reach supports an answer, say so briefly. Never invent facts or cite "
    "papers you haven't read."
)
# Appended only when the user has a source library (Phase 3d): tells the agent it
# can search the user's own uploaded books / pages and how to attribute them.
_SOURCES_PARA = (
    "\n\nThe student has also uploaded their own sources (books, PDFs, web pages), "
    "listed under \"Your library\" below. Use search_sources(query, source_id?) to "
    "semantically search them for relevant passages when the question touches their "
    "own material (e.g. \"how does this relate to my textbook?\") — pass a source_id "
    "to search one source, or omit it to search the whole library. When you use a "
    "passage, attribute it inline in your prose, e.g. \"(Deep Learning, p.243)\". "
    "Source passages are NOT graph papers — don't put them in the " + _CITED + " list."
)
# The final-line citation instruction (kept separate so _SOURCES_PARA can slot in
# ahead of it — nothing may come after this line).
_CITED_INSTRUCTION = (
    "\n\nAfter your answer, on a new final line, emit exactly " + _CITED + " followed "
    "by a JSON array of the indices of the papers your answer draws on, e.g. "
    + _CITED + " [1, 4]. Use " + _CITED + " [] if you drew on none. Output nothing "
    "after that line."
)
_AGENT_SYSTEM += _CITED_INSTRUCTION


def _agent_system(has_sources: bool) -> str:
    """The agent system prompt, with source-search guidance slotted in ahead of
    the citation instruction when the user has a library."""
    if not has_sources:
        return _AGENT_SYSTEM
    return _AGENT_SYSTEM[: -len(_CITED_INSTRUCTION)] + _SOURCES_PARA + _CITED_INSTRUCTION

_TOOLS = [
    {
        "name": "read_paper",
        "description": (
            "Read one of the numbered papers on the graph to ground your answer. "
            "detail='summary' returns its abstract + TL;DR (cheap); detail='full' "
            "returns the full text via ar5iv (use sparingly — limited budget)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "The [n] index of the paper from the numbered list.",
                },
                "detail": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "description": "summary = abstract + TL;DR; full = full text.",
                },
            },
            "required": ["index", "detail"],
        },
    },
    {
        "name": "expand_node",
        "description": (
            "Pull one hop of neighbors — references, citations, or similar work — "
            "for a paper that's already numbered, and add them to the graph as new "
            "numbered papers you can then read_paper. Use when the question needs a "
            "paper that isn't currently visible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "The [n] index of the paper to expand from.",
                },
                "relation": {
                    "type": "string",
                    "enum": ["references", "citations", "similar"],
                    "description": (
                        "references = papers it cites; citations = papers that cite "
                        "it; similar = embedding-similar work."
                    ),
                },
            },
            "required": ["index", "relation"],
        },
    },
    {
        "name": "search_papers",
        "description": (
            "Free-text search across all of Semantic Scholar for papers matching a "
            "query, optionally bounded by year — NOT limited to the graph or its "
            "citation neighborhood. Use for recent or topical work that references / "
            "citations / similar hops can't reach (e.g. the newest paper on a topic, "
            "which an old seed can't cite). Hits get numbered and added so you can "
            "read_paper them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text query — keywords or a topic, not an id.",
                },
                "year_from": {
                    "type": "integer",
                    "description": "Earliest publication year (inclusive). Omit for no floor.",
                },
                "year_to": {
                    "type": "integer",
                    "description": "Latest publication year (inclusive). Omit for no ceiling.",
                },
            },
            "required": ["query"],
        },
    },
]

# Added to the tool set only when the user has a source library (Phase 3d).
_SOURCE_TOOL = {
    "name": "search_sources",
    "description": (
        "Semantic search over the student's OWN uploaded sources (books, PDFs, web "
        "pages) — not the citation graph or Semantic Scholar. Returns the most "
        "relevant passages, each with its source title and page. Use when the "
        "question touches their own material. Omit source_id to search everything, "
        "or pass one from \"Your library\" to search a single source."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for — a concept or question, not an id.",
            },
            "source_id": {
                "type": "string",
                "description": "Restrict to one source's id from the library (optional).",
            },
        },
        "required": ["query"],
    },
}


def agentic_available() -> bool:
    """True when we can run the tool-use agent (Anthropic API + key)."""
    return config.TEACHER_BACKEND == "api" and bool(config.ANTHROPIC_API_KEY)


def _node_by_idx(numbered: list[dict], idx: object) -> Optional[dict]:
    if not isinstance(idx, int) or isinstance(idx, bool):
        return None
    for n in numbered:
        if n.get("idx") == idx:
            return n
    return None


def _paper_text(node: dict, detail: str) -> str:
    """Assemble the text handed back to the agent for one paper read."""
    title = node.get("title") or "(untitled)"
    year = node.get("year")
    arxiv_id = node.get("arxiv_id")
    abstract = node.get("abstract")
    tldr = node.get("tldr")
    # Neighbor nodes arrive without abstract/tldr — hydrate on demand.
    if abstract is None and tldr is None:
        lookup = f"ARXIV:{arxiv_id}" if arxiv_id else node.get("id")
        hydrated = s2.get_paper(lookup) if lookup else None
        if hydrated:
            abstract = hydrated.get("abstract")
            tldr = hydrated.get("tldr")

    header = f"Title: {title}" + (f" ({year})" if year else "")
    if detail == "full" and arxiv_id:
        ft = fulltext.get_fulltext(arxiv_id)
        if ft.get("available") and ft.get("text"):
            body = ft["text"][: config.FULLTEXT_MAX_CHARS]
            tail = "\n\n[...truncated]" if len(ft["text"]) > config.FULLTEXT_MAX_CHARS else ""
            return f"{header}\nTL;DR: {tldr or '—'}\n\nFull text:\n{body}{tail}"

    parts = [header]
    if tldr:
        parts.append(f"TL;DR: {tldr}")
    parts.append(f"Abstract: {abstract}" if abstract else "Abstract: (unavailable)")
    if detail == "full" and not arxiv_id:
        parts.append("(No arXiv full text for this paper — summary only.)")
    return "\n".join(parts)


def _run_read(block, numbered: list[dict], budgets: dict, read_cache: dict) -> tuple[str, dict, Optional[str]]:
    """Execute a read_paper tool call. Returns (tool_result_text, trace, node_id)."""
    inp = getattr(block, "input", None) or {}
    idx = inp.get("index")
    detail = "full" if inp.get("detail") == "full" else "summary"
    node = _node_by_idx(numbered, idx)
    if node is None:
        return (f"No paper at index {idx}.", {"action": "read", "ok": False, "index": idx, "title": None, "detail": detail}, None)

    title = node.get("title")
    # Downgrade a full read to summary when the full budget is spent.
    if detail == "full" and budgets["full"] <= 0:
        detail = "summary"
    if budgets[detail] <= 0:
        return (
            "Read budget exhausted — answer now with what you've already gathered.",
            {"action": "read", "ok": False, "index": idx, "title": title, "detail": detail},
            node.get("id"),
        )

    ck = (node.get("id"), detail)
    if ck in read_cache:
        text = read_cache[ck]
    else:
        text = _paper_text(node, detail)
        read_cache[ck] = text
        budgets[detail] -= 1
    return (text, {"action": "read", "ok": True, "index": idx, "title": title, "detail": detail}, node.get("id"))


_REL_TAG = {"references": "reference", "citations": "citation", "similar": "similar"}


def _s2_neighbors(paper_id: str, relation: str) -> list[dict]:
    """S2 references/citations/recommendations for one hop, cached a day (same
    TTL as a graph snapshot) so repeated expansion doesn't hammer the rate limit."""
    cache_key = f"expand:{relation}:{paper_id}"
    cached = cache.get(cache_key, config.GRAPH_CACHE_TTL)
    if cached is not None:
        return cached
    if relation == "references":
        hits = s2.references(paper_id, config.AGENT_EXPAND_LIMIT)
    elif relation == "citations":
        hits = s2.citations(paper_id, config.AGENT_EXPAND_LIMIT)
    else:
        hits = s2.recommendations(paper_id, config.AGENT_EXPAND_LIMIT)
    cache.set(cache_key, hits)
    return hits


def _run_expand(
    block,
    numbered: list[dict],
    known_ids: set[str],
    expanded: set[tuple[str, str]],
    hops: dict,
) -> tuple[str, dict, Optional[dict]]:
    """Execute an expand_node tool call: pull one hop of neighbors for a paper
    already numbered and append any new ones to `numbered` so the agent can
    read_paper them next turn.

    Returns (tool_result_text, trace, discovery), where `discovery` is
    ``{"nodes": [...], "edges": [...]}`` for the frontend to merge into the live
    graph, or None when nothing new came back.
    """
    inp = getattr(block, "input", None) or {}
    idx = inp.get("index")
    relation = inp.get("relation")
    node = _node_by_idx(numbered, idx)
    if node is None or relation not in _REL_TAG:
        return (
            f"Invalid expand_node call (index={idx}, relation={relation!r}).",
            {"action": "expand", "ok": False, "index": idx, "title": None, "relation": relation},
            None,
        )

    title = node.get("title")
    paper_id = node["id"]
    if hops["left"] <= 0:
        return (
            "Expansion budget exhausted — work with what's already on the graph.",
            {"action": "expand", "ok": False, "index": idx, "title": title, "relation": relation},
            None,
        )

    key = (paper_id, relation)
    if key in expanded:
        return (
            f"Already expanded {relation} of \"{title}\" — see the numbered papers above.",
            {"action": "expand", "ok": True, "index": idx, "title": title, "relation": relation, "found": 0},
            None,
        )
    expanded.add(key)
    hops["left"] -= 1

    rel_tag = _REL_TAG[relation]
    try:
        hits = _s2_neighbors(paper_id, relation)
    except s2.S2Error as exc:
        return (
            f"Couldn't expand {relation} of \"{title}\": {exc}",
            {"action": "expand", "ok": False, "index": idx, "title": title, "relation": relation},
            None,
        )

    new_nodes: list[dict] = []
    new_edges: list[dict] = []
    lines: list[str] = []
    next_idx = numbered[-1]["idx"] + 1
    for hit in hits:
        n = hit["node"]
        nid = n["id"]
        if nid == paper_id:
            continue
        if rel_tag == "reference":
            edge = {"source": paper_id, "target": nid, "type": "reference", "influential": hit.get("influential", False)}
        elif rel_tag == "citation":
            edge = {"source": nid, "target": paper_id, "type": "citation", "influential": hit.get("influential", False)}
        else:
            edge = {"source": paper_id, "target": nid, "type": "similar"}
        new_edges.append(edge)

        if nid in known_ids:
            continue
        known_ids.add(nid)
        disc = dict(n)
        disc["rels"] = [rel_tag]
        disc["is_seed"] = False
        disc["discovered"] = True
        disc["idx"] = next_idx
        numbered.append(disc)
        new_nodes.append(disc)
        lines.append(f"[{next_idx}] ({disc.get('year') or 'n.d.'}) {disc.get('title', '')}")
        next_idx += 1

    if not lines:
        text = f"No new papers — {relation} of \"{title}\" is already on the graph."
    else:
        text = (
            f"Expanded {relation} of \"{title}\" — {len(lines)} new paper(s) added:\n"
            + "\n".join(lines)
        )
    trace = {"action": "expand", "ok": True, "index": idx, "title": title, "relation": relation, "found": len(lines)}
    discovery = {"nodes": new_nodes, "edges": new_edges} if (new_nodes or new_edges) else None
    return (text, trace, discovery)


def _s2_search(query: str, year_from: Optional[int], year_to: Optional[int]) -> list[dict]:
    """Cached free-text S2 search (same day-TTL as a graph snapshot) so repeated
    queries in a session don't re-hit the rate-limited endpoint."""
    cache_key = f"search:{query.strip().lower()}:{year_from or ''}-{year_to or ''}"
    cached = cache.get(cache_key, config.GRAPH_CACHE_TTL)
    if cached is not None:
        return cached
    hits = s2.search_papers(query, config.AGENT_SEARCH_LIMIT, year_from, year_to)
    cache.set(cache_key, hits)
    return hits


def _search_scope(year_from: Optional[int], year_to: Optional[int]) -> str:
    if year_from and year_to:
        return f" ({year_from}–{year_to})"
    if year_from:
        return f" (since {year_from})"
    if year_to:
        return f" (through {year_to})"
    return ""


def _run_search(
    block,
    numbered: list[dict],
    known_ids: set[str],
    searched: set,
    searches: dict,
) -> tuple[str, dict, Optional[dict]]:
    """Execute a search_papers tool call: run an ungrounded free-text S2 search
    and append any papers not already numbered so the agent can read_paper them.

    Returns (tool_result_text, trace, discovery). Discovery carries only nodes —
    no edges — since a topic search links the hits to no specific paper; the
    frontend anchors them near the seed so they don't fly in from the origin.
    """
    inp = getattr(block, "input", None) or {}
    query = (inp.get("query") or "").strip()
    year_from = inp.get("year_from")
    year_to = inp.get("year_to")
    if not query:
        return (
            "Invalid search_papers call (empty query).",
            {"action": "search", "ok": False, "query": query},
            None,
        )
    if searches["left"] <= 0:
        return (
            "Search budget exhausted — answer with what you've found.",
            {"action": "search", "ok": False, "query": query},
            None,
        )

    key = (query.lower(), year_from, year_to)
    if key in searched:
        return (
            f'Already searched "{query}" — see the numbered papers above.',
            {"action": "search", "ok": True, "query": query, "found": 0},
            None,
        )
    searched.add(key)
    searches["left"] -= 1

    try:
        hits = _s2_search(query, year_from, year_to)
    except s2.S2Error as exc:
        return (
            f'Couldn\'t search "{query}": {exc}',
            {"action": "search", "ok": False, "query": query},
            None,
        )

    new_nodes: list[dict] = []
    lines: list[str] = []
    next_idx = numbered[-1]["idx"] + 1
    for hit in hits:
        n = hit["node"]
        nid = n["id"]
        if nid in known_ids:
            continue
        known_ids.add(nid)
        disc = dict(n)
        disc["rels"] = ["search"]
        disc["is_seed"] = False
        disc["discovered"] = True
        disc["idx"] = next_idx
        numbered.append(disc)
        new_nodes.append(disc)
        lines.append(f"[{next_idx}] ({disc.get('year') or 'n.d.'}) {disc.get('title', '')}")
        next_idx += 1

    scope = _search_scope(year_from, year_to)
    if not lines:
        text = f'Search "{query}"{scope} returned nothing new.'
    else:
        text = (
            f'Search "{query}"{scope} — {len(lines)} new paper(s) added:\n'
            + "\n".join(lines)
        )
    trace = {
        "action": "search", "ok": True, "query": query, "found": len(lines),
        "year_from": year_from, "year_to": year_to,
    }
    discovery = {"nodes": new_nodes, "edges": []} if new_nodes else None
    return (text, trace, discovery)


def _sources_context(library: list[dict]) -> str:
    """A compact listing of the user's uploaded sources for the agent's context,
    so it knows what it can search and can scope search_sources by id."""
    lines = []
    for s in library:
        loc = f"{s['pages']}pp" if s.get("pages") else s.get("kind", "")
        lines.append(f"- [{s['id']}] \"{s['title']}\" ({loc})")
    return "Your library (search with search_sources):\n" + "\n".join(lines)


def _run_search_sources(block, source_searches: dict) -> tuple[str, dict]:
    """Execute a search_sources tool call: semantic search over the user's own
    uploaded library. Returns (tool_result_text, trace). No graph discovery —
    source passages aren't graph nodes; the agent cites them inline by page."""
    inp = getattr(block, "input", None) or {}
    query = (inp.get("query") or "").strip()
    source_id = inp.get("source_id") or None
    if not query:
        return (
            "Invalid search_sources call (empty query).",
            {"action": "search_sources", "ok": False, "query": query},
        )
    if source_searches["left"] <= 0:
        return (
            "Source-search budget exhausted — answer with what you've found.",
            {"action": "search_sources", "ok": False, "query": query},
        )
    source_searches["left"] -= 1
    try:
        hits = sources.search(query, source_id=source_id)
    except Exception as exc:
        log.exception("search_sources failed")
        return (
            f"Couldn't search your sources: {exc}",
            {"action": "search_sources", "ok": False, "query": query},
        )
    if not hits:
        return (
            f'No passages in your library matched "{query}".',
            {"action": "search_sources", "ok": True, "query": query, "found": 0},
        )
    trace = {"action": "search_sources", "ok": True, "query": query, "found": len(hits)}
    return (f'Passages from your library for "{query}":\n\n' + _format_passages(hits), trace)


def _format_passages(hits: list[dict]) -> str:
    """Render retrieved source passages for a prompt: one per line, tagged with
    the source title and (for PDFs) page so the model can cite them inline."""
    lines = []
    for h in hits:
        loc = f", p.{h['page']}" if h.get("page") else ""
        lines.append(f"[{h['source_title']}{loc}] {' '.join(h['text'].split())}")
    return "\n\n".join(lines)


def answer_agentic(
    question: str,
    seed: dict,
    nodes: list[dict],
    history: Optional[list[dict]] = None,
) -> Iterator[tuple[str, object]]:
    """Agentic Q&A: Claude reads the visible papers via tool use, then answers.

    Yields ``("trace", {...})`` as it reads/expands, ``("nodes", {...})`` when
    expand_node discovers papers not previously on the graph, ``("token", str)``
    for the streamed answer, ``("discard", None)`` if streamed preamble must be
    dropped (the turn turned out to be a tool call), and a final
    ``("cited", node_ids)`` (the papers it actually read)."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    numbered = _number_nodes(nodes)

    # Offer the source-search tool only when the user actually has a library
    # (checked before touching the embedding model, so an empty library never
    # pays the torch load). list_sources is cheap; available() loads the model.
    library = sources.list_sources()
    has_sources = bool(library) and sources.available()
    tools = _TOOLS + [_SOURCE_TOOL] if has_sources else _TOOLS
    system = _agent_system(has_sources)

    messages: list[dict] = []
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": turn["role"], "content": turn["content"]})
    context = _qa_context(seed, numbered)
    if has_sources:
        context += "\n\n" + _sources_context(library)
    messages.append({"role": "user", "content": f"{context}\n\nQuestion: {question}"})

    budgets = {"full": config.AGENT_MAX_FULL_READS, "summary": config.AGENT_MAX_SUMMARY_READS}
    read_cache: dict = {}
    known_ids = {n["id"] for n in numbered if n.get("id")}
    expanded: set[tuple[str, str]] = set()
    hops = {"left": config.AGENT_MAX_HOPS}
    searched: set = set()
    searches = {"left": config.AGENT_MAX_SEARCHES}
    source_searches = {"left": config.AGENT_MAX_SOURCE_SEARCHES}
    cited: list[str] = []
    start = time.time()

    for _ in range(config.AGENT_MAX_STEPS):
        use_tools = (time.time() - start) < config.AGENT_WALLCLOCK
        turn_text = ""
        tool_turn = False
        emit_buf = ""  # held-back tail so a split <<CITED>> sentinel never leaks
        cut = False  # once we hit the sentinel, stop emitting this turn's prose
        hold = len(_CITED)
        with client.messages.stream(
            model=config.AGENT_MODEL,
            max_tokens=config.TEACHER_MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools if use_tools else [],
        ) as stream:
            for event in stream:
                et = getattr(event, "type", "")
                if et == "content_block_start" and getattr(event.content_block, "type", "") == "tool_use":
                    if not tool_turn:
                        tool_turn = True
                        emit_buf = ""  # this turn is a tool call, not the answer
                        if turn_text.strip():
                            yield ("discard", None)  # streamed preamble wasn't the answer
                elif et == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
                    turn_text += event.delta.text
                    if tool_turn or cut:
                        continue
                    # Stream the answer while hiding the <<CITED>> sentinel from view.
                    emit_buf += event.delta.text
                    if _CITED in emit_buf:
                        visible = emit_buf.split(_CITED, 1)[0]
                        if visible:
                            yield ("token", visible)
                        cut = True
                        emit_buf = ""
                    elif len(emit_buf) > hold:
                        out, emit_buf = emit_buf[:-hold], emit_buf[-hold:]
                        yield ("token", out)
            final = stream.get_final_message()
        # Flush the held tail once we know this turn was the spoken answer.
        if not tool_turn and not cut and emit_buf:
            yield ("token", emit_buf)

        if final.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": final.content})
            results = []
            for b in final.content:
                if getattr(b, "type", "") != "tool_use":
                    continue
                if b.name == "read_paper":
                    content, trace, read_id = _run_read(b, numbered, budgets, read_cache)
                    yield ("trace", trace)
                    if read_id and read_id not in cited:
                        cited.append(read_id)
                elif b.name == "expand_node":
                    content, trace, discovery = _run_expand(b, numbered, known_ids, expanded, hops)
                    yield ("trace", trace)
                    if discovery:
                        yield ("nodes", discovery)
                elif b.name == "search_papers":
                    content, trace, discovery = _run_search(b, numbered, known_ids, searched, searches)
                    yield ("trace", trace)
                    if discovery:
                        yield ("nodes", discovery)
                elif b.name == "search_sources":
                    content, trace = _run_search_sources(b, source_searches)
                    yield ("trace", trace)
                else:
                    content = f"Unknown tool {b.name!r}."
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
            messages.append({"role": "user", "content": results})
            continue
        # end_turn: the answer already streamed as tokens. Fold the papers it
        # named via <<CITED>> into `cited` (so a follow-up answered from context,
        # without re-reading, still highlights the papers it drew on).
        for cid in _parse_citations(turn_text, numbered):
            if cid not in cited:
                cited.append(cid)
        yield ("cited", cited)
        return

    # Step budget spent mid-investigation — force a tool-free answer.
    messages.append({"role": "user", "content": "Answer now with what you've gathered."})
    full_box = [""]
    with client.messages.stream(
        model=config.AGENT_MODEL,
        max_tokens=config.TEACHER_MAX_TOKENS,
        system=system,
        messages=messages,
    ) as stream:
        for text in _emit_hiding_sentinel(stream.text_stream, full_box):
            yield ("token", text)
    for cid in _parse_citations(full_box[0], numbered):
        if cid not in cited:
            cited.append(cid)
    yield ("cited", cited)


# --- Offline library chat (Phase 3d) -----------------------------------------
# A graph-free RAG chat straight over the user's local library: retrieve the most
# relevant passages, then answer grounded only in them, citing inline by page. No
# tool loop, so it works under BOTH backends (api and the claude CLI) and needs no
# open graph — the lightweight entry point for "just ask my books a question".
_SOURCES_CHAT_SYSTEM = (
    "You are a sharp, friendly teacher answering a student's question grounded ONLY "
    "in passages retrieved from their OWN uploaded library (books, PDFs, web pages), "
    "shown below. Answer conversationally and concretely, in a few short paragraphs "
    "at most. Attribute what you draw on inline by source and page, e.g. "
    "\"(Deep Learning, p.243)\". If the passages don't contain the answer, say so "
    "plainly and suggest what to upload or how to rephrase — do NOT invent facts or "
    "cite sources that aren't shown."
)


def _hit_titles(hits: list[dict]) -> list[str]:
    """Distinct source titles among the retrieved passages, in first-seen order —
    surfaced in the trace so the chat can show which sources it drew on."""
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        t = h.get("source_title")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def answer_from_sources(
    question: str,
    history: Optional[list[dict]] = None,
    source_id: Optional[str] = None,
) -> Iterator[tuple[str, object]]:
    """Answer a question purely from the user's local library — no graph.

    Yields a single ``("trace", {...})`` naming the retrieved passages, then
    ``("token", str)`` prose events. Retrieve-then-answer (no tool use), so it runs
    on either teacher backend. ``source_id`` scopes retrieval to one source."""
    hits = sources.search(question, k=config.SOURCES_CHAT_K, source_id=source_id)
    yield ("trace", {"found": len(hits), "sources": _hit_titles(hits)})
    if not hits:
        yield (
            "token",
            "I couldn't find anything in your library about that. Try rephrasing, "
            "or upload a source that covers it.",
        )
        return

    messages: list[dict] = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"Passages from your library:\n\n{_format_passages(hits)}\n\n"
                f"Question: {question}"
            ),
        }
    )

    for chunk in _stream(_SOURCES_CHAT_SYSTEM, messages, config.TEACHER_MAX_TOKENS):
        yield ("token", chunk)
