# `agents.lecturer`

The streamed graph lecture: the story of **the papers the reader has scoped
on screen**, told as an ordered sequence of typed **beats** — a signpost
heading, one tight narration paragraph, and the papers to light up on the graph
while it's spoken.

## Why it exists

The lecture is the app's showpiece: press the button and the teacher narrates
the papers you're looking at, oldest first, highlighting each as the story
reaches it.

**What a lecture is *about* is the reader's choice, not a mode's** (v7.17.0).
Four buttons used to each carve their own slice out of the graph — the
references, the landmark citers, the recent frontier, the seed alone — and in
doing so *overrode* whatever the reader had filtered or hand-picked. Now the
scope IS the request: filter to the references and you have asked for the
history lecture; keep only recent work and you have asked for the frontier one;
alt-drag a cluster and it narrates those. Two shapes are still read off the
request rather than chosen — a `target` makes it a bridge lecture, and a scope
of **exactly one paper** makes it a *solo* one, which teaches that paper in
chapters. That paper is whichever one you selected, not the seed: the old
INTUITION mode could only teach the seed, so learning about a paper you found
meant re-seeding the graph on it first.

**One thing the scope genuinely cannot say, so the reader still picks it:
`framing`.** The same set of papers is a fair subject for a themed *summary*
or a chronological *history*, and only the reader knows which they wanted.
Summary is the default — a chronological arc is a strong claim to make about an
arbitrary selection, and forcing one produced beats about the *timeline* rather
than the papers. The old repo did this by begging the model for
newline-delimited JSON and armoring a parser against disobedience
(fence-stripping, line buffering, malformed-JSON tolerance). Here the shape
is *enforced*, not requested: the model's output type IS `list[LectureBeat]`,
validated by Pydantic as it streams.

## How it works

```
lecturer.lecture(seed, nodes, target, framing)       main.py
  0  _story_nodes: the caller's scope, oldest-first, nothing added
     _solo_subject: the one scoped paper, or None
  1  prompt = intent (bridge if target / solo if one paper / else the reader's
       framing) + SEED or SUBJECT/TARGET header
     + the numbered paper list — era-banded + a concrete year-span line ONLY
       for a history-framed many-paper lecture (prompts.node_lines_by_era),
       plain otherwise
     + (solo) the subject's full text, figures, and library passages
  2  streams.drive(agent, ...) — the shared sync event bridge
  3  the output tool's args JSON is partial-parsed as it grows; a beat is
     emitted the moment the model starts the next one — narration begins
     before the lecture ends
  4  each LectureBeat -> events.Beat, indices mapped to node ids
     (prompts.idx_to_id); the beat's inline [n] markers resolved to a
     graph_refs map (prompts.graph_refs_from_text) for clickable citations;
     blank-text beats dropped
```

- **`config.py`** — `AGENT_ID`, `SKILLS` (`numbered-papers`,
  `teaching-voice`, `citation-discipline`), the beat-structure
  `SYSTEM_PROMPT`, the `Framing` alias, the four intent paragraphs
  (`SUMMARY_INTENT`, `HISTORY_INTENT`, `SOLO_INTENT`, `BRIDGE_INTENT`), and
  the `_SPAN_NUDGE` (the full-span guardrail in words, appended to the
  history-framed lecture only).
- **`main.py`** — `LectureBeat` (the model-facing beat: indices, not ids),
  the `Agent`, and `lecture`.
- No `tools.py` — the lecturer narrates what it's given. Lectures never
  expand the graph: the scoped node set is narrated exactly as handed in (only
  the researcher, on explicit questions, pulls new papers onto the canvas).
- **Lectures are illustrated — deterministically, not via tools.** Before
  the run, `_figure_pool` builds the figure pool (cached ar5iv
  fetches; captions listed in the prompt, attachable to a beat via the
  beat's `figure` number → resolved to a proxied image + source-paper title
  on `events.Beat.figure`): a **solo** lecture pools the seed's own figures,
  untitled; a many-paper one pools the seed plus the story's most-cited arXiv
  papers (`_FIGURE_PAPERS` papers, `_FIGURES_PER_PAPER` each), each entry
  titled with its source; a **bridge** pools none. A solo lecture
  additionally **reads the seed** — `_seed_fulltext` pulls the paper's ar5iv
  body text (equations kept as LaTeX, capped at `_SEED_FULLTEXT_CHARS`) so the
  lecture teaches it in chapters with its real math — and grounds in
  `_seed_passages` library passages (the same hybrid retrieval the researcher's
  search_sources uses, queried
  with the seed's title — optional context, cited by the same `[Sn, p.N]`
  marker protocol the answer agents use, with one `SourceRefs` event emitted
  ahead of the first beat to resolve them). Everything
  degrades to empty on any failure; a lecture never blocks on its grounding.

## Design decisions worth knowing

- **The shape is read off the request; only the *framing* is named by it.**
  There is no mode parameter: `target` present → the bridge intent; a scope of
  one paper → the solo intent; anything else → summary or history, per the
  reader's `framing`. The line between the two kinds of input is worth
  holding: *which papers* is always the scope's answer, *how to tell them* is
  always the reader's. That is the
  v7.0.0 lesson applied to the lecturer — the deleted `Intent` enum was "a
  string round-trip between a route and the function next to it", and a
  `mode` field whose only remaining job was to say whether a `target` had
  been sent would have been the same thing. Three intents, one storyteller.
- **A beat lights up every paper it discusses, not just its picks.** The
  prompt asks for 1-4 indices in `nodes` — the beat's focus — but a beat over
  a broad scope routinely cites a dozen more inline as `[n]`, and those were
  silently unlit: click a beat naming sixteen papers and three would glow,
  with the card's footer reading "3 papers". `_beat` therefore unions the
  model's picks with every id in `graph_refs`, deduped, picks first. Latent
  since beats existed; invisible until a lecture's scope got wide enough for
  the gap to show. See `docs/bugs.md`.
