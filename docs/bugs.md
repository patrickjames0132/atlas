# Bugs — notable, found & fixed

A running log of bugs worth remembering — the ones with a non-obvious root
cause, a surprising reproduction, or a lesson that outlives the fix. Everything
here is already **fixed and shipped**; open work lives in [OnePager.md](../OnePager.md)'s Backlog and the `todos.md` inbox. The point is institutional memory: when a
symptom recurs or someone touches the same code, the story is one grep away
instead of buried in a diff.

Keep it newest-first. One entry per bug, with **Symptom** (what was visibly
wrong), **Root cause** (the actual mechanism, not the surface), **Fix** (what
changed, and where), and **Lesson / guard** (what keeps it from coming back — a
test, an invariant). Small, obvious bugs don't need an entry — the commit
message is enough. This section is for the ones you'd want to re-read a year
later.

Split in two, because the categories age differently. **Ours** are bugs we wrote
and repaired; the lesson is about our own code, and the guard is a test. **Upstream**
are bugs in a provider's data or service — we can't repair those, only work around
them, and the entry's real job is to justify a piece of code that looks wrong
until you know the story. An upstream entry is a **standing** hazard: it can
recur with the next data release, and its workaround must survive future cleanups.

## Ours

### The keyless app couldn't start, and the settings modal couldn't change a model

*Found 2026-08-21 while wiring multi-provider support; filed then, fixed in
v7.14.0. Two bugs, one line of code.*

- **Symptom.** Two, and they looked unrelated. A machine with a blank
  `llm.providers` block couldn't start Atlas at all: `create_app` raised
  before returning, so the **keyless graph explorer** — the half of the app
  that needs no API key, and the half README.md and `docs/configuration.md`
  both promise costs nothing — was unreachable by exactly the people it was
  written for. Separately, editing an agent's vendor or model in Settings
  appeared to work (the modal saved, the value round-tripped, a reload showed
  it) and then changed nothing: the next lecture ran on the old model.
- **Root cause.** One line, repeated in five packages:

  ```python
  agent = Agent(factory.build_model(AGENT_ID), ...)   # module level
  ```

  Building the model at **import** meant importing the app constructed a
  provider for whatever vendor each agent named. Blank block → the provider
  raised → the import failed → no app. Before v7.13.0 the error was
  PydanticAI's own, *"Set the `ANTHROPIC_API_KEY` environment variable"*,
  which is doubly wrong in an app whose config rule is **no env vars at all**.

  The second symptom is the same line seen from the other side. `config.py`'s
  `reload_config` folds fresh values into the **existing** config object
  precisely so that "every consumer holds the module-level `config` and reads
  its fields late" — the codebase's stated convention. The agents were the one
  place that read early, so they held a model built from boot-time config
  forever. The modal's "no restart" promise was true for every setting except
  the ones it was built to change. The web scout had it twice over: its
  `capabilities=[WebSearch(...)]` was decided at import too, so a vendor
  switch could leave it silent on a searching vendor, or vice versa.
- **Fix.** `factory.model_for(agent_id)` — build on first use, cache against a
  **fingerprint of the config that produced it** (the agent's `provider:model`
  string plus the named vendor's whole block, so an edited key invalidates as
  surely as a switched vendor), and pass the result to the *run* rather than
  the `Agent`: `agent.run(..., model=...)`. PydanticAI accepts a model-less
  `Agent` and takes `model=` on every run method, so this needed no proxy and
  no wrapper — and `streams.drive` already forwarded `**kwargs`, so the
  streaming path changed by one argument. The web scout's `capabilities` moved
  to the same call for the same reason.
- **Lesson / guard.** *Import time is config time, and config is not constant.*
  Anything read at module scope silently opts out of `reload_config`, and any
  **construction** at module scope turns a bad value into a failure to boot
  rather than a failure to serve one request.

  The guard is the test that was impossible to write before the fix —
  `test_app_starts_with_no_llm_vendor_configured_at_all` blanks every vendor
  block, **reloads all five agent modules** (the failure was import-time, and
  they are long since imported by the time the suite runs), and asserts the
  app still answers `/api/health`. It fails on the pre-fix code, which is the
  only reason to trust it. `test_model_for_rebuilds_when_only_the_credentials_change`
  guards the subtler half: same model name, new key, must not be reused.

### A dropped connection looks exactly like a finished download

*Found 2026-08-16 by Patrick, as an ingest that died 36 minutes in. Fixed in v7.12.0.*

- **Symptom.** `atlas corpus ingest --release 2026-08-05` ran for 36 minutes,
  reached citations shard **355/395**, and died inside a DuckDB worker:

  ```
  _duckdb.InvalidInputException: Invalid Input Error: Malformed JSON in file
  "…/raw/citations/20260807_073810_00079_q5mh4_bdf393a8….gz",
  at byte 164 in line 11507038: unexpected end of data.
  ```

  It reproduced identically on every rerun, and — because ingest is
  incremental — each rerun burned straight back to the same shard. The error
  pointed at DuckDB's JSON reader, which was the wrong place to look entirely.
- **Root cause.** The shard on disk was **truncated**: 577,014,079 bytes of a
  1,073,827,198-byte object, its gzip stream ending mid-record at line
  11,507,037. `gzip -t` failed on it; the other 454 shards passed.

  It got there because `download.py` **never checked that a body was
  complete**. `_download_shard` streamed until `response.read()` returned
  empty, then unconditionally renamed the `.part` to the final `.gz`. That
  looks safe until you know what CPython does: `http.client.HTTPResponse.read(amt)`
  does *not* raise `IncompleteRead` when the socket dies mid-body — it returns
  `b""` and closes the connection, with a comment in the stdlib saying it
  would like to raise but won't, for backwards compatibility. So **a dropped
  connection is byte-for-byte indistinguishable from a clean EOF.** The
  half-shard was promoted to final and written into `download.json` as
  `{"bytes": 577014079, "done": true}` — self-consistent, authoritative, and
  wrong, which is why re-running `download` cheerfully skipped it. The
  module's own docstring claimed shards are "only renamed to the final `.gz`
  once complete"; nothing enforced it.

  The shard's mtime (Aug 15) sat days after its neighbours' (Aug 10), so this
  was a single re-fetch in a later session that lost its connection ~54% in.
- **Fix.** `_download_shard` now compares the bytes received against
  `Content-Length` **before** the rename and raises `_ShortRead` if it falls
  short, leaving the `.part` intact so the next of five retries resumes the
  tail via `Range`. The checkpoint records the advertised size alongside the
  byte count, so a shard whose size disagrees is re-fetched rather than
  trusted, and a 416 is now resolved by probing the object's real size instead
  of being guessed at. `atlas corpus verify [--deep] [--repair]` audits an
  existing corpus. Repairing the real shard cost only the missing 497 MB,
  because a truncation cuts the tail and the bytes on disk are a valid prefix.
- **Lesson / guard.** **The quiet variant is the dangerous one.** This
  truncation happened to land mid-record, so DuckDB threw. Had the cut landed
  on a line boundary the shard would have parsed cleanly, earned its `_done`
  marker, and silently dropped every edge after the cut — a citation graph
  wrong in a way no error would ever surface. A full `gzip -t` sweep of all
  455 shards (408 GB) confirmed this was the only casualty, but nothing in the
  pipeline would have told us.

  Also: **`.part`-then-rename is only as good as the completeness test behind
  it.** The atomic-rename pattern was in place and correctly implemented; it
  guarantees a reader never sees a *partially written* file, which is a
  different property from the file being *whole*. And the downloader had no
  test file at all — `test_download.py` now covers the guard, the resume, and
  the verify pass; removing the four-line check fails three of them.

### Two dollar signs in a sentence about money became one giant formula

*Found 2026-08-16 by Patrick, as a chat panel that scrolled sideways. Fixed in v7.10.0.*

- **Symptom.** Two, and nobody connected them. The docked assistant panel
  scrolled **horizontally** beside a graph. And in the same answer, a
  paragraph read as italic, letter-spaced nonsense with the spaces removed —
  `3.77billioninequityinjustthefirstninemonthsof2025](https://…`.
- **Root cause.** The answer said *"companies raised $3.77 billion … up from
  $1.8 billion in 2024"*. `remark-math` paired those two **currency** dollars
  and rendered everything between them — prose, a full URL, punctuation — as
  one inline formula. KaTeX output cannot wrap, so the 521px box pushed the
  transcript sideways; the "nonsense" was KaTeX faithfully typesetting English
  as mathematics.

  The deeper cause is that **the app had two parsers and only one knew the
  rule**. `notation/splitMath.ts` applies the CommonMark boundary rules (an
  opener isn't followed by whitespace, a closer isn't preceded by whitespace
  nor followed by a digit) precisely so that "costs $5 and $10" stays prose —
  and it has done since the notation work landed, which is why abstracts,
  beats and the detail panel never showed this. Answers were the one surface
  that renders through react-markdown instead, and remark-math pairs dollars
  far more eagerly.
- **Fix.** `notation/prepareMath.ts` makes splitMath's verdict **binding** on
  remark-math: run the parser first, escape every dollar it left in text, and
  re-emit genuine math in `$…$`/`$$…$$` (which also got `\(…\)` and `\[…\]`
  rendering in answers for the first time). Code runs are skipped — `$HOME` in
  a fenced block is a variable, and inside code a backslash is not an escape —
  and an already-escaped `\$` is left alone, since escaping it twice would
  produce a literal backslash *and* a live opener.
- **Lesson / guard.** Two lessons. **One rule, one implementation**: the
  currency heuristic existed and was correct; the bug was a second renderer
  that never asked it. And **a layout symptom can have a parsing cause** — the
  first two rounds of fixes went at the CSS (a viewport-aware width clamp,
  `overflow-wrap`, per-element scrollers) and were all reasonable, all shipped,
  and none of them the bug. What ended the guessing was a DOM measurement:
  listing every element overhanging the panel's right edge showed all of them
  inside a single `SPAN.katex`. Guarded by `test/notation/prepareMath.test.ts`
  (the reported sentence, real math, code runs, mid-stream half-formulas,
  double-escapes) and two end-to-end cases in
  `test/teacher/transcript/AnswerMarkdown.test.tsx`: a paragraph of money
  renders **no** `.katex` at all, and a real formula still does.

