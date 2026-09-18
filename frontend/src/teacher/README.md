# `src/teacher`

One composer serves General and graph threads. General is graphless: searches,
broad questions and comparisons can live there. A graph thread's composer names
its subject and scoped paper count. Questions and lectures belong to the active
thread; opening another graph switches to its discussion rather than carrying
this transcript onto a different canvas.

## Sending and streaming

`Teacher.tsx` owns input, menus, scope controls, scroll behavior and transcript
rendering. `useConversation.ts` asks the router whether the message wants the
researcher or lecturer; graphless conversations bypass that choice. The routing
label lets readers correct a model-selected destination. Lectures are ordinary
chat replies with beats, including real figures and citations. (A `/lecture`
command was the explicit path from v7.21.0 to v7.23.0; asking in words
replaced it once the router could read everything the command said, and more.)

**Which papers a turn is about is one rule, shared by both agents**
(v7.24.0, `scope/README.md` has the full story): what the message asked
for, else the hand-picked selection, else what passes the view filters.
`send` resolves it **once**, with the router's `scope`/period in play — "the
references", "the seed", named papers (one more call, `resolveRoutedPapers`,
with titles/authors/years only), "between 2016 and 2017" — and hands the
same `ResolvedScope` to `ask` or `lectureInChat`, which stamp it on the turn
(`ChatMsg.scope`, shown as *"Scoped to the references, 2010–2019 · 12
papers"*) and never read the store for it again. A message scope **becomes
the selection** (`nodeSelectionSet`: ringed, drawn even where a filter would
hide it) and stays after the turn, like a pick made by hand — Patrick's
call: a request that changes the scope changes it, it does not borrow it. A
message scope that matches nothing **fails the turn in words** for either
agent, never falling through to the next rung, and leaves the selection as
it was. A correction (`reroute`) or a retry re-resolves the turn's *stamped
request* against the graph as it stands now, sets the selection again, and
re-asks. Callers that skip routing (graph-free asks) take `selectScope`, the
default.

Every lecture ends with all of its beats' papers lit and its bubble active —
the same state as clicking the bubble — rather than the last beat alone,
which read as the lecture pointing at its ending rather than at what it
covered.

Bare paper mentions and pasted paper ids open graph threads. Paper mentions
inside questions attach those papers without changing the graph. The same `@`
dropdown lists this exploration's other discussions above the paper results;
choosing one inserts `@thread[Title]`, which `readMessage` keeps away from the
paper scout so a bare thread mention can never launch a literature search.
Nothing in the dropdown is pre-selected: Enter on an untouched list sends the
message as typed (a bare `@phrase` to the scout); Enter on a chosen paper that
is the whole message opens it in one press (Tab only completes the text); a
paper inside a sentence or a thread completes and waits for the question. The
composer feeds its resolved-mention keys back into the dropdown so a picked
title ends its mention rather than the question after it becoming the query.
See `../mentions/README.md`.

`useConversation.ts` captures the conversation key when a run starts. Background
tokens and beats land there, and discoveries are held for that thread if it is
not visible. Highlight and error effects consult the current store before
changing the screen. Controllers are retained by thread so returning to a running
discussion can stop it. A successful terminal response marks the turn complete;
aborted or failed partial prose remains visible but never enters model history.

## History and cross-thread knowledge

`history.ts` supplies one conversion for normal sends, retries and borrowed
history. A lecture's heading and beat prose become the assistant's content even
though its `text` field is empty. Failed and unfinished exchanges are excluded,
and `<<FIG n>>` placement markers are stripped. Every research request carries
client history; the backend no longer maintains endpoint-specific copies.

Each request also carries a sibling index: titles and summaries from this
exploration only. Explicit `@thread[Title]` references attach that discussion's completed
history. The server bounds sibling count, summary length, history turns and total
borrowed text; it labels the result as quoted background with independent paper
numbering. Replies show a `Context from` line linking to explicitly attached
threads. Borrowing a discussion never silently swaps the canvas.

## Scopes and citations

Source exclusions remain panel-local; the uploaded-source list is shared Redux
state. `scope/resolve.ts` owns paper scope, for lectures and answers alike; a
discovery is in scope on the same terms as any other paper (eligible,
selected or named — no longer kept regardless for the researcher). Scope
changes do not invalidate earlier answers; each turn keeps its own stamp.

Paper citations highlight their node on the current graph, toggling off on a
second click. Graph icons on search references open or resume that paper's
provider-specific graph thread directly. There is no intermediate paper modal.
Whole-answer and beat clicks highlight their cited papers — for a lecture
turn, the bubble lights every beat's papers at once (the lecture's whole
scope), a beat lights its own. `ChatMsg.graph`
remains for migration and lecture scope counts; observed grounding provenance
(papers, sources and web actually consulted) stays.

The transcript renders Markdown and KaTeX math, structured source references,
streamed tool traces, inline figures and expandable lecture beats. All of that
stays on its turn across save and restore. `transcript/README.md` describes the
rendering boundary; `figures/README.md` describes figure placement.

## Verification

`test/teacher/useConversation.test.tsx` runs the real hook through a lecture and
an ordinary follow-up, asserting that researcher history includes the lecture —
and through the scope priority list's acceptance cases (see
`scope/README.md`): what reaches each agent, a message scope becoming the
selection and staying, an unmatched scope failing the turn, a correction
re-asking for the same papers. `test/scope/resolve.test.ts` pins
the rule itself. `history.test.ts` covers
incomplete exchanges and figure-marker removal. Teacher and transcript
component tests exercise layout controls, lecture folding and citation clicks
offline. Browser handoff checks the complete flow:
General search, two graph threads, independent follow-ups, cross-thread comparison,
and return to the first graph without losing its conversation or selection.