- **The prompt forbids narrating the graph.** A `SYSTEM_PROMPT` rule bans
  remarks on the numbered list itself — its gaps, its year jumps, how many
  papers it holds, what the view includes. It is there because a
  history-framed lecture over a sparse scope wrote *"Notice the gap in the
  timeline: after [1], the graph jumps straight to 2023-2026…"*, which is a
  beat about the view rather than about any paper. The reader chose what is in
  front of the model; explaining their own selection back to them is noise.
  (The era-banded list and span line, now history-only, are what invited it.)
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
  - `min_beats` / `max_beats` — how many beats a lecture asks for (default
    7–12), phrased into the system prompt (`_BEAT_RANGE`; pinning both ends
    to the same value reads "exactly N"). A prompt bound, not a hard cap —
    and it's also what keeps lecture length in check (see below). Widened from
    5–9 as one of the full-span levers: a multi-decade history needs beats to
    spare, or reaching both ends forces skipping the middle.
- **No `max_tokens` knob.** The old `TEACHER_MAX_TOKENS` (3000) died with
  the config rewrite; the beat bound in the prompt caps length
  naturally. If runaway lectures ever appear, the knob goes in this agent's
  `extras` first.
- **Failures propagate.** Unlike the query analyst (search must never
  break), a failed lecture has no useful degraded form — the caller ends
  the event stream with `Error`.

## Who uses it, and how/why

- **`routes/agents.py`'s `POST /api/lecture`**, per
  `skills/workflows/lecture.md`: pure delegation — it types the payload,
  calls `lecture(seed, nodes, target)` and relays the `Beat` stream through
  `streams.terminated`, which appends `Done`/`Error`. The route passes the
  node list **through untouched**, because that list is the lecture's
  subject; it no longer parses an `edges` array (see the scoping note below),
  and it ignores a `mode` field from an older client rather than 400-ing a
  stale tab.

## Testing

`test_main.py` drives the real streaming path: `TestModel` with
`custom_output_args` (the bare output value — TestModel wraps it in the
output tool's envelope itself) streams canned beats through partial
validation, proving index→id mapping, blank-beat dropping, and
hallucinated-index tolerance; a recording `stream_function` captures the
request to pin which intent leads, the SEED/TARGET header, numbered list
format, the solo grounding (seed full text + figures + passages), and the
many-paper lecture's era-banded list + concrete span line, and that skills ride
along as instructions; an exploding one proves model failures reach the caller (and that
grounding failures never block a lecture). `prompts.node_lines` /
`node_lines_by_era` / `idx_to_id` have their own tests in `test_prompts.py`.


## Scoping: from relations, to edges, to the reader (v7.7.0 → v7.17.0)

`_story_nodes` decides which papers a lecture narrates, and the answer has
changed twice. It is worth keeping both turns, because each one fixed a real
bug and the second one deletes the first one's machinery.

**v7.7.0 — tags to edges.** Each mode was pinned to one relation, and scoping
filtered on `relation in node.rels`: keep the nodes tagged `reference` for
HISTORY, `citation` for EVOLUTION, `latest` for FRONTIER. That was correct
while the graph *was* the seed's neighbourhood, and quietly stopped being
correct the moment `expand_node` could grow it past that. **A tag says what a
relation is; it never says what it is *to*.** An expanded paper carries the
relation it has to *the paper it was expanded from*, so a
reference-of-a-reference is tagged `reference` and is, by tag alone,
indistinguishable from something the seed actually cites. Play a history
lecture over an expanded graph and it narrated both. No feature was broken —
the bug lived in the space between two of them. So scoping asked the edges
instead: a paper was in a mode's story iff an edge of that relation joined it
**directly to the seed** (`_seed_neighbors`), direction-agnostically.

**v7.17.0 — edges to the reader.** The mode buttons are gone, and with them
the reason to derive a node set at all. The frontend already sends exactly what
is on screen — `selectLectureNodes`: visible after the reader's filters,
narrowed to their hand-picked selection when there is one — and the mode
scoping was *throwing that away* to rebuild its own slice. Selecting five
papers and pressing a lecture button narrated something else entirely, which is
the same class of bug as v7.7.0's: the app deciding it knew better than the
thing the reader had done. `_story_nodes` now only sorts chronologically, and
adds nothing at all — not even the seed, which has its own filter chip and can
legitimately be scoped out (an empty scope is the one case it falls back to).

**`selectLectureNodes`, not the researcher's `selectGroundingNodes`**, and the
difference is one line: grounding keeps a paper the agent discovered even when
a filter hides it, the lecture's scope drops it. A lecture that promises to
narrate what is on screen must not narrate something invisible — the reader
would have no way to tell why an unfamiliar paper turned up.

What that deletes: `_MODE_RELATION`, `_seed_neighbors`, the `edges` argument,
and the route's tolerant edge parser. That parser existed for a specific
gotcha worth remembering if edges are ever sent again — react-force-graph
**replaces a link's `source`/`target` strings with the node objects
themselves**, in place, so `{"source": {...node...}}` is the normal shape off a
live canvas, and parsing only strings would have yielded zero edges and
silently restored the v7.7.0 bug.

What it inverts: an expanded paper's satellites ARE narrated now, because the
reader put them on screen. The frontend's `selectSatelliteCount` survives and
still names them in the lecture panel's intro — but as an inclusion ("that
includes the 3 papers you expanded") rather than the boundary it used to
state. See `docs/bugs.md`.