### A lecture narrated papers the seed had never cited

*Found 2026-08-15 by Patrick, playing a lecture over an expanded graph. Fixed in v7.7.0.*

- **Symptom.** Expand a paper or two on the graph, then play "How it began".
  The lecture told the story of papers the seed has no relationship to at
  all — confidently, and with correct-looking citations, because every paper
  it named really was on screen.
- **Root cause — a tag says what a relation *is*, never what it is *to*.**
  `_story_nodes` scoped each mode by `relation in node.rels`: HISTORY kept
  nodes tagged `reference`, EVOLUTION `citation`, FRONTIER `latest`. That was
  exactly right while the graph *was* the seed's neighbourhood. Then
  `expand_node` shipped, and an expanded paper is tagged with the relation it
  has to **the paper it was expanded from** — so a reference-of-a-reference
  carries `rels=["reference"]` and is, by tag alone, indistinguishable from
  something the seed actually cites. There was no bug in either feature; the
  bug appeared in the space between them, and only when a reader used both.
- **Fix.** Scope by **edges**, which can express what tags structurally
  cannot. `/api/lecture` now takes the graph's edges, and `_seed_neighbors`
  keeps only papers joined directly to the seed by an edge of that mode's
  relation. Deliberately **direction-agnostic** — a `reference` edge runs
  seed→cited while `citation`/`latest` run citer→seed, but the question is
  adjacency to the seed, not which way the arrow points, so a future relation
  can't be mis-scoped by getting its direction backwards. Empty edges fall
  back to tag scoping: over-including beats a lecture with no papers in it.
- **Lesson / guard.** **A derived label is not a relationship.** `rels` was
  always a *rendering* concern — what colour to paint a node — and it got
  reused as a *semantic* one, which held only while the graph had a single
  origin. When a feature later broke that assumption, nothing failed; the
  label just quietly stopped meaning what its readers thought. Ask whether an
  attribute encodes a fact about the thing or a fact about a *pair* of things.
  If it's about a pair, the edge is the only honest home for it.

  Two guards, one per side. `test_a_paper_expanded_off_a_reference_is_not_part_of_the_seeds_history`
  asserts the satellite is excluded **and** that its tag is identical to a real
  reference's — without that second assertion the test would pass for the
  wrong reason. And a route test pins a trap worth knowing: react-force-graph
  **mutates a link's `source`/`target` from id strings into the node objects
  themselves**, in place, so `{"source": {...node...}}` is the *normal* shape
  off a live canvas. Parsing only strings would have silently yielded zero
  edges, fallen back to tag scoping, and restored the bug with every test
  still green.

  A third thing the fix bought: the reader is now *told*. Papers with no edge
  to the seed are counted (`selectSatelliteCount`, the same predicate the
  backend scopes by) and named in the lecture panel's intro, so their absence
  reads as a stated boundary rather than as the lecture skipping papers.

### A cache-key version bump left the local search silently blind

*Found 2026-08-15 by Patrick, testing direct search's instant results. Fixed in v7.6.0.*

- **Symptom.** Direct search's cache-first list never appeared. The stream was
  provably fine — a timing probe against the real server showed the frames
  arriving 1s apart exactly as designed — and the cache provably had content:
  four graph snapshots sat in `data/digest.db`. But `local_search("qmix")`
  returned **0 hits**, as did every other query. No error, no warning, no
  empty-cache message. Just a cache-first search that had quietly stopped
  being cache-first.
- **Root cause — two places knowing one key format, and only one of them
  updated.** v7.5.0 removed `Counts.similar` from the `Graph` model. Because
  the model is `extra="forbid"`, every *stored* snapshot carrying the dead
  field would now fail `model_validate` — a validation **error**, not a cache
  miss. The fix was to version the key: `graph:{provider}:{seed}` became
  `graph:v2:{provider}:{seed}`, so stale entries become unreadable instead of
  poisonous and age out on the TTL. That worked exactly as intended for
  `build_graph`, which writes and reads the key.

  What nobody noticed is that a *second* reader existed. `local_search` doesn't
  fetch a snapshot by key — it **scans a prefix**, `cache.scan(f"graph:{provider}:")`,
  to sweep every cached graph for papers matching a query. A prefix scan
  can't fail loudly: it matched nothing, returned `[]`, and every caller
  treated that as "the cache has nothing for you", which is a perfectly
  ordinary answer. The feature degraded to its own no-op for two releases.
- **Fix.** One writer of the key format, one reader: `snapshot_prefix(provider)`
  in `services/graph/build.py`, next to the `SNAPSHOT_VERSION` constant and its
  note about when to bump it. `build_graph` composes its key from it;
  `local_search` scans with it. Neither can drift again without the other
  moving.
- **Lesson / guard.** **A prefix scan is a silent reader.** A keyed `get` that
  misses is indistinguishable from a key that never existed, which is fine — a
  miss is a legal outcome. But a *scan* returning nothing is also a legal
  outcome, and that is the trap: when the shape of the key changes, the scan
  doesn't break, it just stops finding things, and "no cached results" is
  exactly what a healthy empty cache looks like. Anything that both writes and
  prefix-scans a key needs the format in **one** place.

  The guard is `test_local_search_reads_the_same_key_prefix_build_graph_writes`,
  which seeds the cache through `snapshot_prefix` and asserts the scan finds
  it — so the two agree by test rather than by everyone remembering. Worth
  noting what would *not* have caught this: the existing `local_search` tests
  all passed throughout, because they seeded the cache with their own
  hardcoded `graph:s2:...` keys. They tested the function against a fixture
  that had drifted with it. A test that builds its input the way production
  builds it is worth several that don't.

### The grounding guard deadlocked the agent into losing the whole answer

*Found 2026-08-15 by Patrick, testing the web→papers join. Fixed in v7.1.0.*

- **Symptom.** A question about a paper already on the graph. The agent read
  four papers, then the trace filled with **failures** — a refused read, then
  two refused web searches — and the panel ended in red: *"The next request
  would exceed the request_limit of 16."* No answer at all, after 87 seconds.
- **Root cause — a guard demanding what the run could no longer reach.** The
  coverage guard (`_must_have_looked`) bounces a substantive answer that
  skipped an available source. "Available" was read from *config*: the web is
  available when its budget is non-zero. But budgets are also spent at
  *runtime*, and this run spent all 12 steps on reads before it ever reached
  the web. From there it was a closed loop, and each lap cost two requests:
  `search_web` refused (`STEPS_EXHAUSTED` — it never reached the scout, which
  is how `data/atlas.log` proves it, with no `search_web need=` line for the
  whole run) → the model wrote an answer → the guard saw `web_searches_run ==
  0` and bounced it with *"call search_web"* → the model obeyed. Twice, until
  the `UsageLimits` backstop fired. The 16 model requests in the log are the
  whole story: 12 fast ones (the steps), then long-short, long-short — two
  full answers written and thrown away.
- **The near miss.** `web_enabled` exists *for this exact failure* and its
  comment says so — "availability is one fact, and both consumers must read
  the same one or the guard demands a source the model has no way to reach."
  It was written for the operator's off switch and stopped there. The hazard
  was correctly identified and then guarded in only one of its two forms.
- **Fix.** `_unconsulted` now returns only sources that are **still
  reachable** — a spent step budget returns the empty list outright, and each
  source additionally checks its own remaining budget. `_doomed` shares that
  function, so held-back streaming stayed consistent for free. `max_steps`
  went 12 → 16 in the same change, for the separate reason that v7.0.0 and
  v7.1.0 gave the agent more to do per turn (three sources to sweep, then the
  join) than 12 was chosen for.
- **Lesson / guard.** *An enforcement rule must be satisfiable by the agent it
  polices.* The guard's job is to stop the model **choosing** to skip a
  source; punishing it for a budget it doesn't control turns a
  quality check into a liveness bug — and the failure mode is the worst one
  available, since an ungrounded answer (which provenance reports honestly
  anyway) beats no answer. Note that the deadlock needed no exotic state: any
  run that spends its steps before the sweep finishes reproduces it.
  `test_a_spent_step_budget_ends_the_coverage_obligation` and
  `test_a_spent_source_budget_ends_the_library_obligation` pin both halves —
  the second because the library is where the two counters genuinely diverge
  (`search_sources` charges its budget before retrieval and counts the consult
  after, so a retrieval that throws spends one without earning the other).

### The agent looked hung whenever it delegated — and the obvious fix made it worse

*Found 2026-08-15 by Patrick, testing the workers ticket. Fixed in v7.0.0.*

- **Symptom.** Ask "what's new in quantum computing" and the panel sat
  completely empty for up to 90 seconds, then filled in all at once. Nothing
  was broken — the answer arrived, the scouts had done their work — but every
  reader would have concluded the app had frozen and reloaded.
- **Root cause — a queue with no reader.** Tool-side events reach the stream
  through `deps.queue`, which `researcher.answer` drains *between run events*:
  `for event in stream: yield from deps.drain()`. A tool call produces **no run
  events while it executes**, so nothing queued inside a tool can surface until
  the tool returns. That was invisible for years because every tool was one
  quick fetch. A worker delegation is a whole sub-agent — several provider
  calls for papers, a provider-side web search for the web — so the same
  structure that had been fine at 200ms became a 90-second silence.
- **The obvious fix, and why it was wrong.** Announce the step *before* it
  runs, on `FunctionToolCallEvent` — the event that fires when the model
  requests a tool. It is named exactly right and it does not work:
  pydantic-ai delivers it **after** the tool has executed, so the "starting"
  chip arrived *behind* the result it was meant to precede. This was caught
  only because the test asserted the order of the two traces rather than their
  presence. The signal that genuinely precedes execution is `PartEndEvent` —
  the model finishing writing the tool call.
- **Fix.** Scouts emit a `pending` trace on `PartEndEvent`; the finished trace
  **replaces** its pending twin in the store (`traceAdded`) so one chip fills
  in rather than two stacking up. Separately, the web scout dropped from Sonnet
  to Haiku with `max_uses` 4 → 2 — it was the slow half, and `data/atlas.log`
  had one of its calls holding a connection for 86 seconds.
