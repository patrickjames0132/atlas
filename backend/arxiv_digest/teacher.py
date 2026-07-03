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
from typing import Iterator, Optional

from . import config

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
