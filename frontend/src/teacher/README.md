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

**A lecture's scope is the message's to choose** (v7.23.0). The route carries
a `scope` — `screen` when the message did not say, which is what every lecture
used to be and still the common case; `references`, `citations`, `seed`; or
`named`, meaning the message pointed at specific papers — and a **year
window** (`year_from`/`year_to`) when the message limited it to a period,
which combines with any scope: "the references from the 2010s" is a relation
and a window, "the papers between 2016 and 2017" is the graph and a window.
`lectureScope.ts` turns that into nodes on the current graph: "the
references" are the reference-tagged nodes (the tag the paper is coloured by
and the set its chip toggles, so the word means the same said as clicked),
"the seed" is the solo lecture, a period filters off the *whole* graph (a
year the sliders exclude is exactly what the message should reach past —
narrowed within a hand-picked selection when there is one), and a `named`
scope pays one more call (`resolveRoutedPapers`, with the graph's
titles/authors/years only — never abstracts) to turn nicknames and
author-year references into ids. `send` then puts the scope on the canvas
*before* the lecture starts — `lectureScopeApplied` makes it the hand-picked
selection and **reveals** whichever of those papers a chip or slider was
hiding, so the reader sees what is about to be narrated and the lecturer's
one promise (it narrates what is on screen) holds — and hands the same nodes
to `lectureInChat` explicitly, because the canvas republishes its visible set
only on its next render. A scope that matches nothing on the graph fails the
turn in words; lecturing on everything instead would be the app deciding it
knew better, which is the override this app keeps having to remove.

**The scope is one-shot** (Patrick, 2026-09-15: the request should force the
scope, but once the lecture finishes it should only be *highlighting* the
papers). The selection holds while the lecture streams — papers ringed, the
rest dimmed, "Scoped to N papers" in the panel — and `lectureScopeReleased`
lets it go when the stream ends, unless the reader re-picked meanwhile. What
stays is the highlight: every lecture, scoped or not, ends with all of its
beats' papers lit and its bubble active — the same state as clicking the
bubble — where before only the last beat stayed lit, which read as the
lecture pointing at its ending rather than at what it covered. The revealed
papers stay on screen too (a released reveal would hide the very papers the
highlight is lighting) until the next Esc.

Bare paper mentions and pasted paper ids open graph threads. Paper mentions
inside questions attach those papers without changing the graph. `@thread` opens
a sibling-discussion picker; choosing a row inserts `@thread[Title]`. The thread
mention is handled before paper lookup, so it cannot accidentally launch a
literature search. Both pickers retain their own keyboard behavior.

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
and through each routed scope, asserting what reaches the lecturer, what the
canvas is scoped to, which hidden papers are revealed, and that an unmatched
named scope fails the turn without streaming. `lectureScope.test.ts` pins the
scope-to-nodes rule and the thin resolver list. `history.test.ts` covers
incomplete exchanges and figure-marker removal. Teacher and transcript
component tests exercise layout controls, lecture folding and citation clicks
offline. Browser handoff checks the complete flow:
General search, two graph threads, independent follow-ups, cross-thread comparison,
and return to the first graph without losing its conversation or selection.
