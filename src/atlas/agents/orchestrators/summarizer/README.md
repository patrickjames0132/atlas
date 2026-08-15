# `agents.summarizer`

A one-shot micro-agent that writes a TL;DR from a paper's title + abstract —
the detail panel's on-demand summary for papers that don't ship one.

## Why it exists

The detail panel's summary section shows the abstract by default with a
TL;DR view a click away. Semantic Scholar provides its own model-written
TLDRs for many papers — but **OpenAlex has no equivalent at all**, and even
S2 lacks one for plenty of papers. Rather than a blank view (or a second
panel section — rejected in the OnePager ticket), the TL;DR toggle
generates one right there. This is the digest era's "summarize" button
reborn as a per-paper TL;DR.

## How it works

```
DetailPanel  (TL;DR toggle on a paper without one)
      ↓ POST /api/paper/tldr {id, title, abstract}
routes/graph.api_paper_tldr
      ↓ cache.get("tldr:v1:<id>")          hit → return, NO model call
      ↓ summarizer.summarize               main.py
      ↓ agent.run_sync → Summary.tldr      (PydanticAI Agent, no deps/tools)
      ↓ cache.set("tldr:v1:<id>")          never expires
```

- **`config.py`** — `AGENT_ID` (which `config.llm.agents` entry to build
  from), the complete `SYSTEM_PROMPT`, and an empty `SKILLS` tuple (skills
  carry teaching-behavior rules; this agent doesn't teach).
- **`main.py`** — the `Agent` (model from `factory.build_model`, output type
  `Summary`) and `summarize`, the only function callers touch.
- No `tools.py` — the agent calls nothing.

## Design decisions worth knowing

- **On demand is the contract.** The agent runs ONLY when the user toggles a
  selected paper to TL;DR — never during graph builds, neighbor traversals,
  or panel hydration. Patrick's rule, verbatim: don't bill the Anthropic
  account for papers nobody reads. Hydration (`api_paper`) only *reads* the
  cache — a cached TL;DR rides along for free; an uncached one stays
  ungenerated until asked for.
- **Cached forever, keyed by node id** (`tldr:v1:<node id>`, `max_age=None`).
  An abstract-derived summary doesn't go stale, and the permanent cache is
  what makes each paper bill at most once, across sessions and reloads. The
  `v1` prefix is the invalidation lever if the prompt ever changes enough to
  matter.
- **Provider-agnostic on purpose.** The ticket asked for OpenAlex; keying by
  node id and passing `{title, abstract}` from the client makes the same
  path serve S2 papers whose TLDR is missing — free coverage, no extra code.
- **None on any failure, and the route says so.** `summarize` catches
  everything and returns None (blank abstract, no key, network, junk
  output); the route maps that to an honest 502 and the panel keeps showing
  the abstract. Unlike the query analyst there's no silent passthrough —
  the user explicitly asked for a summary, so failure must be visible.
- **Structured output, not completion text** — a typed `tldr` field, so
  lead-ins the model might add can't reach the panel. The prompt pins the
  register: one plain-language sentence, lead with the contribution,
  summarize only what the abstract claims.
- **A cheap, fast model.** The config entry runs Haiku — one sentence from
  one abstract on an interactive click; flagship models buy nothing here.

## Who uses it, and how/why

- **`routes/graph.py::api_paper_tldr`** — the only caller, wrapping it in
  the cache check/write. `api_paper` (hydration) additionally back-fills
  `tldr` from the same cache so a generated summary shows up on later
  opens without the frontend asking.
- **Frontend:** `DetailPanel`'s summary toggle → `api.generateTldr` — the
  only surface that can trigger a generation.

## Testing

`test_main.py` swaps the model via `agent.override(...)`: `TestModel` with
`custom_output_args` proves the sentence flows through, a `FunctionModel`
captures the prompt (title + abstract both present), a raising
`FunctionModel` proves failure degrades to None, and a run *without* an
override proves the suite's `ALLOW_MODEL_REQUESTS = False` guard trips
first. Blank-abstract and blank-output edges round it out. The route's
cache-hit/miss/error behavior lives in `test/atlas/routes/test_graph.py`.
