# `agents.librarian`

The offline library chat: a graph-free RAG agent answering purely from the
user's own uploaded sources (books, PDFs, web pages), citing inline by title
and page. The first *streaming* agent in the crew, and the first to load
shared skills.

## Why it exists

Not every question is about the graph. Once a user has uploaded their own
material, "just ask my books" needs no seed paper, no S2, no open canvas —
retrieval over the local library (hybrid FTS5 + vector search, see
`services/sources/README.md`) finds the relevant passages, and the librarian
answers grounded only in them. Everything runs against local data except the
one completion call.

## How it works — retrieve *then* answer

```
librarian.answer(question, history, source_ids)     main.py
  1  sources.search(question, k=chat_k, scope)      ← deterministic, model not engaged
  2  yield RetrievalTrace(found, sources)           ← "what I'm working from"
  3  no hits? yield Token(NO_HITS_ANSWER); return   ← an answer, not an error
  4  passages + question → one streamed completion
  5  yield Token(delta) as the prose arrives
```

The whole `skills/workflows/librarian.md` playbook lives in this one
generator — the orchestrator's `librarian` intent just calls it. Retrieval
running *before* the model is the design: the passages are the grounding, so
an empty library never pays for a completion, and the trace can honestly name
the sources before a single token streams.

- **`config.py`** — `AGENT_ID`, `SKILLS` (`teaching-voice` +
  `citation-discipline`), the librarian-specific `SYSTEM_PROMPT` (grounding
  scope + the `[Title, p.N]` attribution form), and `NO_HITS_ANSWER`.
- **`main.py`** — the `Agent` (instructions assembled by
  `prompts.assemble`) and `answer`.
- No `tools.py` — retrieve-then-answer needs no tool loop.

## Design decisions worth knowing

- **`instructions=`, never `system_prompt=`.** PydanticAI drops a
  `system_prompt` whenever `message_history` is passed — a follow-up turn
  would silently lose the persona. House rule for every agent (the history
  helper's docstring says why); this agent is why the rule exists, being the
  first to take history.
- **The prompt splits between package and skills.** `teaching-voice` and
  `citation-discipline` carry the shared persona and grounding ethics;
  `SYSTEM_PROMPT` here adds only what's librarian-specific. Compare the old
  repo, where each of the four teacher prompts restated the persona.
- **Scope semantics are the retrieval layer's** (`None` = whole library,
  present list = only those, `[]` = nothing) — `answer` forwards
  `source_ids` untouched, adding no interpretation of its own.
- **`chat_k` over `search_k`**: the passages are the answer's *only*
  grounding (no paper reading, no follow-up searches), so the chat retrieves
  more than the tutor's search tool will.
- **Availability is the route's problem.** The old `/api/ask_sources`
  route's 400-when-unavailable check stays in Phase 5; if the embedder is
  missing, retrieval degrades (lexical-only, or `[]` → the no-hits answer)
  rather than crashing.

## Testing

`test_main.py` fakes `sources.search` (canned passage dicts) and swaps the
model: `TestModel` streams a canned answer (trace-then-tokens order, token
reassembly); an exploding `FunctionModel` proves no hits never engage the
model; a recording `stream_function` proves the passages land tagged in the
prompt and prior turns ride ahead of it as message history; a kwargs spy
proves scope and `chat_k` reach retrieval untouched.
