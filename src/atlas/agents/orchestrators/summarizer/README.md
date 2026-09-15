# `agents.summarizer`

Three one-shot micro-agents that each write one short piece of text: a
**TL;DR** from a paper's title + abstract (the detail panel's on-demand
summary for papers that don't ship one), an **exploration title** from a
conversation's opening turns (the name an automatically-saved exploration
arrives in the rail with), and a **paper name** resolved from an acronym or
nickname (the composer's `@` lookup).

They share one `AGENT_ID`, and so one configured model. Adding an entry to
Agent Settings for a six-word phrase would have bought nothing, and the
summarizer is already the crew's cheapest, safest-to-downgrade member — which
is exactly the tier these want.

## The paper-name resolver (v7.18.0)

`title_for_paper_name('dqn')` → *"Playing Atari with Deep Reinforcement
Learning"*. It exists because that mapping is **world knowledge and nothing
else can supply it**, which was measured before the agent was written: S2's
free-text search does not return that paper for that query even at limit 30,
`match_title('dqn')` returns nothing, and no field of the cached node —
title, authors, abstract, tldr, venue — contains the string, because the 2013
paper predates the name.

Two properties of its contract matter more than the prompt:

- **It emits `confident` as a field**, and the caller throws the answer away
  when it is false. A model asked for a title will usually produce one whether
  or not it knows the paper, and an invented title at the top of a suggestion
  list is worse than no suggestion at all. "transformers" and "reinforcement
  learning" name fields, not papers, and must come back false.
- **Its caller verifies before trusting.** `services/search/naming.py` runs
  the proposed title through the provider and keeps the paper only if one
  matches — the model proposes, the corpus confirms. That module also caches
  per name (misses included) and only calls this at all when no candidate's
  title already equals what was typed, so a nickname costs one model call
  rather than one per keystroke.

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
  from), the complete `SYSTEM_PROMPT` and `TITLE_SYSTEM_PROMPT`, and an empty
  `SKILLS` tuple (skills carry teaching-behavior rules; neither agent teaches).
- **`main.py`** — both `Agent`s (output types `Summary` and
  `ConversationTitle`; the model arrives per run from `factory.model_for`,
  never at import — see `agents/README.md`) and the two entry points callers
  touch, `summarize` and `title_for_conversation`.
- No `tools.py` — neither agent calls anything.

The titling flow:

```
useAutosave  (an exploration's FIRST save only)
      ↓ POST /api/sessions/title {turns: [...]}
routes/sessions.api_sessions_title
      ↓ summarizer.title_for_conversation   main.py
      ↓ title_agent.run_sync → ConversationTitle.title
      ↓ null → caller falls back to the reader's own first message
```

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
- **A title is written once per exploration, and never on the save path.**
  The autosave fires every couple of seconds; titling on each write would
  bill a model call per debounce *and* would overwrite a name the reader had
  edited from the row's ⋮ menu. So the frontend calls the title route once,
  on an exploration's first save, and reuses the answer. It is a separate
  route from `POST /api/sessions` for the same reason — model latency has no
  business on a request that runs all afternoon.
- **A null title is a 200, not an error.** Unlike the TL;DR — where the user
  explicitly asked for a summary, so failure must be visible — nobody asked
  for a title. The caller has a free fallback in the reader's own first
  message, and an exploration must never fail to save because a nicety was
  unavailable.
- **The output is stripped of a model's habits**: surrounding quotes and a
  trailing period, both of which read wrong in a list row. The prompt bans
  the stock openings ("Chat about…", "Exploring…") and asks for the subject
  rather than the activity.

## Who uses it, and how/why

- **`routes/graph.py::api_paper_tldr`** — the TL;DR's only caller, wrapping
  it in the cache check/write. `api_paper` (hydration) additionally back-fills
  `tldr` from the same cache so a generated summary shows up on later
  opens without the frontend asking.
- **`routes/sessions.py::api_sessions_title`** — the titler's only caller.
- **Frontend:** `DetailPanel`'s summary toggle → `api.generateTldr` for the
  TL;DR; `shell/useAutosave.ts` → `api.titleForConversation` for the title.

## Testing

`test_main.py` swaps the model via `agent.override(...)`: `TestModel` with
`custom_output_args` proves the sentence flows through, a `FunctionModel`
captures the prompt (title + abstract both present), a raising
`FunctionModel` proves failure degrades to None, and a run *without* an
override proves the suite's `ALLOW_MODEL_REQUESTS = False` guard trips
first. Blank-abstract and blank-output edges round it out. The titler is
covered the same way — the structured title flows through (stripped of quotes
and a trailing period), an empty conversation never reaches the model, and a
raising model degrades to None. The route behaviour lives in
`test/atlas/routes/test_graph.py` (TL;DR cache hit/miss/error) and
`test/atlas/routes/test_sessions.py` (title validation, and null-as-200).

## Thread summaries

`summary_for_thread` is a fourth micro-agent sharing the summarizer model. It
combines the previous paragraph with completed discussion prose, bounded to
24,000 input characters and 1,500 output characters. It is called only when a
thread settles and its transcript has advanced, separately from saving. Failure
returns None so a missing model never prevents persistence.