- **Lesson / guard.** *An event named for a thing is not proof it precedes
  that thing.* When ordering matters, assert the order — a presence check
  would have passed on the broken version and shipped a progress indicator
  that reports the past. `test_a_scout_announces_itself_before_it_runs` pins
  the sequence. The deeper lesson is about the drain: anything long-running
  inside a tool is invisible by construction, so a tool that grows from a
  fetch into a delegation needs its own "starting" signal, not just a result.

### "OpenAlex doesn't build these graphs" — an id handed to the wrong namespace

*Found 2026-08-14 by Patrick, reported as a graph-build failure. Fixed in
v6.14.0.*

- **Symptom.** With the Data source dropdown on OpenAlex, clicking a citation
  in a landing-page chat answer failed with *"Could not build that graph."*
  Every S2 click worked. The obvious reading — and the one the error text
  invites — is that the OpenAlex graph builder is broken.
- **Root cause.** It wasn't the builder; it was handed an id that never
  existed in OpenAlex. `streamAskSources` (`api/agents.ts`) had no `provider`
  field, and `api_ask_sources` (`routes/agents.py`) never read one, so its
  `orchestrator.run(Intent.RESEARCH, …)` call omitted it and the researcher
  fell to the default backend — Semantic Scholar. The chat therefore searched
  S2 while the header said OpenAlex, and its citations carried 40-hex S2
  paperIds. The seeding click (v6.11.0) built with the *workspace's* provider,
  producing `?seed=<S2 paperId>&provider=openalex`, which
  `openalex.resolve_seed_work` correctly found nothing for. `data/atlas.log`
  had both halves in plain sight: `semantic_scholar.client` requests during an
  OpenAlex session, then `graph build failed for 9ecbd3cf…`.
- **Why it hid.** `/api/ask` and `/api/ask_sources` are siblings serving the
  same agent, and the graph-mode one *did* send the provider — so the feature
  looked implemented. And nothing failed loudly at the boundary: a wrong
  provider isn't a type error, it's a lookup in the wrong namespace, which
  returns "not found" and is indistinguishable from a genuinely missing paper.
- **Fix.** Two parts, because the missing field was only the proximate cause.
  (a) Thread `provider` through the graph-free ask, via the same
  `resolve_provider` every other provider-keyed route uses. (b) Bind ids to
  their namespace: `events.PaperRef` now carries the `provider` that minted
  its `node_id` (stamped by `prompts.paper_refs`), and the seeding click
  builds under *that*, moving the dropdown with it. Without (b) the same
  failure returns the moment the dropdown is switched mid-conversation, or a
  session saved under one backend is restored under the other — neither of
  which (a) touches.
- **Lesson / guard.** *A bare id is not a reference.* Two providers, two id
  spaces, one `str` type — so the compiler, the schema, and the route
  boundary are all blind to a mix-up, and the failure surfaces far from its
  origin as "not found." Anything that crosses a provider boundary (stored,
  saved, or streamed to the frontend) should carry its provider with it. Two
  tests guard the halves: `test_ask_sources_runs_on_the_requested_provider`
  (routes) and `test_paper_refs_carry_the_backend_that_minted_the_ids`
  (researcher), plus the frontend's seed-under-the-ref's-provider case.

### The "fully offline" test suite was loading a real BERT model — and it took Windows CI to notice

*Found 2026-08-09 by the very first CI run (v6.10.0), on `windows-latest`.
Green on macOS and Linux for as long as the test had existed.*

- **Symptom.** `uv run nox` died on the Windows runner with
  `Windows fatal exception: access violation`, the C-level crash of the
  interpreter — exit code `3221225477`. The traceback bottomed out in
  `torch/cuda/graphs.py`'s `is_current_stream_capturing`, reached from
  `sentence_transformers … encode` ← `embeddings.embed_query` ←
  `retrieval._vector_search` ← the researcher's `search_sources` tool ←
  `test_show_source_figure_attaches_a_library_figure`. Linux passed the same
  commit.
- **Root cause — the crash was the messenger, not the message.** That test
  takes only `monkeypatch`; it never asks for `stub_embeddings`. Its scripted
  agent calls `search_sources`, which runs the *real* retrieval path, which
  embeds the query with a *real* sentence-transformers model. So the suite
  downloaded and ran a BERT model on any machine where torch was importable —
  flatly contradicting `test/atlas/conftest.py`'s "fully offline" guarantee.
  It had never been *noticed* because `_load_model` swallows failures and
  returns `None`: wherever torch was missing or the model wouldn't load, the
  code degraded silently to lexical search and the test passed anyway. Windows
  CI was simply the first environment where torch *was* present, *was*
  loadable, and was the **CUDA build with no GPU** — where the same code path
  doesn't degrade, it segfaults.
- **The second, self-inflicted half.** CI had set `ATLAS_SKIP_TORCH=1` so
  `bin/setup.sh` would skip torch entirely, which would have masked this
  forever. It didn't work: **`uv run` syncs the project before running**, so
  `uv run nox` reinstalled the very package the bootstrap had excluded. The
  timings gave it away — bootstrap 25s (no CUDA download), then `uv run nox`
  3:09. Fixed with `uv run --no-sync nox`.
- **Fix.** The autouse `_isolate` fixture now also forces
  `config.sources.semantic_enabled` off, so no test can reach a real embedder
  by accident. This is deliberately the same place, and the same reasoning, as
  the earlier `s2_corpus` leak — both are "a real resource on the developer's
  machine silently replaces the test double." `stub_embeddings` is unaffected
  (it patches `available`/`embed_texts`/`embed_query`, above the config gate).
  The three loader tests in `test_embeddings.py` opt back in through
  `_install_fake`, which is safe because the `sentence_transformers` it
  installs is a fake module.
- **Lesson / guard.** **A test that passes because a dependency is missing is
  not passing — it's abstaining.** `_load_model`'s catch-all `except` is right
  for production (slow beats unavailable) but it means an isolation leak in
  tests shows up as *nothing at all*. When a fixture exists to replace a heavy
  dependency, the default must be that the real one is unreachable, not that
  well-behaved tests remember to ask. Verified by running the suite with torch
  **installed** and asserting neither `torch` nor `sentence_transformers` ends
  up in `sys.modules`: 605 passed, no leak, and the suite got 2.7x faster
  (7.7s → 2.8s) purely from stopping the model-load attempts. That timing drop
  is itself the tell nobody had thought to look for.

### The frontend format/lint hooks never ran on a test-only commit

*Found 2026-08-09 while wiring oxlint's `id-length` rule (v6.9.0) — not by a
symptom, but by reading the hook config to check the new rule would fire.*

- **Symptom.** None, which is the point. `uv run nox -s precommit` was always
  green, and so was every commit. But `pre-commit` on an actual
  **`git commit` touching only `frontend/test/`** silently ran neither
  prettier nor oxlint.
- **Root cause.** Both hooks are `pass_filenames: false` — they shell out to
  `npm run format` / `npm run lint`, which cover `src/` **and** `test/`. What
  decides whether the hook runs at all is the separate `files:` regex, and
  that had been left at `^frontend/(src/.*\.(ts|tsx|css)|vite\.config\.ts)$`.
  So the *scripts* covered `test/` while the *trigger* did not: the two
  drifted apart the moment the prettier script's glob grew a `test/` entry,
  and nothing tied them together. `nox -s precommit` hid it completely,
  because `pre-commit run --all-files` passes every file and every hook
  matches something.
- **Fix.** Widened both patterns to
  `^frontend/((src|test)/.*\.(ts|tsx|css)|vite\.config\.ts|\.oxlintrc\.json)$`
  — `test/` because the scripts already lint it and the naming convention
  applies there too, and `.oxlintrc.json` because a config-only change should
  re-judge the tree.
- **Lesson / guard.** For a `pass_filenames: false` hook, the `files:` regex
  is a *second, independent* declaration of scope — it must be re-checked
  whenever the underlying script's globs change, or the hook quietly narrows.
  And a green `nox -s precommit` is **not** evidence the git hook fires:
  `--all-files` masks every trigger-pattern gap. To test the real thing, stage
  a file of the kind in question and run `pre-commit run` without `--all-files`.

### A recall answer said nothing about being recall — when there was no library

*Found by Patrick on day one of v6.7.0 (2026-08-06), and misdiagnosed twice
before the logs settled it.*

- **Symptom.** Asking the chat about The Odyssey — deliberately off-topic, to
  see whether recall was reachable at all — produced a full answer with no
  library search and **no grounding line at all**. The answer looked
  authoritative and said nothing about where it came from, which is the exact
  failure the provenance line exists to prevent.
- **The two wrong diagnoses.** Both of us assumed the model had labelled a
  real question `conversational` to excuse itself from searching — a genuine
  design weakness (`_must_have_looked` only fires on `answered`, and `kind` is
  self-reported by the party it constrains), so the story fit. It was wrong.
  `grep 'answer kind=' data/atlas.log` showed
  `kind=answered library=False searches=0`: the classification was correct
  every time, and there simply was **no library in scope** on those turns.
- **Root cause.** A missing branch in `transcript/provenance.ts`. The
  skip-the-library line was gated on `had_library && searches === 0`, so a
  turn with *no* library fell past every case to `return null`. The one
  situation where the answer is unambiguously recall — nothing to consult, so
  nothing consulted — was the one situation that rendered nothing.
