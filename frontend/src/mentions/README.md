# `src/mentions`

Naming a paper — or another discussion in this exploration — in the chat bar:
type `@`, pick from the suggestions that appear, and the message carries a real
paper (or a real thread's history) rather than a phrase the assistant has to go
and resolve.

```
mentions/
  parse.ts                  — the grammar, as pure functions: which mention the
                              caret is in, what a pick splices in (a paper or a
                              thread), which threads match, and what a finished
                              message turns out to be asking for
  useMentionSuggestions.ts  — the typeahead engine: debounce, abort, lookup,
                              thread rows, keyboard selection
  MentionSuggestions.tsx    — the dropdown above the composer: threads, then
                              papers
  mentions.css              — its styles
```

## What it replaced, and why that shape was wrong

There was a **"Find papers" toggle** beside the bar (v7.6.0–v7.17.0). You armed
it, then typed, and the same words meant different things depending on a
button's state: armed, they went to the paper scout and came back as a list;
unarmed, they went to the researcher and came back as an answer.

Two problems with a mode. It puts the decision *before* the sentence, when the
reader is still working out what they want to say. And it is invisible in the
result — a transcript of "attention is all you need" doesn't record which mode
was on when it was sent.

`@` says the same thing inside the sentence, where it can be read back. It also
covers a case the toggle never could: naming a paper **as part of a question**
("what does @… say about X?"), which under a mode meant either losing the
question or losing the paper.

## Design decisions worth knowing

- **A mention has no closing delimiter, on purpose.** Paper titles contain
  spaces, so `@attention is all you need` has to be one mention rather than
  five, which means the query runs from the `@` to *wherever the caret is*.
  That works precisely because it is only used while typing. Reading a
  finished message uses a different mechanism (below).
- **Resolution is exact-substring, and its failure mode is deliberate.** A
  pick inserts `@<full title>` and records that string in the draft's resolved
  map; `mentionsIn` finds a paper by looking its inserted text up in the
  message. Edit the title afterwards and the paper quietly stops being a
  resolved mention, so the words are treated as words the reader typed. The
  alternative — tracking offsets through every edit — buys precision the
  composer doesn't need and breaks in ways much harder to explain.
- **Three destinations, still decided without a model.** `readMessage` is a
  substring check and a `startsWith`; `Teacher`'s submit handler has always
  branched on plain facts rather than asking an agent to classify the input,
  and that survives. What changed is who supplies the fact: the reader, by
  typing `@`, instead of a toggle they set earlier.
  - `@<a picked paper>` alone → **seed the graph**. The same rule as a pasted
    arXiv id (`ID_RE`, which still runs first because an id needs no lookup at
    all): naming one paper and nothing else is a statement of intent.
  - `@<words that resolved to nothing>` alone → **the paper scout**. The
    dropdown's fallback, and what makes it safe to keep cheap — a paper the
    local cache has never seen is still reachable, just after sending rather
    than before. This is exactly what the toggle used to do.
  - anything else → **the researcher**, with any resolved mentions attached as
    grounding. An *unresolved* `@phrase` inside a question is simply part of
    the question: routing the whole sentence to the scout would drop the
    question, and the researcher has its own paper search for when an answer
    needs one. A **thread mention** (`@thread[Title]`) always lands here too,
    even alone — it names a discussion to carry along, not a paper to find,
    so `readMessage` keeps it away from the scout, which would otherwise
    search for papers titled "thread[Title]".
- **Sibling threads are rows of the same list, above the papers.** The other
  discussions in the current exploration are offered under their own head
  ("Discussions in this exploration") before "All paper results". They are a
  local list of a few titles, filtered by substring with no request at all, so
  they show from the **first character** — `@` alone lists every one of them,
  which is how a reader finds out that a discussion is mentionable — while the
  paper lookups still wait for the three-character floor. Picking one inserts
  `@thread[Title]`: bracketed because a thread title is arbitrary text
  ("PPO", "General") and the brackets are what tells the send path
  (`teacher/history.ts`, `useConversation`'s `turnContextSet`) that the words
  name a discussion to attach rather than a paper to look up. Nothing else
  about a thread mention is tracked in the draft: the text is the whole
  reference, and `send` resolves it against the exploration's threads.

  This replaced a separate picker that opened only on the literal keyword
  `@thread` (v7.22.0–v7.25.0). The keyword was the problem: the tour said
  "type @thread" and that reads, naturally, as "@ plus the thread's name" —
  which went to the paper lookup, and the reader concluded threads couldn't
  be mentioned at all. One `@`, one list, labelled sections: the discovery
  is in the dropdown instead of in a sentence the reader has to parse right.
- **Nothing is selected until the reader selects it.** The dropdown used to
  pre-highlight its top row, so Enter on an untouched list spliced in a paper
  the reader had only been *shown* — and Enter again, on the bare mention
  that left behind, seeded the graph. That is the wrong default for a list
  whose top row is a guess: the reader who typed `@sparse autoencoders` and
  hit Enter wanted the scout's full search (the `find` route above), not a
  landing on whichever paper the cache ranked first. Now a row is only
  chosen by arrowing onto it or hovering it (`highlighted` is `-1` until
  then, and `choice` null); Enter or Tab with no row chosen falls through to
  send. Down from nothing lands on the first row, up on the last.
- **Enter does the thing; Tab completes.** Enter on a chosen paper that is
  the **whole message** (`ActiveMention.whole`: nothing but whitespace
  around it) picks *and sends* in one press — the reader chose one paper and
  nothing else, which is already the seed rule, and completing `@Title` into
  the box to demand a second Enter was a step with no decision in it. Tab on
  the same row only completes the text, for the reader who wants the title
  in the box without opening it. A paper inside a sentence, or a thread,
  completes either way: the question still has to be written, and a thread
  alone is not a message. Because Enter's two jobs — *send what I typed*,
  *take what I chose* — are told apart only by whether a row is lit, the
  dropdown's footer says what Enter does **right now** (`hintFor`): "Enter
  searches for what you typed" with nothing chosen on a bare mention, "Enter
  sends your message" inside a sentence, "Enter opens this paper", "Enter
  adds this paper to your question", "Enter attaches this discussion". The
  footer is pinned: the panel is capped at 320px but only the row list
  (`.mention-list`) scrolls, so a full page of results can't push the one
  line that explains Enter below the fold — which it did, and exactly when
  the list was long enough to need it.
- **A completed mention ends the mention.** A mention has no closing
  delimiter, so after a pick the `@` at the start of the message still
  "owned" everything typed after it — the lookup ran on *"Attention Is All
  You Need what does it say about"* for every keystroke of the question, and
  the same for *"thread[General] what are some of the other"* (which is how
  it was noticed). `activeMention` therefore takes the draft's `completed`
  texts (the composer passes its resolved-mention keys) and an `@` that opens
  one of them is not active; a closed `@thread[…]` ends itself, its bracket
  being the delimiter a paper title lacks. Editing *inside* a completed title
  reopens it — the text before the caret is then only a prefix of the
  completed one — which is the right answer for a reader changing their
  mind.
- **A mentioned paper grounds the question; it is never merged onto the
  canvas.** Asking *about* a paper is not asking to explore it, and
  rearranging the reader's graph as a side effect of a question is the
  override this app keeps having to remove (see the lecture scoping story in
  `agents/orchestrators/lecturer/README.md`). The paper joins that message's
  numbered nodes — ahead of the graph's own, so it takes the low `[n]` numbers
  an answer is most likely to cite — and `useConversation`'s `mentionNode`
  widens the trimmed row into the full `GraphNode` the ask boundary demands.
- **Two lookups on two clocks, because the sources cost different amounts.**
  `/api/mentions?source=local` scans the reader's cached snapshots and nothing
  else — free, offline, milliseconds — so it fires on **every keystroke, with
  no debounce**: delaying something already instant would only make the
  dropdown feel slower than it is. The full call adds a **day-cached** provider
  search and is the one that waits, so it fires only when the reader pauses
  (250 ms), refuses queries under three characters, and aborts the request in
  flight on each new one. Typing a title straight through therefore costs
  **one provider lookup**, not one per keystroke.

  It shipped as a single blocking call serving both, and that was wrong in a
  way worth recording: the free half bought nothing, because the response still
  waited on the provider. Local-*first* ordering was real; local-first *timing*
  was not.
- **The full pass streams its phases, and the dropdown shows the latest as one
  live line.** Three phases of visibly different cost run inside it — a cache
  scan, a network round trip, and (for a nickname) a model call plus a
  verification — and a blocking response could only say "Searching…" for all
  three. Each `step` frame carries the label in the *server's* words, because
  the frontend cannot see the phase that matters: the resolve happens inside
  the request, so faking labels from which fetch is in flight would name the
  two cheap phases and omit the slow one. The resolve's step is emitted
  **before** the call, since a step that appears on completion reports what
  already happened.

  One line that replaces itself, not an accumulating history — despite the ask
  being phrased as "collapsable steps". The reference it came with (ChatGPT's
  *"Searching www.bls.gov"*) is itself one self-replacing line, the panel is
  small and opens upward, and a lookup that finishes in a second or two turns a
  step history into noise. Collapsible step history belongs to the scout run
  after send, where it already exists as trace chips.

  A provider failure degrades to the cached hits: a reader mid-sentence is
  better served by a short list than by an error.
- **The full list is re-ranked across both sources, and the keyboard follows
  the paper rather than the row.** `rank_mentions` orders by exact title match,
  then title-prefix, then any title hit, then citations — so a paper the reader
  just named leads, whichever source found it, instead of the old "everything
  cached, then everything live". Cached hits are deliberately *not* privileged
  by the sort: being cached makes a paper instant, which is why it is fetched
  and shown first, but says nothing about whether it is the one meant (ties
  still favour it, since cached hits are passed first into a stable sort).

  Re-ranking a list someone is arrowing through is hostile if handled
  carelessly, so the hook tracks the selection by **row key, not index**
  (`highlightedKey` — the row's kind plus its id, so a thread and a paper
  sharing an id can't be confused). The row moves, the selection moves with
  it, and Enter takes what the reader was looking at. If a re-rank drops the
  tracked paper entirely, the selection falls back to **nothing** — not to
  the top, which would be a paper the reader never chose.
- **One model call, and it is the only one — because nicknames are world
  knowledge.** Typing `@dqn` cannot reach *Playing Atari with Deep
  Reinforcement Learning* by any text match, and that was measured rather than
  assumed: S2's free-text search doesn't return it for that query even at
  limit 30, `match_title('dqn')` returns nothing, and no field of the cached
  node — title, authors, abstract, tldr, venue — contains the string, because
  the 2013 paper predates the name. What text search *does* return is a page
  of papers with "DQN" in the title, none of them the one meant.

  So the full pass ends with a resolve: a one-shot micro-agent
  (`summarizer.title_for_paper_name`) proposes the real title, the provider
  **verifies it exists**, and the confirmed paper is prepended. The
  verification is not optional — a model asked for a title will usually
  produce one, so without it a half-remembered nickname would put an invented
  paper at the top of the list, which is worse than showing nothing.

  Three things keep it cheap: it never runs on the free pass, it is skipped
  when a candidate's title already *is* what was typed (the one case world
  knowledge can't improve on), and the answer is **day-cached per name,
  misses included** — "transformers" is not a paper, and asking again won't
  change that. See `services/search/naming.py`.

  The gate is exact-equality on purpose. The obvious version — "does any title
  *contain* the query?" — was written first and is wrong: for `dqn` it reports
  success on a list that doesn't contain the answer. *Text matching finding
  something is not the same as finding the thing.*
- **The year/field filters deliberately do not bind a mention.** They narrow a
  *search* for papers the reader hasn't named; a mention names one. Filtering
  to 2020+ and then failing to resolve `@attention is all you need` (2017)
  would be maddening — and it is the reading the paper scout's `match_title`
  already takes. The filters still bind everything else, which is why the
  funnel control outlived the toggle it sat beside.
- **Hover moves the keyboard selection.** One highlight state, so mouse and
  keyboard can never point at different rows and leave the reader guessing
  what Enter will take. Picks fire on pointer-*down*, because the composer's
  blur closes the panel and would unmount the row before a click landed.

## Who uses it

`teacher/Teacher.tsx` alone. It owns the textarea, so it holds the resolved-mention
map for the draft (a ref — nothing renders from it, and re-rendering on every
pick would fight the textarea's caret handling), passes the exploration's
sibling threads into the hook, re-reads the caret on input, click and key-up,
and hands the arrows and Escape to the dropdown while it is open — and Enter /
Tab only once a row is chosen, so an untouched list never eats a send.

## How it's verified

`test/mentions/` mirrors this folder. `parse.test.ts` is the important one —
it pins the three destinations (including that a bare `@thread[…]` is never a
search), the edit-breaks-resolution behaviour, the two insert forms, the
thread matcher, `whole`, and that a completed mention (a resolved title, a
closed `@thread[…]`) ends the mention while a later `@` opens a new one,
since those rules decide what a message *means*.
`useMentionSuggestions.test.ts` pins the cost guarantees (a burst of typing is
one *provider* lookup while the free pass runs per keystroke; the cache is
asked with no debounce at all; threads cost no request at all and show from
the first character; Escape stays shut until the query changes) because that
is the half that could quietly become expensive — the selection rules (nothing
chosen until the reader moves; down from nothing is the top, up is the bottom;
threads then papers walk as one list) — and the two re-rank tests, which are
the ones that matter most: the keyboard stays on the same paper when the list
reorders, and falls back to no selection when its paper is gone.
`MentionSuggestions.test.tsx` covers the row layout, the thread section and
its cross-section row numbering, the `-1` no-selection state, `hintFor`'s
five states, the sparse record with no byline, pointer-down picking, and the
phase line (including that it shows *alongside* results, since the
provisional list lands first). The composer's side — Enter with nothing
chosen is a send, Enter on a bare chosen paper seeds in one press, Tab only
completes, a paper in a sentence or a thread only completes, a sent
`@thread[…]` reaches the assistant and never the scout — is pinned in
`test/teacher/Teacher.test.tsx` against a scripted hook.
On the backend, `test_search.py` pins the frame order, the provider's name in
its label, that the resolve step precedes the resolve, and that no resolve step
is claimed when the resolve was skipped.

## Sibling discussion references

A picked thread's `@thread[Title]` attaches bounded, labelled sibling history
to the message (`teacher/history.ts`'s `siblingContext`) rather than resolving
a paper or changing the canvas. The sent answer retains stable thread ids for
its `Context from` navigation controls. See `teacher/README.md` for the send
side; this package only puts the reference in the text.
