# `agents.lecturer`

The streamed graph lecture: the story of the visible papers told as an
ordered sequence of typed **beats** — a signpost heading, one tight
narration paragraph, and the papers to light up on the graph while it's
spoken.

## Why it exists

The lecture is the app's showpiece: press the button and the teacher
narrates the intellectual history (or intuition, or a bridge between two
areas) over the citation graph you're looking at, highlighting papers as
the story reaches them. The old repo did this by begging the model for
newline-delimited JSON and armoring a parser against disobedience
(fence-stripping, line buffering, malformed-JSON tolerance). Here the shape
is *enforced*, not requested: the model's output type IS `list[LectureBeat]`,
validated by Pydantic as it streams.

## How it works

```
lecturer.lecture(seed, nodes, mode, target)          main.py
  1  prompt = mode intent + SEED/TARGET header
     + the numbered paper list (prompts.node_lines)
  2  agent.run_stream_sync(...) with output_type=list[LectureBeat]
  3  stream_output() partial validation: a beat is emitted the moment the
     model starts the next one — narration begins before the lecture ends
  4  each LectureBeat -> events.Beat, indices mapped to node ids
     (prompts.idx_to_id); blank-text beats dropped
```

- **`config.py`** — `AGENT_ID`, `SKILLS` (`numbered-papers`,
  `teaching-voice`, `citation-discipline`), the beat-structure
  `SYSTEM_PROMPT`, and the three `MODE_INTENTS` paragraphs.
- **`main.py`** — `LectureBeat` (the model-facing beat: indices, not ids),
  the `Agent`, and `lecture`.
- No `tools.py` — the lecturer narrates what it's given; enrichment
  (the history backfill) is the orchestrator's job, done *before* the
  lecturer runs.

## Design decisions worth knowing

- **Modes are input, not agents.** `history` / `intuition` / `bridge` are
  one `Literal` parameter selecting an intent paragraph — three stories,
  one storyteller. A typo'd mode is a `KeyError` at the call boundary, not
  a silent fall-back to `history` (the old behavior).
- **Two beat models on purpose.** The model emits `LectureBeat` with
  numbered-list *indices* (it never sees Semantic Scholar ids — see the
  `numbered-papers` skill); the frontend receives `events.Beat` with node
  *ids*. The conversion point (`_beat`) is where hallucinated indices get
  dropped: an invalid index costs one highlight, never the lecture.
- **A beat is final when its successor starts.** Under partial validation
  the last list element may still be mid-generation, so the stream loop
  only emits elements before it, and flushes the rest from the validated
  final output. No beat is ever yielded twice or half-formed.
- **No `max_tokens` knob.** The old `TEACHER_MAX_TOKENS` (3000) died with
  the config rewrite; the 5–9 beat bound in the prompt caps length
  naturally. If runaway lectures ever appear, the knob goes in this agent's
  `extras` first.
- **Failures propagate.** Unlike the query analyst (search must never
  break), a failed lecture has no useful degraded form — the caller ends
  the event stream with `Error`.

## Who uses it, and how/why

- **`agents/orchestrator` (Phase 4d, not yet built).** The `lecture` intent
  per `skills/workflows/lecture.md`: in history mode it runs its
  deterministic `history_backfill` tool first (streaming `Trace`/`Discovery`
  events), then calls `lecture(...)` with the ancestor-enriched node set and
  relays the `Beat` stream, appending `Done`/`Error`.
- **Old repo, traced (not yet ported):** `routes/teacher.py`'s lecture SSE
  endpoint calls `teacher.lecture_beats(seed, nodes, mode, target)` directly
  and serializes each beat dict as a `beat` SSE frame. Phase 5 rewrites that
  route to call the orchestrator instead. Note: old `teacher/lecture.py`
  still hosts `history_backfill`, which is NOT superseded until Phase 4d —
  don't retire that file yet.

## Testing

`test_main.py` drives the real streaming path: `TestModel` with
`custom_output_args` (the bare output value — TestModel wraps it in the
output tool's envelope itself) streams canned beats through partial
validation, proving index→id mapping, blank-beat dropping, and
hallucinated-index tolerance; a recording `stream_function` captures the
request to pin the mode intent, SEED/TARGET header, numbered list format,
and that skills ride along as instructions; an exploding one proves model
failures reach the caller. `prompts.node_lines` / `idx_to_id` have their own
tests in `test_prompts.py`.
