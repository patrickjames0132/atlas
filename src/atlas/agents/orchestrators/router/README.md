# `agents/orchestrators/router`

Which assistant a typed message goes to, and — for a lecture — over which
papers. `route(message)` returns the lecturer or the researcher plus the
framing and **scope** a lecture would use; `resolve_papers(message, papers)`
turns a message that *named* papers into their ids.

```
router/
  main.py    — the classifier agent, MessageRoute (+ Scope), obvious_route,
               route; RoutePaper, the resolver agent, resolve_papers
  config.py  — the two system prompts, the obvious-lecture pattern and its
               deictic-tail whitelist, the borrowed id
```

## Yes, this is the router coming back

`orchestrators/` had one before: a `run(intent, …)` entry point every route
funnelled through, dispatching on an `Intent` enum. It was **deleted in
v7.0.0** because it dispatched two known intents to two agents and *"never
grew the model half it was designed around"* — every caller already knew which
workflow it wanted, so the enum was a string round-trip between a route and
the function next to it.

This package is that model half, finally wanted. The difference is the whole
reason it exists: **nothing here knows which workflow it wants.** The caller is
a composer holding a sentence a person typed, and working out what that
sentence *is* is the entire job. So the shape is deliberately not the old
one — no enum threaded through unrelated routes, no single funnel. `/api/ask`
and `/api/lecture` still exist and are still called directly by everything
that already knows (a reader correcting a route). The router is asked only
when the answer is genuinely unknown.

## Two stages, cheapest first

**`obvious_route`** matches messages that name a lecture outright — "lecture
me on these", "give me a lecture", "lecture:" — **and point at nothing in
particular**, and routes them with no model call at all. It is narrow on
purpose. The tempting additions are all ambiguous: *"summarize this"* means
the scoped papers about half the time and **your last answer** the other
half, and *"walk me through attention"* is as likely a question about the
mechanism as a request to be taught the literature. A fast path that guesses
is worse than no fast path, because the model it skipped would have got those
right.

The second condition is new in v7.23.0, and it narrowed the fast path rather
than widening it. Once a message could choose the lecture's *scope*, "lecture
me on the references" stopped being a message the regex could finish: it
knows the target, but the tail is the half a pattern cannot read. So
`DEICTIC_TAIL` whitelists what may follow the lecture phrase — nothing, or a
phrase that points at the screen ("these", "the selected papers", "what I
have here", "how we got here") — and anything else goes to the model *with*
the target it would have got for free. That includes tails a keyword could
read ("the references"), because a pattern that gets "the references" right
and "the papers that reference the seed" wrong is the guessing fast path the
paragraph above rules out. The cost is one classify on lecture requests that
say which papers — a few hundred milliseconds in front of an operation that
runs for tens of seconds.

**Everything else pays one classify call**, and that cost is the honest price
of the feature. Measured on `claude-haiku-4-5` over fourteen real phrasings:
**580-1040ms, median ~780ms**. Against a researcher turn that runs for several
seconds and a lecture that runs for tens of them that is a few percent, paid
on every question, to make lectures reachable by saying so. There is no
cheaper version: a reliable "is this obviously *not* a lecture" test is the
same classification problem wearing a different sign.

Worth knowing what those measurements showed about the *quality* of the
decision, since it is what the cost buys. `"summarize this"` routes to
**answer** and `"summarize these papers for me"` to **lecture** — the exact
distinction the fast path could not have drawn, and the reason it does not
try. `"what's the story here?"` and `"how did this field get here?"` both come
back as lectures framed as history; `"compare the first two"`, `"explain the
math in this one"` and `"tell me about these"` all stay questions, which is
the safe side working as designed.

## The scope is the message's to choose (v7.23.0)

Until v7.23.0 a lecture was about *whatever the reader had on screen*, full
stop — the v7.17.0 rule, which replaced four mode buttons that each carved
their own slice out of the graph and *overrode* the reader's filters. That
rule still holds; what changed is that the message became one more way to
scope the screen. `MessageRoute.scope` says which papers the message asked
for:

- **`screen`** — the message did not say ("these", "this", a topic word,
  nothing at all). The reader's own scope, and by far the common case.
- **`references`** / **`citations`** — the seed's references (the works it
  cites, its bibliography) or its citers (what built on it).
- **`seed`** — the seed paper alone: "the seed", "this paper", "the one I
  opened". The solo lecture, by name.
- **`named`** — the message identified specific papers: by title, nickname,
  author, or author and year. A field or topic is *not* a named paper;
  "lecture me on transformers" over a transformer graph is `screen`.

