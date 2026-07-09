# `agents.lecturer`

The streamed graph lecture: the story of the visible papers told as an
ordered sequence of typed **beats** — a signpost heading, one tight
narration paragraph, and the papers to light up on the graph while it's
spoken.

## Why it exists

The lecture is the app's showpiece: press the button and the teacher
narrates the intellectual history (or intuition, the forward evolution since
the seed, a survey of the current frontier, or a bridge between two areas) over
the citation graph you're looking at, highlighting papers as the story reaches
them. The old repo did this by begging the model for
newline-delimited JSON and armoring a parser against disobedience
(fence-stripping, line buffering, malformed-JSON tolerance). Here the shape
is *enforced*, not requested: the model's output type IS `list[LectureBeat]`,
validated by Pydantic as it streams.

## How it works

```
lecturer.lecture(seed, nodes, mode, target)          main.py
  1  prompt = mode intent + SEED/TARGET header
     + the numbered paper list (prompts.node_lines)
  2  streams.drive(agent, ...) — the shared sync event bridge
  3  the output tool's args JSON is partial-parsed as it grows; a beat is
     emitted the moment the model starts the next one — narration begins
     before the lecture ends
  4  each LectureBeat -> events.Beat, indices mapped to node ids
     (prompts.idx_to_id); the beat's inline [n] markers resolved to a
     refs map (prompts.refs_from_text) for clickable citations;
     blank-text beats dropped
```

- **`config.py`** — `AGENT_ID`, `SKILLS` (`numbered-papers`,
  `teaching-voice`, `citation-discipline`), the beat-structure
  `SYSTEM_PROMPT`, and the three `MODE_INTENTS` paragraphs.
- **`main.py`** — `LectureBeat` (the model-facing beat: indices, not ids),
  the `Agent`, and `lecture`.
- No `tools.py` — the lecturer narrates what it's given. Lectures never
  expand the graph: every mode works from the visible node set exactly as
  handed in (only the researcher, on explicit questions, pulls new papers
  onto the canvas).
- **Lectures are illustrated — deterministically, not via tools.** Before
  the run, `_figure_pool` builds the mode's figure pool (cached ar5iv
  fetches; captions listed in the prompt, attachable to a beat via the
  beat's `figure` number → resolved to a proxied image + source-paper title
  on `events.Beat.figure`): intuition pools the **seed's own** figures;
  history/evolution/frontier pool the seed plus the story's **landmark papers'**
  (the most-cited arXiv papers in the mode-scoped node set — `_FIGURE_PAPERS`
  papers, `_FIGURES_PER_PAPER` each); bridge pools none. Intuition
  additionally grounds in `_seed_passages` — library passages about the
  seed (the librarian's hybrid retrieval, queried with the seed's title —
  optional context, attributed inline). Everything degrades to empty on
  any failure; a lecture never blocks on its illustrations.

## Design decisions worth knowing

- **Modes are input, not agents.** `history` / `intuition` / `evolution` /
  `frontier` / `bridge` are one `Literal` parameter selecting an intent
  paragraph — five stories, one storyteller. A typo'd mode is a `KeyError` at
  the call boundary, not a silent fall-back to `history` (the old behavior).
- **Two beat models on purpose.** The model emits `LectureBeat` with
  numbered-list *indices* (it never sees Semantic Scholar ids — see the
  `numbered-papers` skill); the frontend receives `events.Beat` with node
  *ids*. The conversion point (`_beat`) is where hallucinated indices get
  dropped: an invalid index costs one highlight, never the lecture.
- **A beat is final when its successor starts.** Under partial parsing the
  last list element may still be mid-generation, so the stream loop only
  emits elements before it, and flushes the rest from the validated final
  output. No beat is ever yielded twice or half-formed.
- **Why the event bridge, and why the factory's eager-streaming flag.**
  Two burst-bugs found live (frame-timestamped): `run_stream_sync().
  stream_output()` delivered the whole lecture at once against the real
  API — hence `streams.drive` — and Anthropic buffers a tool call's input
  JSON server-side unless `anthropic_eager_input_streaming` is set (every
  structured output IS a tool call). Both are required for beats to
  actually stream.
- **The `extras` knobs** (the researcher's budget pattern — unknown extras
  keys fail at import):
  - `frontier_window_months` — THE CURRENT FRONTIER's recency window, read
    at import into `FRONTIER_WINDOW_MONTHS`. Default 60 (~5 years), wide on
    purpose: since the OpenAlex hybrid the graph's light-green "Latest
    Publications" nodes span several years, and a 12-month lecture window
    narrated almost none of them. The orchestrator's `_story_nodes` scopes
    with it, and the FRONTIER mode intent describes the same window
    (`_window_phrase`), so the prompt and the filter can't drift.
  - `min_beats` / `max_beats` — how many beats a lecture asks for (default
    5–9), phrased into the system prompt (`_BEAT_RANGE`; pinning both ends
    to the same value reads "exactly N"). A prompt bound, not a hard cap —
    and it's also what keeps lecture length in check (see below).
- **No `max_tokens` knob.** The old `TEACHER_MAX_TOKENS` (3000) died with
  the config rewrite; the beat bound in the prompt caps length
  naturally. If runaway lectures ever appear, the knob goes in this agent's
  `extras` first.
- **Failures propagate.** Unlike the query analyst (search must never
  break), a failed lecture has no useful degraded form — the caller ends
  the event stream with `Error`.

## Who uses it, and how/why

- **`agents/orchestrator` (Phase 4d).** The `lecture` intent per
  `skills/workflows/lecture.md`: pure delegation — it calls `lecture(...)`
  with the visible node set and relays the `Beat` stream, appending
  `Done`/`Error`.
- **Old repo, traced (not yet ported):** `routes/teacher.py`'s lecture SSE
  endpoint calls `teacher.lecture_beats(seed, nodes, mode, target)` directly
  and serializes each beat dict as a `beat` SSE frame. Phase 5 rewrites that
  route to call the orchestrator instead.

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
