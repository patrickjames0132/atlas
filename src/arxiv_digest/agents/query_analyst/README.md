# `agents.query_analyst`

A one-shot micro-agent that analyzes seed-search queries — the smallest agent
in the crew, and the proving ground for the whole PydanticAI wiring (the
factory, the config entry, the test patterns every later agent reuses).

## Why it exists

Semantic Scholar's `/paper/search` is **lexical**: a paper matches only words
that literally appear in its title or abstract. So a query like "DQN" misses
the seminal deep Q-learning papers — they predate the acronym or simply never
spell it out. The analyst attacks that gap from both ends:

- **Expansion** — "DQN" → "DQN deep Q-network deep Q-learning" keeps the
  user's terms and appends the spelled-out forms, so the lexical search can
  meet the papers halfway. (The old repo knew it needed this and left a seam
  — `services/search`'s documented passthrough; this agent is what the seam
  was waiting for.)
- **Title recall** — Google resolves "DQN" straight to the Mnih et al.
  paper because the web is full of pages that *say* "DQN" and *link to* it;
  the model internalized those same associations in training. When the
  query clearly refers to specific papers, the analyst names their exact
  titles from parametric knowledge, and the search service verifies each
  against S2's title-match endpoint before showing anything.

## How it works

```
services.search.live_search
      ↓ _analyze (the seam — unchanged call site since Phase 3)
query_analyst.analyze              main.py
      ↓ agent.run_sync             (PydanticAI Agent, no deps, no tools)
      ↓ Expansion                  (structured output — never prose)
        .expanded_query  → s2.search_papers (the lexical search)
        .known_titles    → s2.match_title, verified hits lead the results
```

- **`config.py`** — `AGENT_ID` (which `config.llm.agents` entry to build
  from), the complete `SYSTEM_PROMPT`, and an empty `SKILLS` tuple (skills
  carry teaching-behavior rules; this agent doesn't teach).
- **`main.py`** — the `Agent` (model from `factory.build_model`, output type
  `Expansion`) and `analyze`, the only function callers touch.
- No `tools.py` — the agent calls nothing.

## Design decisions worth knowing

- **Passthrough on any failure — the one hard rule.** `analyze` catches
  *everything* (no key, network down, rate limit, junk output) and returns
  the query unchanged with no titles, logging a warning. Analysis is an
  enhancement; search must never break because the LLM hiccuped. A blank
  query short-circuits before the model is ever engaged, and a blank
  *expansion* falls back to the original.
- **Titles are suggestions, never truth.** `known_titles` carries only
  confident recalls (the prompt: "a doubtful title is worse than none",
  at most 3) — and the search service verifies every one against S2's
  title match before it reaches the user. A hallucinated title matches
  nothing and costs one lookup; the failure mode is "no better than plain
  expansion," never worse. Post-cutoff papers degrade the same way.
- **Structured output, not completion text.** Typed fields, so prose the
  model might wrap around the query ("Here is the expanded version...")
  can't leak into the search box.
- **The prompt teaches restraint.** Keep every original term, append only a
  handful of expansions — a query drowned in synonyms ranks worse than an
  unexpanded one. "Return it unchanged if nothing needs expanding" and
  "empty list otherwise" are explicit instructions, not hoped-for behavior.
- **A cheap, fast model.** The config entry runs Haiku: this fires on every
  live search, sits on the interactive path, and the task is vocabulary
  work plus recall — flagship models buy nothing here.

## Who uses it, and how/why

- **`services/search/discovery.py`** (ported, live in the new tree) —
  `live_search` passes every free-text query through `_analyze`, whose whole
  body is `return query_analyst.analyze(query)`; it uses `expanded_query`
  for the lexical search and `known_titles` for title-match verification.
  The seam survives as a named function (rather than inlining the call) so
  search tests can monkeypatch `discovery._analyze` without importing agent
  machinery, and because it predates the agent — the old repo shipped it as
  a documented passthrough waiting for exactly this. Pasted arXiv ids
  bypass the analyst entirely (an id isn't vocabulary), and `local_search`
  never calls it: it greps graphs already cached on disk, where recall is
  bounded by what's stored, not by vocabulary.
- **Nobody else.** Not reachable through the orchestrator — query analysis
  is search infrastructure, not a teacher workflow; the frontend never
  addresses this agent, it just gets better search results.

## Testing

`test_main.py` swaps the model via `agent.override(...)`: `TestModel` with
`custom_output_args` proves expansion and titles flow through (and blank
titles are dropped); a raising `FunctionModel` proves failure degrades to
passthrough; a run *without* an override proves the suite's
`ALLOW_MODEL_REQUESTS = False` guard trips first and the passthrough eats
even that. Blank-query and blank-expansion edges round it out. The seam's
delegation, title verification, and result ordering are covered in
`services/test_search.py`.
