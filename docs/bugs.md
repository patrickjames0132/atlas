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
