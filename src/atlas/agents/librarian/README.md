# `agents.librarian`

The offline library chat: a graph-free RAG agent answering purely from the
user's own uploaded sources (books, PDFs, web pages), citing inline by title
and page — and, since v5.28.0, attaching real figures from the uploaded PDFs
via its one tool, `show_source_figure`. The first *streaming* agent in the
crew, and the first to load shared skills.

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
  1  sources.search(question, top_k=chat_k, scope)  ← deterministic, model not engaged
  2  yield RetrievalTrace(found, sources)           ← "what I'm working from"
  3  no hits? yield Token(NO_HITS_ANSWER); return   ← an answer, not an error
  4  passages (+ their source ids) + question →
     streams.drive'd run: show_source_figure may fire
     (FigureTrace/Figure events drain out live), then
     the structured Reply's text streams
  5  yield Token(delta) as the prose arrives
```

The whole `skills/workflows/librarian.md` playbook lives in this one
generator — the orchestrator's `librarian` intent just calls it. Retrieval
running *before* the model is the design: the passages are the grounding, so
an empty library never pays for a completion, and the trace can honestly name
the sources before a single token streams.

- **`config.py`** — `AGENT_ID`, `SKILLS` (`teaching-voice` +
  `citation-discipline`), the librarian-specific `SYSTEM_PROMPT` (grounding
  scope, the `[Title, p.N]` attribution form, and the figure-attachment
  instructions), `NO_HITS_ANSWER`, and `BUDGETS` (the `figures` cap,
  overridable via the agent entry's `extras` like the researcher's).
- **`main.py`** — the `Agent` (instructions = `SYSTEM_PROMPT` plus each
  `prompts.skill`-loaded skill; PydanticAI joins the sequence itself), the
  structured `Reply` output, and `answer`.
- **`tools.py`** — `LibrarianDeps` (queue + figure budget) and
  `show_source_figure`, a thin wrapper over the shared
  `agents/library_figures.attach_source_figure` (the researcher's twin uses
  the same core, so markers, dedupe, and error text can't drift apart).

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
- **Structured `Reply` output, not plain text** — the price of the tool:
  a model narrates its tool turns ("let me pull that figure…"), and with
  text output PydanticAI marks the first text part as the provisional final
  result, so the narration would stream as answer prose. The researcher's
  pattern (structured output; everything outside the final result ignored)
  fixes it, with `streams.partial_text` streaming the prose out of the
  output tool's partial JSON.
- **The prompt lists the retrieved passages' source ids** (`- [id] "Title"`)
  because passages cite by title+page while `show_source_figure` addresses
  by id+page — the map is the bridge, scoped to just the sources actually
  retrieved.
- **`chat_k` over `search_k`**: the passages are the answer's *only*
  grounding (no paper reading, no follow-up searches), so the chat retrieves
  more than the researcher's search tool will.
- **Availability is the route's problem.** The old `/api/ask_sources`
  route's 400-when-unavailable check stays in Phase 5; if the embedder is
  missing, retrieval degrades (lexical-only, or `[]` → the no-hits answer)
  rather than crashing.

## Who uses it, and how/why

- **`agents/orchestrator` (Phase 4d).** The `librarian`
  intent is a pure delegation: the whole `workflows/librarian.md` playbook
  already lives inside `answer(...)`, so the orchestrator just calls it,
  relays the `RetrievalTrace`/`Token` stream, and appends `Done`/`Error`.
  No model-side routing — a librarian question never costs an orchestrator
  completion.
- **Old repo, traced (not yet ported):** `routes/teacher.py`'s
  `POST /api/ask_sources` guards the door (400 when the question is blank
  or `sources.available()` says the local library can't load), pulls prior
  turns from its in-memory `_SOURCES_SESSIONS[session_id]`, calls
  `answer_from_sources(question, history, source_ids)`, and serializes the
  event tuples as `trace`/`token`/`done`/`error` SSE frames. On success it
  persists the new turn back into the session store, trimmed to
  `TEACHER_HISTORY_TURNS * 2` entries. Phase 5 rewrites this route to call
  the orchestrator with intent `librarian`; the availability check and
  history persistence stay in routes (locked decision — agents receive
  history, they never store it), and the SSE frame names fall out of each
  event's `type` tag instead of hand-matched tuple kinds.

## Testing

`test_main.py` fakes `sources.search` (canned passage dicts) and swaps the
model: `TestModel` streams a canned answer (trace-then-tokens order, token
reassembly); an exploding `FunctionModel` proves no hits never engage the
model; a recording `stream_function` proves the passages land tagged in the
prompt — with their source-id map — and prior turns ride ahead of it as
message history; a kwargs spy proves scope and `chat_k` reach retrieval
untouched; a scripted tool-then-answer run proves `show_source_figure`
attaches (sources image URL, `index=None`) and that tool-turn narration
never streams.
