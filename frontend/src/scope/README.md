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
                 (the thin list the name resolver is shown), emptyScopeMessage
                 and describeScope (the words for an empty scope and for the
                 transcript's "Scoped to …" line)
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

- **Message scope becomes the selection — and stays.** `send` dispatches
  `nodeSelectionSet` with the resolved papers, so they ring, draw past the
  filters, and remain the scope after the turn, exactly as if the reader had
  marqueed them. This is Patrick's call over the review's alternative (an
  override layer released at the turn's end, exposing the prior selection):
  *"if the scope changes for a user's request, it should change permanently
  and not revert back to the user's manual scope."* One consequence worth
  knowing: there is no separate scope state at all — the selection *is* the
  scope, whoever set it, and Esc clears it either way. A mid-turn edit by
  hand simply edits it.
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
  "The whole graph" is meant to be an explicit scope a message can ask for
  (`graph`, planned with the researcher's tool constraints).
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