A **year window** (`year_from` / `year_to`) rides beside the scope rather
than being a sixth kind, because a period *combines* with the others: "the
references from the 2010s" is `references` with 2010–2019, "everything since
2020" is `screen` with an open end. The message is sent with today's date
appended, so a relative period ("the last five years") has something to count
back from; a year that is part of a paper's name ("Hawking 1975") is not a
period, and the prompt says so. Measured after the scope and period joined
the prompt: **~0.9–1.1s** per classify on `claude-haiku-4-5`, up from the
~780ms median below — a longer prompt, paid on every message.

Since v7.24.0 the scope and period are read for a **question** exactly as
for a lecture — "what do the references say about entropy?" is `references`,
"who wrote the seed?" is `seed`, "which of these used dropout?" is `screen` —
because the researcher grounds in the scope the same way the lecturer
narrates it, under one frontend contract (`frontend/src/scope/README.md`).
The prompt's tie-break is `screen`: it keeps the context the reader already
set up.

The router says **which kind**, never which ids: it reads the message alone.
`named` is a promise that a second call can finish the job — and it is a
separate call, `resolve_papers`, so the graph's paper list crosses the wire
and is billed only for the one message in many that names a paper, never on
the every-message classify. The resolver is shown `[n] title (first author,
year)` per paper — a thin `RoutePaper` cut of a node, with no abstract,
because a title, an author and a year are what a reader names a paper *by*
and the abstract would multiply the prompt without adding a way to match —
and returns indices, which `resolve_papers` maps to ids with out-of-range and
repeated picks dropped. Its prompt is strict in one direction: match loosely
(nicknames, fragments, "Hawking 1975") but return only what the message
points at, since the reader will get a lecture on exactly the list and a
paper they did not ask for is worse than one that could not be found.

What the frontend does with a scope — making it the canvas selection,
drawing the hidden ones, failing the turn in words when an explicit scope
matches nothing — is `frontend/src/scope/README.md`'s story.
The line
between the two halves is worth holding: the backend says what the message
*means*, the frontend decides what that means *on this graph*, because only
it knows what is on screen.

## The asymmetry is the design

**Every failure routes to the researcher** — no API key, network down, rate
limit, output that won't parse, an empty message. `route` never raises and
never returns None, so callers have one code path. `resolve_papers` takes the
same position — a dead model is an empty list — because "nothing matched" is
a case the caller already has to handle.

That is not just defensive coding, it is the cost model. A question misrouted
to the lecturer costs the reader a minute of narration that never addresses
what they asked. A lecture request misrouted to the researcher costs them a
short answer and a second try. The prompt says this in as many words, and
`MessageRoute` carries no `confident` field because of it: a two-way
classifier expresses doubt by picking the safe side, so `target='answer'`
already means "not sure this is a lecture". A third value would give the
caller two spellings of one decision.

## Why it has no Agent Settings row

`AGENT_ID` is **imported from the summarizer** rather than declared, so the
router runs on the summarizer's configured model. It is the fourth one-shot
micro-agent to do that (paper TL;DRs, exploration titles, paper names), and
the house pattern is that a micro-agent emitting a few tokens of structured
output shares the crew's cheapest entry instead of adding a row operators have
to reason about. Importing the constant keeps the shared-model fact checkable
instead of a duplicated string.

The one thing that makes this safe for a *routing* decision, which is less
obviously downgrade-proof than writing a TL;DR: every route is **visible and
correctable** in the transcript. The turn says which assistant answered and
offers the other in one click, so a misroute costs a click rather than a
wrong answer the reader has to detect.

## Who uses it

`POST /api/route` (`routes/agents.py`), called by the chat composer before it
picks between `streamAsk` and `streamLecture`; `POST /api/route/papers`,
called by the same composer only when the first answered `named`. Nothing
else. (Until v7.23.0 a `/lecture` command bypassed the router entirely — the
deterministic path, no classify, no guess. It went because the router reads
everything the command could say and more: a two-value command has no way to
spell "on the references".)

## How it's verified

`test/atlas/agents/orchestrators/router/test_main.py`. The fast path is tested
without any model at all (it must not need one), including the framing pick
and — the assertion that matters most — that the ambiguous phrasings are
**not** claimed by it, now including every lecture request that says which
papers; that is the regression that would silently undo the reasoning above.
The model path is tested through a stubbed agent run for its two contracts:
the output (scope included) is passed through untouched, and every kind of
failure becomes `ANSWER`. The resolver's tests pin the prompt's paper lines
(first author only, "unknown"/"n.d." for missing fields), the index→id
mapping with hallucinated and repeated picks dropped, the paper-list bound,
and that a dead model or nothing to match is an empty list, never a raise.
