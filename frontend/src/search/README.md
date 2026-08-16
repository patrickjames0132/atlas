# `src/search`

Finding a seed paper — **from the chat bar**, since v7.6.0. This folder no
longer owns a search *surface*; it owns the two small controls that arm a
search and the shaping that turns a scout result into a transcript turn.

```
search/
  SearchControls.tsx — the chat bar's two toggles: "Find papers" + "Filters"
                       (with the year/field popover behind the second)
  useDirectSearch.ts — run the scout, shape its result into a chat message
  search.css         — styles for the toggles and the filter popover
```

## What changed in v7.6.0, and why

The app used to have **two** text inputs: a search box in the header and the
chat bar in the assistant panel. They asked the same question — "find me
papers about this" — and made you pick a box before you knew which one you
wanted. The header box is gone; the chat bar does both, with a toggle
choosing what the words you typed *are*.

The backend consolidated the same way. There used to be two implementations
of "search papers" — `services/search.live_search` (query-analyst expansion,
verified titles, one lexical search) and the paper scout. Now there is one:
the scout, run without the researcher above it. That is the same principle
the v7.0.0 worker split was made on — *two paths to one source is the bug,
not the feature* — applied one level up. `query_analyst` was retired with it;
its title-recall half became the scout's `match_title` tool.

## Design decisions worth knowing

- **Three destinations, decided before any model runs.** `Teacher`'s submit
  handler branches on plain facts, not on an agent classifying your intent:
  a pasted arXiv id/URL goes straight to the graph (`ID_RE`, no LLM at all);
  "Find papers" armed goes to the scout; otherwise the researcher. The id
  check deliberately runs *first* — you pasted the paper, so there is nothing
  left to search for, whichever toggle happens to be on.
- **The filters bind, and they sit outside the toggle.** `year_from` /
  `year_to` / `fields` ride in the scout's **deps**, not its prompt, so no
  wording the model picks can widen them (it may narrow further inside them —
  see `agents/workers/search/papers`). They apply to the researcher's paper
  searches too, which is why they are the *bar's* filters rather than direct
  search's: a reader who narrows to 2020+ compsci means it either way. What
  they never touch is `expand_node` — filtering a reference list by year
  wouldn't narrow a search, it would hide real citations and leave the graph
  lying about what cites what.
- **A result is an ordinary assistant turn, streamed the ordinary way.**
  `useDirectSearch` has **no reducer of its own** — it drives `turnStarted` →
  `traceAdded` → `tokenAppended` → `paperRefsSet`, the same four a streamed
  answer walks. So the turn appears the instant you hit send, the transcript
  snaps to the bottom, and `AnswerMarkdown` renders the `[n]` markers against
  `paperRefs` with a click reseeding the graph — all without a line of bespoke
  rendering. A saved session carries direct searches for free, since
  `paperRefs` and `trace` already persist. (The first build landed the
  finished result in one dispatch; a search read as a frozen screen for the
  several seconds it took.)
- **`/api/search` is an SSE stream**, so the scout's lookups arrive as chips
  **while it works** rather than all at once at the end. Each is announced
  when the lookup *starts*, not when it returns — a chip that appears on
  completion reports what already happened; one that appears on issue says
  what is happening now. They are also the whole debugging surface for a thin
  result: one query behind three papers reads very differently from four.
- **The summary leads the list.** A negative result ("nothing indexed after
  2021") is a real finding, and it explains a short list rather than leaving
  the reader wondering.
- **Direct search's brief lives at the call site, not in the shared prompt.**
  The scout is told to stop as soon as it has what was asked for — right when
  a researcher is waiting, wrong when a *reader* is. The first build of this
  returned exactly one paper for "dqn": correct, and useless, because there
  was nothing to choose between. `routes/search.py`'s `_PICKER_BRIEF` asks for
  a spread instead. Same worker, different consumer.
- **The year slider spans the whole corpus (1800 → now), by Patrick's
  call** — full access beats track precision. The fold-to-null trick makes
  that free: a handle parked at an endpoint reads as "no bound", so the
  default full-width slider IS the empty filter (and doesn't light the
  active-filter badge). Two overlapping `<input type=range>` elements share
  one track; the low handle z-indexes on top at the far right so it stays
  grabbable.
- **The field picker lazy-loads and follows the provider.** The selected
  provider's field vocabulary (`getFields(provider)` → `/api/taxonomy/<provider>`
  → `{id, name}[]`) fetches only when the popover first opens; the options are
  refetched when the provider changes. The picker shows `name` and stores the
  `id` as the filter value (S2 field name / OpenAlex numeric field id). The
  two vocabularies are disjoint, so the backend drops values that don't belong
  to the active provider (`services/search.valid_fields`).
- **The popover spans the whole bar and drops down from it.** It anchors to
  `.teacher-ask`, not to the little toggle that opens it — a popover the width
  of a button has no room for a year slider.
- **The instant cache search is gone from the frontend — not from the
  product.** `searchLocal` and `/api/local_search` were deleted, because the
  scout reads that same cache *inside* its own `search` tool: a rate-limited
  provider still answers from graphs you have already loaded. What was
  actually lost is time-to-first-paint (cached hits used to render while the
  live search was in flight). That was judged the cheaper half of "one path to
  one source"; restoring an instant tier is a small change if it ever feels
  slow.

## Who uses it, and how/why

`Teacher` renders `SearchControls` inside its ask form (beside `ScopePicker`,
for the same reason: they belong to the thing you are about to send) and owns
the `direct` / `searchOptions` state. It passes the options to
`useDirectSearch` **and** to `ask`, which forwards them to the researcher.
`AtlasHeader` no longer imports anything from here.

## How it's verified

`tsc -b` strict + oxlint + prettier. The reducer sequence is pinned in
`test/store/transcript.test.ts` ("direct search reuses the streamed-answer
reducers"); the binding filters are pinned server-side, where they are
actually enforced (`test/atlas/agents/workers/search/papers/test_main.py`),
along with the route's SSE frames (`test/atlas/routes/test_search.py`).
