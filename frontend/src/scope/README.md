# `src/scope`

Which papers a turn is about. One resolver, one priority list, shared by the
lecturer and the researcher:

1. what the **message** asked for — "the references", "the seed", named
   papers, a period;
2. else the reader's **hand-picked selection** on the canvas;
3. else what is **visible** — the papers passing the view filters.

```
scope/
  resolve.ts   — resolveScope (the list, applied), requestsScope, routePapers
                 (the thin list the name resolver is shown), filtersForTurn
                 (the turn's period folded into the researcher's discovery
                 filters), emptyScopeMessage and describeScope (the words for
                 an empty scope and for the transcript's "Scoped to …" line)
```

## Why it exists

Until v7.24.0 that order was real but nowhere: it was the emergent behaviour
of `useConversation.send` (message scope), the workspace's `scopedNodes`
(selection ∩ visible, else visible) and the view filter that fed it. Patrick
worried the scoping features "could overlap in destructive and unintended
ways", and reading the three together they did, twice: a message scope
*replaced* the hand-picked selection and released it to nothing, and the
filters silently beat the selection — a selected paper a later slider change
hid dropped out of scope with no signal. A third gap: only lectures got
message scoping; a question ignored the router's `scope`.

Codex's design review (2026-09-15) tightened the fix into four rules, and
this folder is where they live:

- **Message scope becomes the selection for the turn, and the turn's end
  clears it.** `send` dispatches `nodeSelectionSet` with the resolved papers,
  so they ring and draw past the filters for as long as the agent works —
  the rings are how the reader sees which papers the request was about —
  and when the answer lands (`ask`'s and `lectureInChat`'s endings, on the
  thread on screen) the selection is cleared to **nothing**
  (`nodeSelectionCleared`), whoever set it, while the papers the answer
  cited or the lecture narrated stay lit. Two decisions of Patrick's, a
  fortnight apart, shape this. The review (2026-09-15) proposed an override
  layer released at the turn's end *exposing the prior selection*, and he
  overruled it: *"it should change permanently and not revert back to the
  user's manual scope."* Then, on the v7.27.0 browser round (2026-09-17):
  *"It should only scope at the beginning … to show the user what nodes are
  in scope for this request. By the end of the agent's response, the scoping
  (blue rings) should go away and reset to nothing."* Clearing is not
  reverting, so both hold. One consequence worth knowing: there is still no
  separate scope state — the selection *is* the scope, whoever set it, Esc
  clears it either way, and a hand-picked selection is consumed by the turn
  it grounds: ask a follow-up about the same papers and they are the visible
  default again, unless re-picked or named. A mid-turn edit by hand simply
  edits it, and is cleared with the rest.
- **Absent ≠ empty.** A request that asks for something and matches nothing
  comes back as `{ source: 'message', nodes: [] }` — the **empty-scope
  signal** — and the caller fails the turn in words. It never falls through
  to the selection or the visible papers: an explicit scope that matches
  nothing must not quietly become "everything".
- **Eligibility is not rendering.** "Visible" means *passes the view
  filters*, independent of the viewport, a collapsed panel, and what else the
  canvas draws. The canvas also draws scoped papers the filters would hide
  (marked with a dotted ring, named in the legend), but `GraphExplorer`
  publishes the *eligible* set, not the drawn one — otherwise a paper shown
  only because it was asked for would leak into the default scope of the
  next, unscoped question.
- **Resolve once per turn.** `send` resolves, stamps the result on the turn
  (`ChatMsg.scope`: source, request, count), and hands the same snapshot to
  whichever agent answers. The canvas republishes its visible set on its
  *next* render, and the papers a turn is about must not change under it. A
  correction or retry re-resolves the *stamped request* against the graph as
  it stands then, rather than reusing the node list.

## Design decisions worth knowing

- **Visible is the default, not the whole graph.** Filters are how a reader
  establishes context; defaulting to everything would weaken that control.
  "The whole graph" is an explicit scope a message asks for by name — the
  `graph` kind ("lecture me on the whole graph", "everything on the map"),
  everything the workspace holds, past every filter — which is what lets
  the default stay narrow: the lot is one sentence away, not a filter-reset
  away. "Everything" alone stays deictic (what is on screen).
- **The turn's period binds discovery too.** `filtersForTurn` folds a
  message's period into the researcher's search filters — the same
  `year_from`/`year_to` wire fields the ▽ filters use, the stricter side of
  each — so "what did the citations from the last three years find?" does
  not ground in the right papers and then pull in a 2015 discovery. Discovery
  only, like the ▽ filters themselves: `expand_node` walks citations somebody
  actually wrote, and filtering a reference list by year would hide real
  edges (`ResearcherDeps` in the researcher's `tools.py` has the reasoning).
- **A message kind reads off the whole graph; a bare period narrows the
  context.** "The references" with the references chip off means the
  references — that is what the message is for. "The papers between 2016
  and 2017" names no set, so an ambiguous ask preserves the context the
  reader already has (selection, else visible) and narrows it; a year the
  sliders exclude is reported as empty, with the hint to widen the filter or
  say which papers. The v7.23.0 version reached past the sliders for a bare
  period; that was reversed here for consistency with the rule above.
- **`references` / `citations` are the node's own tag** — the colour the
  paper wears and the set its chip toggles — so the word means the same said
  as clicked. A satellite's references count, per the v7.17.0 rule that what
  the reader put on the graph is fair to narrate.
- **Discoveries are papers.** They stay in the workspace whatever the
  filters do, and are in scope on exactly the same terms as any other paper
  — eligible, selected, or named. The researcher used to keep every
  discovery regardless; under one contract that special case went.
- **No undated paper satisfies a period.** Placing it in one would be a claim
  we cannot make — the same reason Timeline hides undated papers.

## Who uses it

`teacher/useConversation.ts` (`send`, `reroute`, `retryAnswer` — the
per-turn resolution and the empty-scope failure), `store/workspace.ts`
(`selectScope`, the default for the panel's readouts and for callers that
skip routing), and `teacher/transcript/ChatMessage.tsx` (`describeScope`,
the "Scoped to …" line).

## How it's verified

`test/scope/resolve.test.ts` pins the list rung by rung, the empty-scope
signal (with a selection present, to prove it does not fall through), the
period rules, the words. `test/teacher/useConversation.test.tsx` runs the
real hook through the acceptance list: a message scope becoming the
selection and staying (with a mid-turn edit kept), a selection surviving a
filter change, a zero-match scope for either agent leaving the selection as
it was, a bare period narrowing the context, the scope kept on failure so a
retry asks over the same set, and a correction re-asking for the same
papers. `test/store/workspace.test.ts` covers the default selector.
