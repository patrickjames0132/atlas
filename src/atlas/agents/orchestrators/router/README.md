# `agents/orchestrators/router`

Which assistant a typed message goes to. One function, `route(message)`,
returning the lecturer or the researcher plus the framing a lecture would use.

```
router/
  main.py    — the classifier agent, MessageRoute, obvious_route, route
  config.py  — the system prompt, the obvious-lecture pattern, the borrowed id
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
that already knows (the Lecture button, an `@`-mention seed, a correction).
The router is asked only when the answer is genuinely unknown.

## Two stages, cheapest first

**`obvious_route`** matches messages that name a lecture outright — "lecture
me on these", "give me a lecture", "lecture:" — and routes them with no model
call at all. It is narrow on purpose. The tempting additions are all ambiguous:
*"summarize this"* means the scoped papers about half the time and **your last
answer** the other half, and *"walk me through attention"* is as likely a
question about the mechanism as a request to be taught the literature. A fast
path that guesses is worse than no fast path, because the model it skipped
would have got those right.

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

## The asymmetry is the design

**Every failure routes to the researcher** — no API key, network down, rate
limit, output that won't parse, an empty message. `route` never raises and
never returns None, so callers have one code path.

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
picks between `streamAsk` and `streamLecture`. Nothing else — and in
particular the Lecture button does not, because a reader pressing a control
labelled "Lecture" has already classified their own intent.

## How it's verified

`test/atlas/agents/orchestrators/router/test_main.py`. The fast path is tested
without any model at all (it must not need one), including the framing pick
and — the assertion that matters most — that the ambiguous phrasings are
**not** claimed by it, which is the regression that would silently undo the
reasoning above. The model path is tested through a stubbed agent run for its
two contracts: the output is passed through untouched, and every kind of
failure becomes `ANSWER`.
