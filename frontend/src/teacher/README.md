# `src/teacher`

One composer serves General and graph threads. General is graphless: searches,
broad questions and comparisons can live there. A graph thread's composer names
its subject and scoped paper count. Questions and lectures belong to the active
thread; opening another graph switches to its discussion rather than carrying
this transcript onto a different canvas.

## Sending and streaming

`Teacher.tsx` owns input, menus, scope controls, scroll behavior and transcript
rendering. `/lecture` (optionally `history`) explicitly requests a lecture.
Otherwise `useConversation.ts` asks the router whether the message wants the
researcher or lecturer; graphless conversations bypass that choice. The routing
label lets readers correct a model-selected destination. Lectures are ordinary
chat replies with beats, including real figures and citations.

Bare paper mentions and pasted paper ids open graph threads. Paper mentions
inside questions attach those papers without changing the graph. `@thread` opens
a sibling-discussion picker; choosing a row inserts `@thread[Title]`. The thread
mention is handled before paper lookup, so it cannot accidentally launch a
literature search. Paper and command menus retain their own keyboard behavior.

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
exploration only. Explicit `@thread` references attach that discussion's completed
history. The server bounds sibling count, summary length, history turns and total
borrowed text; it labels the result as quoted background with independent paper
numbering. Replies show a `Context from` line linking to explicitly attached
threads. Borrowing a discussion never silently swaps the canvas.

## Scopes and citations

Source exclusions remain panel-local; the uploaded-source list is shared Redux
state. The graph selectors own paper scope. Researchers can retain discoveries
that filters hide; lectures narrate only the visible selection. Scope changes do
not invalidate earlier answers.

Paper citations highlight their node on the current graph, toggling off on a
second click. Graph icons on search references open or resume that paper's
provider-specific graph thread directly. There is no intermediate paper modal.
Whole-answer and beat clicks highlight their cited papers. `ChatMsg.graph`
remains for migration and lecture scope counts; observed grounding provenance
(papers, sources and web actually consulted) stays.

The transcript renders Markdown and KaTeX math, structured source references,
streamed tool traces, inline figures and expandable lecture beats. All of that
stays on its turn across save and restore. `transcript/README.md` describes the
rendering boundary; `figures/README.md` describes figure placement.

## Verification

`test/teacher/useConversation.test.tsx` runs the real hook through a lecture and
an ordinary follow-up, asserting that researcher history includes the lecture.
`history.test.ts` covers incomplete exchanges and figure-marker removal. Teacher
and transcript component tests exercise commands, layout controls, lecture
folding and citation clicks offline. Browser handoff checks the complete flow:
General search, two graph threads, independent follow-ups, cross-thread comparison,
and return to the first graph without losing its conversation or selection.