- **Fix (v6.7.1).** Restructure around the question that actually matters:
  once a pleasantry is ruled out, **every** answer that cites nothing names
  where it came from. No library is now its own case ("answered from
  background knowledge") rather than falling through the library-shaped
  branches.
- **Lesson / guard.** Two. First, the code lesson: when a predicate reads
  `X && Y`, check what happens when `X` is false — here the `!had_library`
  path was never written, only unreached. Second, the diagnostic one: *a
  plausible story that fits the symptom is not a diagnosis.* The conversational
  loophole explained the evidence perfectly and was still not the cause; one
  grep of the log ended twenty minutes of confident reasoning in the wrong
  direction. That log line exists because the same ticket added it — which is
  the argument for logging a model's own claims next to the observed counts.
  Guarded by the no-library recall cases in `provenance.test.ts`.

  *(The conversational loophole is real regardless, just not what happened
  here. v6.7.1 narrowed it pre-emptively — `answered` is now the prompt's
  default and `kind` rides on `Provenance` and the log — and the Backlog
  tracks the escalation if it ever does misfire.)*

### A rejected answer streamed to the screen before the guard could reject it

*Caught while designing the look-before-you-answer guard (2026-08-06), before
it ever shipped — the design worked and the plumbing around it didn't.*

- **Symptom.** With the output validator in place, an answer that skipped the
  library got bounced and retried correctly — but the **rejected** prose had
  already streamed into the chat bubble, so the student watched a complete
  answer appear and then be replaced by a different one. Worse, the two could
  disagree: the first was the from-memory answer the guard exists to prevent.
- **Root cause.** A timing assumption that only breaks once something can
  reject an answer. PydanticAI output validators run **after** the output tool
  call completes, but the researcher streams prose *out of that same tool
  call's partial JSON* (`streams.partial_text`) so the answer appears as it's
  written. Nothing was wrong with either half; they simply can't both be true
  — by the time the validator can say no, every token is already on the wire.
  The retry then made it worse: a second output tool call resets `args_buffer`
  but not `emitted`, so the new answer's tokens are sliced against the old
  one's length.
- **Fix.** Evaluate the guard's condition *while* the args stream and withhold
  prose until the attempt is known-good — `_doomed` in `researcher/main.py`,
  checked before any `Token` is yielded. It reads `kind` out of the partial
  JSON, which is safe on a single character because the two values disagree at
  the first: **a**nswered vs **c**onversational. An empty read means the field
  hasn't arrived, so it holds rather than guessing.
- **Lesson / guard.** *Streaming implies acceptance* — the pre-check and the
  validator evaluate the identical predicate, and no tool runs between them to
  change the answer, so anything that reaches the user is guaranteed to
  survive. Any future output validator has to extend `_doomed` too, or it
  reintroduces exactly this. Guarded by
  `test_the_retried_answer_never_reaches_the_stream`, which asserts the
  rejected text never appears in the token stream.

### Paper citations went dead the moment the graph did

*Found by Patrick browser-testing the librarian retirement (2026-08-06) — the
same bug, in the same shape, as the one fixed a version earlier for library
sources.*

- **Symptom.** In graph-free chat, an answer that cited papers rendered its
  `[n]` markers as inert grey text. Not merely unclickable: there was **no way
  to learn what paper `[1]` was**, so the answer looked sourced while naming
  nothing.
- **Root cause.** The `[n]` protocol carries an unstated assumption — that the
  frontend holds the same numbered list the model was shown. True with a graph
  open (it *is* the visible nodes, so `useConversation` resolves markers
  itself). False without one: every paper arrives mid-answer as a `Discovery`,
  and the graph-free stream had no `onDiscovery` handler and never dispatched
  `refsSet`, so `message.refs` stayed undefined and every marker fell through
  `AnswerMarkdown`'s unresolved-marker branch. The assumption had simply never
  been false before — until v6.7.0 let the researcher run with no graph.
- **Fix.** The same shape as the v6.6.0 fix for library citations: when the
  frontend can't resolve a marker, the **backend streams the resolution**. A
  `PaperRefs` event (`prompts.paper_refs`) carries title + URL for the markers
  the finished prose actually used, and `AnswerMarkdown`'s `citeref` falls back
  to it — rendering the real title, linked to the paper — whenever the graph
  chip isn't available.
- **Lesson / guard.** This is the second instance of one root pattern: *a
  citation whose resolution lives only on one side of the wire dies whenever
  that side is absent.* Sources hit it in v6.6.0, papers in v6.7.0. Any new
  citation flavor should ship its resolution with it rather than assuming the
  frontend can reconstruct one. Guarded on both sides:
  `test_paper_refs_resolve_the_markers_the_prose_used` (backend) and the
  no-graph rendering cases in `AnswerMarkdown.test.tsx`, including that the
  graph chip still wins when a graph *is* open.

### A failed figure chip named the wrong figure, in a book that numbers with hyphens

*Found by Patrick browser-testing the librarian (2026-07-19): a failed figure
attach rendered as a bare "Tried **Figure 1**" — naming neither the source it
reached into nor, as it turned out, the figure it actually asked for.*

- **Symptom.** Two different wrongnesses that looked like one. A **failed**
  attach produced a chip with no source name and a figure number the book
  didn't use; a **successful** attach on a hyphen-numbered book (the Feynman
  Lectures: "Figure 3-2") showed the card headed **"Figure 3"** with its
  caption beginning at a stray `-2.`.
