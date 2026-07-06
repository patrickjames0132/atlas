# `agents.query_analyst`

A one-shot micro-agent that expands seed-search queries — the smallest agent
in the crew, and the proving ground for the whole PydanticAI wiring (the
factory, the config entry, the test patterns every later agent reuses).

## Why it exists

Semantic Scholar's `/paper/search` is **lexical**: a paper matches only words
that literally appear in its title or abstract. So a query like "DQN" misses
the seminal deep Q-learning papers — they predate the acronym or simply never
spell it out. The fix is expansion: "DQN" → "DQN deep Q-network deep
Q-learning" keeps the user's terms and appends the spelled-out forms, so the
lexical search can meet the papers halfway. The old repo knew it needed this
and left a seam (`services/search`'s `_expand_query`, a documented
passthrough); this agent is what the seam was waiting for.

## How it works

```
services.search.live_search
      ↓ _expand_query (the seam — unchanged call site)
query_analyst.expand_query          main.py
      ↓ agent.run_sync              (PydanticAI Agent, no deps, no tools)
      ↓ Expansion.expanded_query    (structured output — never prose)
      → the expanded query, off to s2.search_papers
```

- **`config.py`** — `AGENT_ID` (which `config.llm.agents` entry to build
  from), the complete `SYSTEM_PROMPT`, and an empty `SKILLS` tuple (skills
  carry teaching-behavior rules; this agent doesn't teach).
- **`main.py`** — the `Agent` (model from `factory.build_model`, output type
  `Expansion`) and `expand_query`, the only function callers touch.
- No `tools.py` — the agent calls nothing.

## Design decisions worth knowing

- **Passthrough on any failure — the one hard rule.** `expand_query` catches
  *everything* (no key, network down, rate limit, junk output) and returns
  the query unchanged, logging a warning. Expansion is an enhancement; search
  must never break because the LLM hiccuped. A blank query short-circuits
  before the model is ever engaged, and a blank *expansion* falls back to the
  original.
- **Structured output, not completion text.** `Expansion.expanded_query` is
  a typed field, so prose the model might wrap around the query ("Here is
  the expanded version...") can't leak into the search box.
- **The prompt teaches restraint.** Keep every original term, append only a
  handful of expansions — a query drowned in synonyms ranks worse than an
  unexpanded one. "Return it unchanged if nothing needs expanding" is an
  explicit instruction, not a hoped-for behavior.
- **A cheap, fast model.** The config entry runs Haiku: this fires on every
  live search, sits on the interactive path, and the task is two lines of
  vocabulary work — flagship models buy nothing here.

## Who uses it, and how/why

- **`services/search/discovery.py`** (ported, live in the new tree) —
  `live_search` passes every query through `_expand_query`, whose whole body
  is `return query_analyst.expand_query(query)`. The seam survives as a
  named function (rather than inlining the call) so search tests can
  monkeypatch `discovery._expand_query` without importing agent machinery,
  and because it predates the agent — the old repo shipped it as a
  documented passthrough waiting for exactly this. `local_search` does
  *not* expand: it greps graphs already cached on disk, where recall is
  bounded by what's stored, not by vocabulary.
- **Nobody else.** Not reachable through the orchestrator — expansion is
  search infrastructure, not a teacher workflow; the frontend never
  addresses this agent, it just gets better search results.

## Testing

`test_main.py` swaps the model via `agent.override(...)`: `TestModel` with
`custom_output_args` proves the expansion flows through; a raising
`FunctionModel` proves failure degrades to passthrough; a run *without* an
override proves the suite's `ALLOW_MODEL_REQUESTS = False` guard trips first
and the passthrough eats even that. Blank-query and blank-expansion edges
round it out. The seam's delegation is covered in `services/test_search.py`.