- **Root cause.** Three mechanisms, none in the renderer — `ChatMessage.tsx`
  had drawn "of <title>" correctly all along, it was simply never given one:
  (1) the two earliest failure paths in `agents/library_figures.py` fail
  *before* the source resolves, so they emitted `title=None`; (2) `label` was
  only ever set on the success path (it's split off the resolved caption), so
  a failure fell back to `Figure {figure}` — and `figure` is the **page-local
  ordinal** ("the 2nd figure on p.42"), not the source's own numbering, so
  that fallback confidently named a figure that may not exist; (3)
  `captions.split_label`'s number pattern accepted only dotted forms
  (`3`, `12.4`, `A.2`), so **chapter-hyphenated numbering truncated**:
  "Figure 3-2. Two-slit interference." split into label `Figure 3` and rest
  `-2. Two-slit interference.`
- **Fix.** Failure traces now look the title up from `source_id` (a local
  SQLite read on an already-failing path, degrading to an unnamed chip if it
  too fails, so it can never mask the original error) and carry an
  **attempted** label — `figure 2 on p.42` — which says what was asked for
  instead of asserting a number. The label regex accepts hyphen/en-dash/
  em-dash numbering, but only when digits follow immediately, so a spaced
  "Figure 3 - A single slit" keeps its dash in the caption.
- **Lesson / guard.** *A fallback that states a fact is worse than one that
  states a request.* "Figure 1" reads as the source's own label; "figure 1 on
  p.72" can only be read as the address that was tried — and the same
  mislabeling family as the Sarsa(λ) incident below, where our text asserted
  something about a figure we hadn't actually identified. Guarded by
  `test/atlas/agents/test_library_figures.py` (every emit path's chip
  contract, including the unknown-source and lookup-explodes degradations)
  and the hyphen/en-dash/spaced-dash cases in `test_captions.py`. Note the
  hyphen truncation was found *by writing the test*, not by the browser
  round — the assertion "Figure 3-2 beats the ordinal" simply failed.

### The Sarsa(λ) figure that "didn't exist" — three stacked reasons a captioned textbook figure was unminable

*Found by Patrick browser-testing the v5.28.0 fixes (2026-07-18): asked for
Figure 12.9 (Sarsa(λ)'s backup diagram) by name; the tool insisted the book
had no such extractable figure — while the PDF plainly captions it on p326.*

- **Symptom.** `show_source_figure` reported "no extractable figures" for a
  properly captioned, numbered textbook figure, and the model relayed the
  miss as "returned as uncaptioned inline diagrams" (parroting our error
  text's parenthetical).
- **Root cause.** Three independent gaps, uncovered one beneath the next:
  (1) **paper-sized mining caps** — `extract_floats` stopped at 80 pages /
  12 floats, so a 548-page textbook's manifest ended in chapter 2 and
  everything beyond was invisible; (2) with the caps lifted, the diagram was
  *still* missed because it's drawn as a **swarm of tiny vector pieces**
  (arrow/node clusters of 200–1200 pt²), every one below the 4000 pt²
  per-cluster floor that guarded against junk; (3) with small pieces
  admitted, contact-only chaining (8 pt pad) **couldn't walk the sparse
  diagram** — its pieces relate diagonally, 40–60 pt apart, so only one
  fragment near the caption seeded and the region fell under the size floor.
- **Fix.** Caps became the caller's, with book-sized `config.pdf.library_*`
  values for uploaded sources (paper values unchanged for OA mining); the
  size threshold moved from inputs to the answer (`_MIN_CLUSTER_AREA` now
  only drops dust; the grown region must clear `_MIN_REGION_AREA`); chaining
  became **axis-aware** (`_chain_near`: overlap in one axis, ≤ 60 pt gap in
  the other), which climbs the whole diagram from one seeded piece. Cached
  manifests re-mine via the `srcfloats:v3:` key bump. Verified on the real
  book: 119 floats cover-to-cover in ~6 s, Figure 12.9 mined and rendered;
  the spike corpus (attention/PPO/LDA) mines identically to before.
- **Lesson / guard.** Limits tuned for one corpus (papers) become silent
  data loss on another (books) — size caps belong to the call-site, and
  input-side quality filters discard evidence that only aggregates into
  significance (the swarm was junk piecewise, a figure collectively;
  threshold the *answer*). Guarded by `test_max_pages_cap` (caps are
  per-call), the region-floor behavior in the synthetic float tests, and
  this entry.

### The backup-diagrams incident — a tool that listed pages without captions invited figure hallucination

*Found by Patrick browser-testing the v5.28.0 library-figures branch
(2026-07-18): asked for Sutton & Barto's Bellman backup diagrams, got the
Chapter-2 bandit parameter study confidently captioned as backup diagrams.*

- **Symptom.** The librarian attached a real, correctly-rendered figure
  (image and caption agreed — extraction was NOT at fault) whose content had
  nothing to do with the prose describing it: the model presented Figure 2.6
  (bandit parameter study) as "the backup diagrams for the Bellman optimality
  equations".
- **Root cause.** Three stacked design gaps, reconstructed from
  `data/atlas.log`. (1) The wanted backup diagrams are **uncaptioned inline
  graphics** — invisible to caption-anchored mining (the documented
  limitation, and textbooks hit it hard). (2) The tool's wrong-page message
  listed the pages that DO have figures **as bare page numbers** — an open
  invitation to grab blind, which the model did (pages 86, 116 missed → it
  took page 60's figure). (3) The success result **didn't echo the caption**,
  so the model never had a chance to notice the mismatch before describing
  the figure as what it wanted it to be.
- **Fix.** `resolve_page_figure`'s miss message now lists candidates **with
  their captions** ("only attach one if its caption matches — otherwise
  explain in prose"); `attach_source_figure`'s success result **echoes the
  attached caption** with describe-only-as-captioned instructions; both
  agents' prompts forbid attaching an unrelated figure as a stand-in.
- **Lesson / guard.** A tool result is the model's only eyes: any affordance
  it lists ("figures exist on pages…") WILL be used, so steering text must
  carry enough information (captions) to be used *correctly* — and every
  attach-style action should echo what was actually attached, because the
  model otherwise fills the gap with what it expected. Guarded by
  `test_resolve_page_figure_miss_lists_candidates_with_captions` and the
  caption-echo text in `agents/library_figures.py`.

### Rule spans that never grew — PyMuPDF's `Rect | Rect` silently ignores empty rects

*Found during the v5.27.0 PDF-figure-mining spike (2026-07-18), in the
booktabs-table extractor.*

- **Symptom.** Caption-anchored table extraction found its seed rule but every
  span came back one-rule tall, so booktabs tables (attention's Tables 1–2,
  PPO's Table 1) all reported "no region" — while the identical logic,
  hand-traced with the same coordinates, was obviously correct. Instrumented
  prints showed the seed found, `same_width` true, `step` in range… and the
  union unchanged after the loop.
- **Root cause.** A hairline rule is a **zero-height rect**, which PyMuPDF
  considers *empty* (`is_empty`: `y0 >= y1` — height-0 qualifies), and
  `Rect.__or__` **ignores empty operands entirely** — `span | rule` returns
  `span` unchanged, no error. Every union in the span-growing loop was a
  silent no-op.
- **Fix.** Build spans from raw coordinates (`min`/`max` over `y0`/`y1`),
  never with `|`, in `services/pdf/floats.py::_rule_span` (and
  `_algorithm_region`, written coordinate-wise from the start).
- **Lesson / guard.** When geometry comes from *drawings*, degenerate rects
  are the norm, not the exception — hairline rules ARE the anatomy of tables
  and algorithm floats, so any PyMuPDF rect-algebra over them must be
  audited for empty-operand semantics (`|`, `&`, `contains` all special-case
  empty). Guarded by the synthetic-PDF tests in
  `test/atlas/services/pdf/test_floats.py` (`draw_line` produces exactly such
  height-0 rects; the booktabs and algorithm tests fail if `|` sneaks back),
  and by comments at both construction sites.

### The citations ingest slowed 3x across a release — and the process itself was the state that grew

*Found on the 2026-07-15 first-full-release ingest (filed as the "O(n²)" Backlog
ticket); root-caused & fixed on the `ingest-append-mode` branch (2026-07-17) —
a branch named for the hypothesis that turned out to be wrong.*

- **Symptom.** Per-shard cost climbed steadily across the 390-shard citations
  ingest: 26.5 s/shard for the first ten, 76.0 for the last (2.9x); ~5.7h total
  against the ~2.2h a single-shard benchmark predicted. Looked like O(n²) in
  shards-done.
- **Root cause.** Two superimposed effects, neither the filed suspect. The filed
  theory — `OVERWRITE_OR_IGNORE` + `FILENAME_PATTERN '<stem>_{i}'` forcing DuckDB
  to re-scan the ~400k accumulated partition files per shard, fixable with
  `APPEND` mode — **benchmarked as false**: a shard-sized write into the *real*
  399,360-file end-of-release tree costs the same as into an empty dir, both
  modes (DuckDB 1.5.4). What the `_done` marker mtimes (a complete per-shard
  timeline the run left behind) plus five benchmarks actually showed:
  **(1)** the sharp step at shard 241 sits exactly on the export-batch boundary —
  batch-2 shards carry **39% more edge rows** (83.1 vs 59.7 MB Parquet out), so
  ~half the "degradation" was just bigger jobs; **(2)** the rest is the
  partitioned write slowing down **per process**: the same COPY repeated in one
  process degraded 3.04x in 8 minutes *with its output deleted every iteration*,
  survived a DuckDB reconnect without a blip (so not connection state), left CPU
  perf counters flat (not thermal) and Defender at 0 CPU (not AV), spared
  single-file COPYs of the identical sorted+zstd payload — and reset to cold
  speed with every fresh process. Fingerprint: allocator/heap wear from cycling
  1024 per-partition writers, ~0.1s added per COPY, matching the real run's
  ~0.08 s/shard slope.
- **Fix.** `ingest.py::_ingest_citations_shards`: shards route through a
  **single-worker `ProcessPoolExecutor` with `max_tasks_per_child =
  _SHARDS_PER_WORKER` (16)** — the child is replaced before wear accumulates,
  holding every shard near cold speed for ~0.3s respawn per cycle. Markers stay
  parent-written after the worker returns (completion is never recorded ahead of
  rows on disk); runs with ≤ one quota pending stay in-process, so the test
  fixtures and a resumed run's tail pay no spawn. A/B through the real
  `ingest_release`: in-process 2.42 → 4.70 s over 20 shards; recycled saws back
  to 2.48 s at shard 17. Guard: `test_ingest.py`'s recycled-worker test pins the
  pool path (markers, rows, layout) with the quota shrunk to 2.
- **Lesson / guard.** v5.6.0's lesson said *benchmark against a populated tree,
  not an empty one* — right instinct, wrong variable: the tree was innocent; the
  **process age** was the state that grew. When a long batch job degrades,
  reconstruct the real timeline first (marker/file mtimes are a free flight
  recorder), then bisect the layers — same tree/fresh tree, same
  connection/fresh connection, same process/fresh process — before trusting any
  named suspect. And a fix that's mechanism-proof (recycle the process) beats
  one that needs the mechanism named: whatever inside the CRT heap is actually
  wearing out, a bounded process lifetime caps it by construction.

*Found & fixed on the `budget-vocabulary` branch (2026-07-16), while re-executing
the notebooks after a vocabulary rename.*

- **Symptom.** None. That's the entry's whole point. `research/cite_budget/analyze.ipynb`
  and `research/latest_gap/analyze.ipynb` both looked fine in git — committed
  outputs, plausible numbers, prose that matched the code. They simply could not
  run. `jupyter nbconvert --execute` died on the first code cell of each with a
  `FileNotFoundError`.
- **Root cause.** Both loaded their corpus from `../../ml_pipelines/<name>/corpus.csv`.
  The **src-layout migration** moved the pipelines to `src/ml_pipelines/`, and the
  notebooks' relative paths were never updated — from `research/<name>/`, `../../`
  is the repo root, so the path resolves to a directory that no longer exists. The
  third notebook (`live_pool_validation`) was written *after* the migration and
  correctly says `../../src/ml_pipelines/...`, which is why the breakage looked
  like a quirk of two files rather than a class of rot.
  **Why nobody noticed:** the gate has five sessions and none of them execute a
  notebook. `precommit` lints notebook *identifiers* (`bin/check_identifiers.py`
  covers `.ipynb`), so notebooks are touched by CI just enough to feel covered
  while their actual correctness — does this still run? do the numbers still hold?
  — is checked by nobody. The committed outputs are indistinguishable from fresh
  ones, so the write-ups silently became historical artifacts of whenever they
  last ran on someone's machine.
- **Fix.** Both paths corrected to `../../src/ml_pipelines/...`
  (`research/cite_budget/analyze.ipynb`, `research/latest_gap/analyze.ipynb`), and
  both notebooks re-executed. Two further staleness bugs surfaced the moment they
  actually ran, having been frozen behind the failure: `cite_budget`'s cap-grid
  discovery used `col.startswith("n_star_k")` against columns that had been
  renamed, and its final cell pointed at `ml_pipelines/models/cite_budget.joblib`,
  a path that hasn't existed for several versions.
- **Lesson / guard.** **A committed notebook output is a claim, and nothing was
  checking it.** The re-executed `cite_budget` notebook now reproduces
  `CV R2 = 0.680`, matching the committed `model.metadata.json`'s
  `cv_r2 = 0.6804741428173474` — that agreement is the real check, and it was
  unavailable while the notebook couldn't run. No automated guard exists yet: a
  nox session that executes the three notebooks would catch this class outright,
  but two of them read committed corpora (cheap, offline) while any future one
  might not, so it needs a moment's design rather than a reflex. **Filed as a
  Backlog item.** Until then, the rule of thumb: if you change a path, a column
  name, or an artifact location, re-execute the notebooks — they will not tell you
  themselves.

### The corpus ingest wrote 3.5 KB Parquet files — one DuckDB default against our 1024 buckets

*Found & fixed on the `corpus-ingest-perf` branch (2026-07-15), while the first full release was ingesting.*

- **Symptom.** The ingest was "really slow" — 2.8 min/shard, ~18h projected for 390
  citations shards, having managed 18. Merely *listing* the output directory timed
  out after five minutes. Nothing looked broken; it was just never going to finish.
- **Root cause.** **`partitioned_write_max_open_files` defaults to 100**, and we
  partition into `NBUCKETS = 1024`. A `PARTITION_BY` spanning more partitions than
  DuckDB can hold open must close and reopen them as it cycles — and a closed
  Parquet file can't be appended to, so **every reopen starts a new file**. One
  shard produced ~21k files averaging **3.5 KB**, nearly all Parquet footer rather
  than data, on course for ~8M files. Sequential throughput was never the
  bottleneck; **file creation** was. Two aggravators: the corpus sat on the box's
  only spinning disk (an SMR 5400-RPM drive, beside two idle NVMe SSDs), where
  every file create is a seek; and `_connect()` pinned `threads=8` /
  `memory_limit='8GB'` while DuckDB would have sized itself to the machine (16 /
  25 GiB) — *below* its defaults, contradicting the function's own docstring ("the
  ingest is the one place we want DuckDB to use the whole box"), and the tighter
  memory made the premature flushing worse.
- **Fix.** Raise the limit past `NBUCKETS` and stop under-provisioning
  (`corpus/ingest.py::_connect`). One shard, measured: **1024 files across 1024
  buckets — exactly 1.0 each, at 61 KB** (was ~21 per bucket at 3.5 KB); 98.2s on
  the HDD (was ~168s) and **20.6s on NVMe**. Since `raw/` is read once
  sequentially — which a spinning disk does fine — while the Parquet absorbs all
  the partitioned writes, a new optional `config.storage.s2_corpus_parquet_dir`
  lets the two halves live on different drives; `paths.release_paths()` wires both
  roots so a hand-built `ReleasePaths` can't silently ignore the split.
- **Lesson / guard.** **A partition count is a contract with your writer, not just
  a read-side choice** — 1024 buckets were picked to make a seed lookup touch
  ~1/1024 of the edge list, and nothing connected that to a write-side default four
  orders of magnitude away. The corpus README now states the coupling: *changing
  `NBUCKETS` must move `partitioned_write_max_open_files` with it*. Second lesson,
  learned when the 2.2h estimate became 5.7h: **benchmark a bulk job against a
  populated tree, not an empty one** — per-shard cost isn't constant when the job's
  own output becomes part of its input state (see the O(n²) backlog ticket).

### Field Landmarks were never landmarks — the relation rode a pager built for something else

*Found & fixed on the `s2-fallback-density-budget` branch (Patrick's browser test, 2026-07-15).*

- **Symptom.** On the s2 provider, DQN's "Field Landmarks" were 2024–2025 LLM-agent
  surveys — the top one a 394-cite paper called *Trust in AI*. Not one of the
  citers anyone would name (AlphaGo, CQL, Decision Transformer) appeared, and the
  whole 1096-node graph crammed into the last two years of a thirteen-year history.
  Easy to read as "the ~10k offset ceiling, nothing to be done".
- **Root cause.** Not the ceiling — the **stop condition**. `_fetch_citers(deep=True)`
  paged only until the rolling 12-month `latest` window was covered, then quit at
  the first page holding no in-window citer. Landmarks were never its goal: v3.1.0
  mined them from *past* the ceiling (`_mined_landmarks`), v3.4.0 added deep paging
  to fill `latest`, and v4.0.0 retired the mining once OpenAlex's sorted `cites:`
  made it redundant. That left `landmark` quietly living off the `latest` pager's
  one-page overshoot — and when v5.0.0 promoted s2 back to a first-class provider,
  nothing replaced the mining. Measured on DQN: page 1 held **exactly one**
  in-window citer, page 2 held none, so paging stopped at offset 2000 with a pool
  covering 2024–2025. The full reachable list runs back to **2019** and holds CQL,
  Decision Transformer and Dota 2 — six-sevenths of it was never fetched.
- **Fix.** Page the whole reachable list, stopping only at the list's end or the
  ceiling (`semantic_scholar/traversal.py`). `latest` is byte-identical (every
  deeper page is older than the window); the landmark pool goes 1999 → 7999. Cold
  builds cost more, scaling with the citer list (measured: QMIX 4 pages / ~8s, DQN
  9 pages / ~15s, against ~3 before). Also corrected **`_MAX_OFFSET` 9000 → 8000**:
  S2 400s `offset=9000&limit=1000` (verified on two seeds) while 8000 serves, so
  the old constant fired one doomed request per deep build — masked because the
  window break almost always tripped first.
- **Lesson / guard.** **When you retire a capability, audit what was quietly
  depending on the scaffolding it leaves behind.** Deleting the mining was right;
  what went unnoticed is that `landmark` had no source of its own afterwards and
  silently inherited a pager optimising for a different relation. The code even
  said so ("fill the latest window + reachable mid band") and read as intentional.
  Guarded by `test_citation_relations_pages_past_the_latest_window`, which pins
  that an out-of-window page no longer stops the walk.

### The cite-budget model was sizing a pool it was never trained on

*Found & fixed on the `s2-fallback-density-budget` branch (2026-07-15).*

- **Symptom.** With `cite_limit: null` (unbounded) the s2 live path still shipped
  exactly 63 landmarks for DQN — and they piled into two years rather than reading
  as a map of the field.
- **Root cause.** `adaptive_cite_limit` predicts the landmark budget from the seed's
  **age + citation count**, and its label was collected over **OpenAlex** pools —
  where a seed's citers are ranked across its *whole* history. It reads DQN's
  age=13 and infers "old classic, landmarks spread over decades, afford ~63". The
  live S2 pool is truncated at the offset ceiling (2019+, not 2013+), so 63 lands
  three times denser than the label ever meant. The features transferred; the
  *label* didn't. `cite_limit: null` was a red herring — with the adaptive toggle on,
  config is only the ceiling the model clamps against, so a `null` can only ever
  raise a cap the model is already far under.
- **Fix.** The live path stops predicting and reads the pool it already holds
  (`budget.select_landmarks`) — the model's own rationale (don't fetch a pool just
  to size a trim) doesn't apply where the pool is in memory. The model still serves
  the ranked paths (OpenAlex, the offline corpus), where its premise holds.
- **Lesson / guard.** **A model's training distribution is part of its contract, and
  identical features don't make two sources interchangeable.** The skew was invisible
  because the inputs were legal and the output was plausible. It surfaced only by
  running the model's own label rule against the served pool: 63 predicted, 29
  admitted. `test_live_s2_fallback_selects_instead_of_predicting` pins which path
  gets which rule.

### Two vertical lines in the Timeline — date-poor papers handed a guaranteed quota

*Found & fixed on the `s2-fallback-density-budget` branch (Patrick's browser test, 2026-07-15).*

- **Symptom.** QMIX's Timeline drew two bare vertical bars of ~12 nodes each: one
  skewered through the seed, one at the graph's right edge (visible with the Latest
  chip off).
- **Root cause.** Two mechanisms, one theme — **papers S2 gave no `publicationDate`**,
  each handed a full `PER_YEAR_CAP` bucket by the new per-year landmark band:
  1. *At the seed.* Citers with **no year** were given their own bucket, then
     `useTimeline`'s `noDateX` parked every one of them on the seed's exact x. The
     placement was a deliberate old decision (S2 not knowing a date isn't evidence a
     paper is old) and reasonable per-node — it just never accounted for *all* of
     them landing on one pixel column.
  2. *At the right edge.* `_is_latest` required a `pub_date`, so a **2026** citer
     without one was filed as a *historic* landmark — nonsense for a months-old
     paper. With no month it pinned to the 2026 gridline, and with Latest hidden
     those 12 stood alone.
  In both cases the band's per-year cap didn't cause the bad data, it **guaranteed
  twelve of it**: the buckets were filled by PDF-extraction stubs ("This paper is
  included in the Proceedings of…") that no citation ranking would otherwise reach.
- **Fix.** `select_landmarks` drops undated citers rather than bucketing them (a
  landmark is "top-cited citer *of year Y*" — a claim a yearless paper can't make);
  `_is_latest` falls back to `year` when there's no date, so a post-cutoff year is
  frontier, not history (the cutoff's own year stays a landmark — ambiguous, and
  misfiling a landmark as frontier is the worse error); `_latest_order` gives the
  sort the same fallback so reveal order matches on-screen order; and Timeline now
  filters undated papers out of the view entirely (`GraphExplorer`'s `nodeOk`),
  `noDateX` deleted. QMIX landmarks 120 → 96 (8 years × 12, no junk).
- **Lesson / guard.** **A rule that guarantees N of something will find N of the
  worst things your data has** — quotas are only as good as the pool's floor. And
  *no date is not an unknown position; it's the absence of a claim* — a time axis
  should decline to place it rather than guess. Guarded by
  `test_undated_citers_are_dropped_not_banded`,
  `test_citation_relations_year_settles_a_dateless_citer_inside_the_window`, and
  `frontend/test/graph/hooks/useTimeline.test.tsx`.

### `bin/setup` left a venv where `import anthropic` failed — two dists, one import package

*Found & fixed on the `s2-fallback-density-budget` branch (2026-07-15).*

- **Symptom.** After a routine session-start `bin/setup.bat`, the **entire backend
  suite failed to collect** — 14 collection errors, all from `import anthropic`
  raising `ModuleNotFoundError: No module named 'docstring_parser'`. Nothing in the
  working tree had touched either package.
- **Root cause.** `1609833` correctly removed **pydoclint** from the project env
  (it pins `docstring-parser-fork`, which collides with the mainline
  `docstring-parser` that `anthropic` requires). But both distributions install the
  **same `docstring_parser/` import package**, so uv's uninstall of the fork
  **deleted the directory the mainline dist owns** — leaving `docstring_parser-0.18.0.dist-info`
  behind with no code beside it. uv therefore believed the package was installed
  and `uv sync` was a no-op: a broken env that reports itself as current.
- **Fix.** `uv sync --reinstall-package docstring-parser`. Only bites machines whose
  env still had the fork when they pull `1609833`; a fresh checkout is unaffected —
  which is exactly why it survived CI and landed on `main`.
- **Lesson / guard.** **Uninstalling one of two distributions that share an import
  package can silently maim the survivor, and `uv sync` won't detect it** — its
  metadata says installed. If an import breaks for a package nothing changed, check
  whether the *directory* still exists before trusting the resolver. The trailhead
  is the pinned comment in `pyproject.toml`'s dev group explaining the collision.

### A running research agent bled its discoveries into the next graph

*Found & fixed on the `provider-aware-agents` branch (Patrick's browser test, 2026-07-13).*

- **Symptom.** Switching providers (or otherwise re-seeding) **while the research
  agent was mid-search** left the agent running in the background; when the new
  graph rendered, its `expand_node`/`search_papers` discoveries streamed into the
  **new** graph's view — papers that had nothing to do with it.
- **Root cause.** The assistant panel (`Teacher`) is keyed on the workspace
  `epoch`, so every graph change remounts it — but `useConversation` had **no
  abort-on-unmount**. The old instance's in-flight `streamAsk` / `streamLecture`
  fetches kept running after unmount (closures persist), and their `onDiscovery`
  callbacks kept dispatching `discoveryMerged` into the store — which now held the
  *new* graph (`loadGraph.fulfilled` had reset `discoveredNodes` to `[]`, so the
  stale finds landed on a clean slate).
- **Fix.** An unmount cleanup in `useConversation` aborts the Q&A controller and
  every lecture controller (`teacher/useConversation.ts`), so a provider switch /
  re-seed / Home / restore stops any running stream. Captures the ref *objects*
  so the cleanup reads their live `.current` at unmount.
- **Lesson / guard.** **A remount does not stop an in-flight async stream** — the
  fetch and its dispatch callbacks outlive the component unless explicitly
  aborted. Any component that streams into shared (Redux) state and remounts on a
  context change needs an abort-on-unmount, or its stale stream mutates the new
  context's state.

### Topic-search nodes never rendered — the view filter silently ate edge-less nodes

*Found & fixed on the `provider-aware-agents` branch (Patrick's browser test, 2026-07-13).*

- **Symptom.** The researcher's `search_papers` clearly ran (trace chips, "N new"),
  but the pink **`search`** nodes never appeared on the canvas — under *either*
  provider. Expand's citation/similar nodes showed fine.
- **Root cause.** GraphExplorer's `view` filter shows a neighbor only when it's
  **`reachable`** — i.e., at least one *enabled edge* touches it (that's how a
  relation chip trims the graph). But an **ungrounded topic-search hit has no edge
  at all** (it floats near the seed — "the link is topical, not verified"), so it
  was never in `reachable` → always filtered out. A latent bug since the filter
  became reachability-based (the per-relation count sliders' retirement); it only
  surfaced now, exercising search heavily.
- **Fix.** Track a `linked` set (nodes with ANY edge) alongside `reachable`
  (`graph/GraphExplorer.tsx`). A node that's genuinely edge-less is shown when its
  own relation is enabled (`search` is always-on); a node hidden merely because
  its relation is off (it has edges, just none enabled) still hides.
- **Lesson / guard.** **Reachability filtering has a blind spot for nodes with no
  edges** — they can't be "reached." Any relation that legitimately produces
  edge-less nodes (topic search here) needs an explicit path in the node filter,
  not just the edge filter.

### `'node'` KeyError ending some OpenAlex-graph chats — a two-shapes search mismatch

*Found & fixed on the `provider-aware-agents` branch (Patrick's browser test, 2026-07-13).*

- **Symptom.** On an **OpenAlex** graph, *some* researcher answers ended with a
  bare red **`'node'`** error after the prose had already streamed — but only
  sometimes (many chats were fine).
- **Root cause.** Two providers, **two search return shapes.** `s2.search_papers`
  returns the traversal shape `[{"node": …}]`; `openalex.search_papers` returns
  **bare** node dicts `[{id, …}]` (the shape the *seed-search* discovery path
  wants). The researcher's `search_papers` tool — and `agents/traversal.search`'s
  contract — expect `[{"node": …}]` and do `hit["node"]`, so under OpenAlex that
  raised `KeyError('node')`. The orchestrator caught it and surfaced
  `str(exc)` = `"'node'"`. It was **rare because it only fired when the model
  chose the `search_papers` tool** (read/expand-only answers never hit it). Same
  bug hid the pink **`search` relation** — the tool crashed before adding any of
  its search-tagged nodes, so an OpenAlex graph only ever showed expand's
  citation/similar finds.
- **Fix.** Wrap OpenAlex's bare nodes into `[{"node": …}]` at the agent boundary
  (`agents/traversal.search`), honoring the function's documented shape for both
  providers. (A test fake had *masked* this by returning the wrapped shape; it now
  mirrors the real bare-node return.)
- **Lesson / guard.** **When two backends fill one interface, pin the shared
  return *shape* in a test, and make fakes mirror the real contract — not a
  convenient stand-in.** The fake that returned `{"node": …}` for a function that
  really returns bare dicts is why the seam passed CI but failed live.

### OpenAlex detail hydration nulled out a known arXiv id — arXiv tags vanished

*Found & fixed on the `provider-reach` branch (Patrick's browser test, 2026-07-13).*

- **Symptom.** Under the **OpenAlex** provider, a paper's detail panel showed its
  **OpenAlex tags** but not its **arXiv tags** — even for papers plainly on arXiv
  (e.g. Prioritized Experience Replay, `1511.05952`, whose arXiv id OpenAlex
  *does* expose). The arXiv-tags section just never appeared.
- **Root cause.** The arXiv category tags are fetched by the node's `arxiv_id`.
  `openalex.node()` *always* emits an `arxiv_id` key — a value **or `null`**.
  Clicking a node hydrates its detail from the **exact** OpenAlex record (by DOI);
  for a paper whose canonical OA record is the *published* version, that record
  carries **no arXiv location**, so hydration returns `arxiv_id: null`. The
  detail-panel merge `{...node, ...details}` then let that present-but-null key
  **overwrite** the `arxiv_id` the graph build had already extracted (from the
  neighbor traversal's `locations`) → `selected.arxiv_id` went null → the tags
  fetch was skipped. So we *had* the id and threw it away.
- **Fix.** The merge now coalesces: `arxiv_id: detail.arxiv_id ?? node.arxiv_id`
  (`detail/useSelection.ts`), preserving a known id when hydration doesn't supply
  one. arXiv tags now show whenever OpenAlex exposes the id at build time.
- **Lesson / guard.** **A spread-merge of a partial record is dangerous when the
  patch emits keys with `null` values** — `{...a, ...b}` lets `b`'s explicit
  `null` clobber `a`'s good value, unlike an "only fill what's missing" merge.
  When a normalizer always includes a field (even as null), coalesce the ones
  that shouldn't regress. (The genuine OA gap remains: a published-only record
  with no arXiv location has no id to show — that's data, not this bug.)

### Alt+Shift+drag never added to the node selection (Windows)

*Found & fixed on the `node-selector` branch (2026-07-12).*

- **Symptom.** The node selector's other gestures worked — alt-drag picked a
  cluster, shift-click toggled one, alt-click cleared — but the **Alt+Shift+drag
  "add this rectangle to the pick"** gesture did nothing (or panned/replaced
  instead). Only that one modifier combo was dead, and only on Windows.
- **Root cause.** **Alt+Shift is the OS keyboard-layout switch on Windows.** The
  moment both were held, Windows grabbed the combo: the browser never saw a
  clean `event.shiftKey` mid-drag, and the layout-switch focus change fired a
  window `blur` — which our `useMarquee` used to **disarm** the capture overlay,
  so the mousedown fell through to react-force-graph and panned instead of
  marqueeing. Nothing wrong with the code's logic (the reducer + a jsdom test of
  the shift branch both passed) — the gesture was simply un-triggerable on the
  target OS.
- **Fix.** Dropped the "replace vs. add" modifier split entirely and made the
  marquee **additive**: every alt-drag unions its rectangle onto the pick (reset
  is alt-click empty / Clear). No second modifier, so no OS collision. The
  `shiftKey` branch and its test are gone; a new test drives two sweeps and
  asserts they accumulate.
- **Lesson / guard.** **Don't build gestures on OS-reserved modifier combos** —
  Alt+Shift (layout switch) and Ctrl+Alt (AltGr on international keyboards) are
  claimed by the platform before the browser sees them, and a passing unit test
  proves nothing about whether a human can actually *fire* the gesture.
  Single-modifier drags (Alt alone here) are safe; anything richer needs an
  in-app affordance (a mode toggle, a button), not a chord.

### "Event loop is closed" when several lectures stream at once

*Found & fixed on the `color-lecture-buttons` branch (2026-07-11).*

- **Symptom.** Playing all four lectures at once (each button clicked before the
  last finished) surfaced a red **`Event loop is closed`** error in the assistant
  panel. The lectures still played — the error was cosmetic — but it looked
  broken. It only ever appeared under **concurrency**; a single lecture at a time
  never triggered it.
- **Root cause.** The agents, and the one **shared Anthropic `AsyncClient`** they
  hold, are module-level singletons — but `agents/streams.py::drive` opened a
  **fresh `asyncio` event loop per call and closed it at the end**. Fine
  sequentially. But Flask is threaded, so concurrent lectures each ran `drive` on
  their **own** loop over that **one shared httpx connection pool** — and a pool
  binds to the first loop that touches it. The first stream to finish closed
  *its* loop, tearing the pool out from under the streams still running on it →
  `Event loop is closed`.
- **Fix.** `streams.py` now runs all agent async work on **one long-lived event
  loop** (a daemon thread; request threads reach it via
  `asyncio.run_coroutine_threadsafe`). The shared client stays bound to a single
  loop for the process's life, and asyncio multiplexes the concurrent streams the
  way it's meant to. `drive`'s external contract — a sync generator yielding one
  event at a time, context manager always exited — is unchanged, so the lecturer
  and researcher both benefit with no caller edits.
- **Lesson / guard.** A shared async client and a per-call event loop are
  incompatible the moment anything runs concurrently — the loop a pooled
  connection was born on must outlive every stream using it. New test
  `test/atlas/agents/test_streams.py` drives **8 streams concurrently** and
  asserts they all complete cleanly (the prior suite only ever drove one at a
  time, so it couldn't have caught this).

### The same paper as two (actually three) nodes — cross-source identity in the hybrid graph

*Found & fixed in v4.5.1 (2026-07-10).*

- **Symptom.** Seeding on DQN showed "Continuous control with deep reinforcement
  learning" as **two** node instances, each with a partial view of the paper
  (different rels, wildly different citation counts). An audit of the four
  cached graphs found 24/11/43/30 duplicate-title groups — the graph had been
  quietly double-counting papers since the v4.0.0 hybrid.
- **Root cause.** The node table was keyed by raw id, but the hybrid ships
  **two id schemes**: S2 relations (references, similar) carry bare paperIds
  while OpenAlex citers carry `DOI:`/`ARXIV:`/`W…` ids. The "duplicate" was
  actually **three** sightings — an OpenAlex `ARXIV:` citer, an OpenAlex `DOI:`
  citer from a *duplicate OpenAlex work* (verified live: two QMIX works share
  one DOI), and an S2-paperId similar hit — each minting its own node.
- **Fix.** `build.py::add_neighbor` resolves identity through the **arXiv id**,
  the one id both sources agree on: first sighting wins the node slot, later
  sightings append their rels and upgrade fields they know better
  (`_upgrade_node`: max `citation_count` — S2's counts are far more complete —
  fill-if-None for summary/date fields). `add_neighbor` returns the canonical
  id and the edge loops use it; `add_edge` skips self-loops and duplicate
  `(source, target, type)` triples with ranks staying compact; `counts` are
  post-dedupe. The seed registers its own arXiv id, so a citer that IS the seed
  under another id merges instead of self-looping. Two pinned tests.
- **Lesson / guard.** A graph fed by two sources needs an explicit **identity
  key**, not "whatever id arrived". The known residual is deliberate: a
  journal-DOI record vs. its preprint twin where neither side carries the arXiv
  id can't merge — title matching was rejected as riskier than the rare leftover
  duplicate (same-title distinct papers exist, e.g. Living Reviews editions).

## Upstream — their bug, our problem

Root cause outside our code: a provider's data or service. We can't fix these,
only work around them — so the entry exists to explain why some piece of our code
looks paranoid, and to stop a later cleanup from quietly removing the guard.
**Fix** here means *our* workaround, not a repair; **Lesson / guard** is what keeps
us honest when their data changes again.

### Semantic Scholar ships every citation edge twice — a release is two overlapping export batches

*Found on the `corpus-dedupe` branch (2026-07-16), an hour after the first full corpus went live.*

- **Symptom.** With the corpus finally serving, DQN's Field Landmarks came back
  **citation-sorted across all history and visibly right** — DDPG, Soft Actor-Critic,
  A3C, TRPO, Rainbow — but only **32 of them**, against an adaptive budget of 63. The
  relation was half-empty with no error anywhere, and the papers it *did* show were
  the correct ones, which is precisely why it looked fine.
- **Root cause.** **S2's own data.** A release's `citations` dataset is published as
  more than one export batch, and the batches **overlap**. The `2026-07-07` release
  advertises 390 shards — 240 stamped `…_00151_3g69z_…` and 150 stamped
  `…_00016_bxc9g_…` — and our download pulled exactly what their API listed. Together
  they carry **5,112,091,751 rows for ~2.7B distinct edges**: every edge lands about
  twice (DQN: 27,230 rows, 13,729 distinct — 1.98x). So a `LIMIT 63` in
  `landmark_citers` counted **rows, not papers**, and bought ~32 real landmarks.
  Two things hid it: `build.py`'s `add_edge` dedupes endpoints, so the *graph* stayed
  correct — just half-empty; and S2's own `citationCount` for DQN says 13,824, which
  matches the *distinct* count, so the API and the bulk dataset quietly disagree by 2x.
- **Fix (workaround).** `source._citers` groups by `citingcorpusid` **before** the
  join and the limit, so a limit counts distinct citing papers;
  `bool_or(isinfluential)` merges the copies, which matters because **the batches
  disagree** — an edge is influential in one and not the other. Deduping at *ingest*
  is impossible: a duplicate pair spans two different shards, and each shard is
  written independently, so a per-shard `DISTINCT` never sees both copies. Ingest
  therefore stores upstream's rows verbatim and the query collapses them.
- **Lesson / guard.** **A bulk dataset is not a set — don't assume a vendor's export
  is deduplicated, and don't trust the row count as an entity count.** The tell was
  arithmetic, not an error: 27,230 ≈ 2 × 13,824, and 63 → 32. Any `LIMIT` over
  un-deduped edges silently spends the budget on duplicates. The synthetic fixture now
  **ships a second, overlapping batch that disagrees on `isinfluential`**, exactly as
  S2 does, so the ordinary landmark assertions fail if the dedupe is ever removed —
  the guard is in the *data*, not just a test name. Expect this every release; if a
  future one stops duplicating, the grouping is still correct and costs nothing.

### OpenAlex couldn't find "Attention Is All You Need" — a hard seed-resolve failure

*Found & fixed on the `provider-reach` branch (Patrick's browser test, 2026-07-13).*

- **Symptom.** With the **OpenAlex** provider selected, re-seeding (or loading)
  the transformer paper by its arXiv id failed outright — a red **"No paper found
  on OpenAlex for 1706.03762"** — even though the paper is obviously in OpenAlex
  (it's the top hit for a title search). Other papers resolved fine.
- **Root cause.** `openalex.resolve_seed_work` resolves a bare arXiv id
  cheapest-first through the **arXiv-minted DOI** (`doi:10.48550/arXiv.<id>`).
  For a famous *published* paper, OpenAlex's canonical record is the published
  version and is **not aliased to the arXiv-minted DOI** — that DOI simply 404s
  in OpenAlex. The resolver then tried a title search *fallback* but had **no
  title** (it's only given the id), so `_clean_search("")` bailed and the whole
  resolve returned `None` → the route's 404. The v4.x hybrid never hit this
  because S2 resolved the seed; the v5.0.0 provider split unmasked it, and it was
  a *hard failure*, not just the documented "lands on the lower-cited preprint
  stub."
- **Fix.** When the arXiv-DOI path misses, fetch the paper's **title from arXiv**
  (`arxiv.get_title`, a new lookup sharing `categories.py`'s export-API fetch) and
  title-search OpenAlex — which lands the canonical, most-cited record.
  `integrations/openalex` already depends on `integrations/arxiv` (for
  `extract_id`), so the direction is clean. Verified live: 1706.03762 now
  resolves.
- **Lesson / guard.** A "cheapest-first, fall back to title" resolver is only as
  good as its fallback's *inputs* — the title fallback existed but was reachable
  only when a title was already in hand. When you drop a masking layer (the S2
  seed resolve), re-check that every downstream fallback still has what it needs.
  (Separately: the resolved OpenAlex record still carries OA's known ML-undercount
  and the 2025-misdate — a *data* tradeoff, documented in
  `docs/citation-coverage.md`, not this bug.)

### OpenAlex misdates "Attention Is All You Need" to 2025 — nearly broke the cite-budget model

*Found & handled during the v4.5.0 adaptive-budget build (2026-07-10).*

- **Symptom.** While fitting the landmark-budget model (`ml_pipelines/cite_budget`),
  a **sqrt-age** variant that scored *better* on cross-validation (CV R² 0.73 vs
  0.68) predicted a budget of **~2 landmarks** for "Attention Is All You Need" —
  absurd for one of the most-cited ML papers.
- **Root cause.** OpenAlex's canonical record for that paper reports
  `publication_year: 2025` (it resolves to a low-citation duplicate work,
  `W2626778328`, not the 2017 original), so the model saw **age ≈ 1**. The
  sqrt-age transform is steep near zero, so a wrong age of 1 collapsed the
  prediction; plain-age is linear and far more forgiving there (~30, the right
  ballpark).
- **Fix.** Chose the **plain-age linear model** over the higher-CV sqrt variant
  precisely *because* it survives this dating noise (documented in
  `ml_pipelines/cite_budget/train.py` and the notebook). `compute_features` also
  floors age at 0 so a future-dated seed can't go negative. A test pins the
  misdated anchor (`year=2025 → 30`) so a future "improvement" that reintroduces
  the fragility fails loudly.
- **Lesson / guard.** OpenAlex publication years are **not trustworthy** for
  individual works — anything age-based (this model, and the queued
  landmark→latest date-distribution work) must degrade gracefully on a wildly
  wrong year, and CV score alone can hide a catastrophic failure on a single
  important point. Always eyeball the anchors, not just the aggregate metric.

### OpenAlex's coarse dates emptied the "Latest Publications" relation

*Found & fixed during the v4.0.0 OpenAlex hybrid build (2026-07-09).*

- **Symptom.** For the DQN seed, the graph showed **1** "Latest Publications"
  node — obviously wrong for a paper with hundreds of recent citers.
- **Root cause.** The latest relation used a rolling 12-month **date** window
  (`from_publication_date:<today − 12mo>`), ported from the S2 path. But OpenAlex
  dating is **coarse**: a large fraction of works carry a *year-only*
  `publication_date` that OpenAlex defaults to `<year>-01-01`. So a paper
  "published in 2025" is stamped `2025-01-01` and falls *outside* a window that
  starts mid-2025 — the filter silently excluded almost every recent-year citer.
  Confirmed live: DQN had **1** citer via `from_publication_date:2025-07-09`
  but **30** in `publication_year:2025` (6 of them dated exactly `2025-01-01`).
- **Fix.** Split landmark/latest by **publication year**, not an exact date:
  `latest` filters from `<first latest year>-01-01`, robust to the Jan-1 default
  (`integrations/openalex/traversal.py`, `citation_relations`). DQN latest: 1 → 30.
- **Lesson / guard.** Don't assume cross-source date precision. OpenAlex trades
  exact dates for coverage; any *date*-range filter against it must be
  year-granular (or tolerate `-01-01`) or it quietly drops year-only records.
  Pinned by `test_latest_uses_year_window_not_exact_date`.

### Tripled MathML soup in ar5iv figure captions

*Found & fixed v3.2.0 (2026-07-08), while shipping "Proper subscripts & math
notation".*

- **Symptom.** Figure captions in the detail panel and in the teacher's
  answers rendered as garbled, tripled math — e.g. the Double Q-Learning paper
  (arXiv 1509.06461) showed
  `…the action values are Q(s,a)=V*(s)+eaQsasubscriptVssubscriptitalic-ϵaQ(s,a)=V_{*}(s)+\epsilon_{a} and the errors…`.
  The new frontend KaTeX renderer couldn't help — the caption *string itself*
  was already corrupt, and the LaTeX in it wasn't even `$`-delimited.
- **Root cause.** ar5iv renders each formula as a `<math>` element whose
  children are **three redundant text renderings** of the same formula:
  presentation MathML (`<mi>`, `<msub>`…), a content-MathML / semantic
  annotation (the source of the literal words `subscript`, `superscript`,
  `italic-ϵ`), and a LaTeX annotation. `_FigureParser` in
  `src/atlas/integrations/arxiv/figures.py` stripped tags and accumulated **all
  of it**, concatenating the three into soup. The clean LaTeX was sitting
  unused in each element's `alttext` attribute the whole time.
- **Fix.** `_FigureParser` now tracks `<math>` nesting: on entering the
  outermost `<math>` inside a caption it emits the element's `alttext` wrapped
  in `$…$`, and suppresses the subtree's own text nodes. Captions come out as
  clean, KaTeX-ready `$V_{*}(s)+\epsilon_{a}$`. Covers every figure surface at
  once (detail panel, teacher `FigCard`, lightbox) because they all fetch
  through `get_figures`.
- **Lesson / guard.** When scraping rendered LaTeX (ar5iv/MathJax/KaTeX
  output), prefer the source-carrying attribute (`alttext`, `data-tex`,
  `<annotation encoding="application/x-tex">`) over the visual subtree — the
  subtree is *display* markup, often duplicated for accessibility, and
  text-stripping it is lossy. Two regression tests pin this
  (`test_get_figures_math_becomes_delimited_latex_not_tripled_mathml`,
  `…math_without_alttext_is_dropped_not_garbled`). Note the 30-day figure cache:
  a parser fix doesn't reach already-cached captions until they re-fetch —
  clear `figures:*` from the `cache` table to re-test immediately.
