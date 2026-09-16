# Atlas

**Explore how research papers connect — and have an AI teacher narrate the
story of how a field got here.**

Drop in a paper and Atlas renders a **Connected-Papers-style interactive
graph** of how it links to the literature — the papers it cites (its
intellectual ancestors), the papers that cite it (its descendants), and its
nearest neighbors by meaning. Then wander: double-click any node to re-center
the graph on it and keep exploring.

Each **exploration** contains a permanent **General** discussion and a thread
for each graph. Switching threads restores that graph and its conversation.
Paper citations highlight the current graph; graph icons open or resume a graph
thread directly. Use **@thread** to bring another discussion into the agent's
context. Lectures remain part of their thread's history, including follow-up
questions after a reload. Existing saved sessions migrate lazily when opened.

It connects to the academic-graph ecosystem **dynamically** — there's no local
corpus of papers to store. The only things kept on disk are a small cache of
the graphs you've looked at, your saved sessions, and the library of sources
you upload (embedded locally; nothing leaves your machine).

**Why it exists.** Atlas is free software (MIT), built to put research and
self-teaching within reach of anyone who wants to learn something — not to
become a product. It runs on your own machine, and the sources you upload
never leave it. If something with more reach ever does this better, good;
until then this exists, and you can have it.

> **The teacher runs on whichever model you point it at, including free ones.**
> The graph explorer is keyless and free. For the AI teacher, pick a vendor:
> **[Ollama](https://ollama.com)** runs a model on your own machine — no key,
> no signup, no cost, nothing leaving the computer — or **Google AI Studio**
> issues a free-tier key, or use paid **Anthropic** / **OpenAI** if you have
> one. Any OpenAI-compatible server (Groq, OpenRouter, LM Studio) works
> through the OpenAI entry too. It is a **per-agent** choice, so a sensible
> setup runs the lecturer locally and leaves the one agent that needs web
> search on a cloud vendor. See [docs/configuration.md](docs/configuration.md).

```
┌──────────┐  find seed   ┌─────────┐   whole graph      ┌──────────────────┐
│  search  │ ───────────▶ │ backend │ ─── seed/refs/ ──▶ │  Semantic Scholar│
│  (S2+LLM)│  (title/id)  │ (Flask) │     citations      │       — or —      │
└──────────┘              └────┬────┘  (one provider)    │     OpenAlex     │
                               │ /api/graph (thin cache)  └──────────────────┘
                               ▼
                     ┌───────────────────────┐
                     │  React + force graph  │  ← the interactive map you explore
                     └───────────────────────┘
```

**Stack:** Python/Flask + uv · [PydanticAI](https://ai.pydantic.dev) agents on
Claude · React + TypeScript (strict) + Vite + Redux Toolkit ·
[`react-force-graph-2d`](https://github.com/vasturiano/react-force-graph) ·
[OpenAlex](https://openalex.org) (citations) +
[Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/) ·
[ar5iv](https://ar5iv.org) + pymupdf-mined open-access PDFs for figures/full text ·
[Hugging Face Papers](https://huggingface.co/papers) for code & artifacts ·
sentence-transformers + sqlite-vec for the local library. Runs locally.

---

## Setup

The toolchain (python, uv, nodejs, trivy) is pinned in `.tool-versions` —
[mise](https://mise.jdx.dev) installs it all with `mise install` (mise reads
the asdf-format file and works on Windows and macOS alike). With mise in
place, `bin/setup.bat` (Windows) or `bin/setup.sh` (macOS/Linux) does the full
bootstrap: pinned tools, a full `uv sync` (dev tooling, the notebook
`research` group, and every optional extra), and the frontend install + build.
Without mise, `uv` and `Node.js` installed any other way work fine too.

> **Three capabilities are optional extras**, because they are most of the
> install and a reader who only wants the graph and the teacher needs none of
> them — core is **83 MB** against **1.0 GB** with everything:
>
> | Extra | Gives you | Cost |
> | --- | --- | --- |
> | *(core)* | the graph explorer and the AI teacher | 83 MB |
> | `pdf` | figures, tables and algorithm boxes mined from PDFs | +54 MB |
> | `corpus` | the offline Semantic Scholar citations corpus | +44 MB |
> | `sources` | search over your own uploaded books and PDFs | +~800 MB |
>
> `bin/setup` installs all of them. To pick: `uv sync --extra pdf`, or
> `pip install 'atlas[pdf,corpus]'`. Nothing breaks without one — the feature
> says it isn't installed and names the command. See
> [docs/first-run.md](docs/first-run.md).

> **Windows pulls a CUDA build of torch** (~1.8GB, from PyTorch's `cu130`
> index) with the `sources` extra, so the local embedder can use a GPU if you
> have one — PyPI's Windows wheel is CPU-only, and that's the whole difference
> between ~80 and ~1500 chunks/s at ingest. It falls back to CPU on a machine
> without a GPU, and macOS/Linux resolve torch from PyPI as usual. See
> [`sources.embedding.device`](docs/configuration.md).

### 1. Configure

```bash
cp config.example.json config.json
```

All configuration lives in `config.json` (gitignored — it holds your keys; no
environment variables, ever). Every field must be *present* and is validated at
startup by Pydantic, so a malformed value fails fast with a clear message — but
the API-key values may be left blank. For the **full value-by-value reference**
(every tunable, its default, and *why* it's there), see
**[docs/configuration.md](docs/configuration.md)**.

The two **data-source keys are completely optional** — Atlas explores the graph
fully without them, just on tighter public rate limits. The **Anthropic key is
the one that unlocks the AI teacher** (lectures, research Q&A, library chat); the
graph explorer runs fine without it, but the Assistant panel needs it.

- **`providers.s2.api_key`** — **optional.** A free
  [Semantic Scholar API key](https://www.semanticscholar.org/product/api) is
  recommended (the keyless pool is tight), but keyless works.
- **`providers.openalex.api_key`** — **optional.** OpenAlex (the citation
  source) runs keyless on its `mailto` polite pool ($0.10/day of metered search
  — plenty for browsing); a free key at
  [openalex.org/settings/api](https://openalex.org/settings/api) lifts it to
  $1/day. Set `providers.openalex.mailto` to your email either way.
- **`llm.providers`** — **one block per LLM vendor; fill in at least one to
  power the agents.** Four are wired, and two of them cost nothing:
  - **`ollama.base_url`** — **free and local.** Point it at a running
    [Ollama](https://ollama.com) server (normally `http://localhost:11434/v1`,
    keep the `/v1`). No key, no signup, no quota, and the conversation never
    leaves your machine. The one trade: a local model can't search the web, so
    that scout goes quiet rather than inventing sources.
  - **`google.api_key`** — **free tier.** A key from
    [Google AI Studio](https://aistudio.google.com/apikey), quota-limited.
    The free quota covers the **flash** models; the pro ones answer
    `429 RESOURCE_EXHAUSTED`, so pick a `gemini-*-flash*` for each agent.
    A key on a *paid* project with its credits spent fails the same way even
    on flash — if everything 429s, check billing rather than the model name.
  - **`anthropic.api_key`** — paid. A
    [Claude API key](https://console.anthropic.com/settings/keys).
  - **`openai.api_key`** / **`openai.base_url`** — paid at OpenAI, but the
    `base_url` points the same adapter at **any OpenAI-compatible server**
    (Groq, OpenRouter, Together, LM Studio), several with free tiers.

  Which vendor each agent uses is set per agent in `llm.agents`
  (`"model": "ollama:qwen3:8b"`), so mixing them is normal — Settings ▸ Agents
  has a one-click "run every agent on" picker for the simple case.

### 2. Build the frontend & run

**Single-server** (serves the built frontend + API together):

```bash
cd frontend && npm install && npm run build && cd ..
uv run atlas serve                      # http://127.0.0.1:5000
uv run atlas serve --port 5050          # ...or another port (--host to expose it)
```

**Development** (two terminals, hot-reloading frontend):

```bash
uv run atlas serve                      # Terminal 1 — API
cd frontend && npm run dev                    # Terminal 2 — http://localhost:5173
```

The Vite dev server proxies `/api/*` to Flask.

---

## Using it

1. **Find a paper** — everything starts in the **chat bar**; there is no
   separate search box. Ask a research question and the assistant goes
   looking, or **type `@`** to name a paper: suggestions appear as you type,
   and picking one attaches that exact paper to your message. What happens
   next depends on what you said — the same rule a pasted id has always
   followed, that naming one paper and nothing else is a statement of intent:

   | What you send | What it does |
   | --- | --- |
   | `@` + a paper you picked | lands on that paper's graph |
   | `@` + words nothing matched | searches properly and lists what it found |
   | a question with `@…` in it | answers *from* that paper, leaving your graph alone |
   | an **arXiv id / URL** | goes straight to the graph, no model involved |

   The suggestions arrive in two passes: your **cached papers appear as you
   type** (a local scan — free, offline, no wait), then a real search fills the
   list out when you pause, re-ranked so the paper whose title most nearly *is*
   what you typed leads. While that second pass runs, the panel says which
   phase it is on — *"Searching Semantic Scholar"*, *"Working out which paper
   'dqn' is"* — rather than a bare spinner. So a paper you have never opened
   is still nameable, and one you have seen shows up instantly. (There was a
   **🔍 Find papers** toggle for this until
   v7.18.0. It made the same words mean different things depending on a
   button's state, and it couldn't express "answer from *this* paper" at all.)
   A search streams: cached papers appear immediately (⚡ **opens instantly**
   marks the ones whose whole neighborhood is cached, so a click costs no API
   call), then the scout's finds arrive lookup by lookup with a trace chip
   each. The **Filters** popover holds a publication-year window (1800 → now)
   and **fields of study** — hard limits, not hints, and they bind the
   assistant's own paper searches too (though never an `@` lookup: you named
   that paper, so a filter has no business hiding it). Citation links on the graph are never
   filtered.
2. **Read the map** — 🟡 seed · 🔵 references · 🟢 citations.
   (💗 found-by-search too, on a session saved before v7.3.0 — free-text hits
   used to be drawn as edgeless pink dots; now the assistant numbers what it
   finds and you promote a paper onto the graph by clicking its citation.)
   **Every paper that cites the seed is one `citations` relation** — from the
   historic giants to work published this month — and **which of them matters is
   yours to decide** with the year and citation-count sliders, not ours to
   decide with a threshold. (They were two relations, *Field Landmarks* and
   *Latest Publications*, until v7.17.0.)

   Behind that one relation are still **two queries**, because they have to be:
   the most-cited citers come back ranked by citation count (under **OpenAlex**,
   the true all-time top-cited from a sorted `cites:` query; under **Semantic
   Scholar**, the whole citation history when the offline corpus serves it or the
   seed's citer list is fully reachable live — the graph's own note names which
   source is behind them; see
   [docs/citation-coverage.md](docs/citation-coverage.md) for how the two sources
   compare), with **how many to show measured per-seed from the real citer pool**
   (an old classic maps out large, a young hot paper stays tight — the STOP rule
   in `services/graph/budget.py`). A second query runs **per recent year**, and
   it is the only reason recent work appears at all: citation counts measure
   attention *and* elapsed time together, so a paper from this year never
   survives a citation ranking. Its start year is **sized per-seed from fitted
   constants** so an old classic's coverage reaches back to meet its dense
   cluster instead of leaving a gap (see `services/graph/bands.py`). (Every term
   here — *landmark*, *band*, *tail edge*, the sizing rules — is defined once,
   with a worked example, in
   [docs/landmark-vocabulary.md](docs/landmark-vocabulary.md).) Node size =
   citations; thick links = influential citations; a
   dashed ring = discovered by the teacher mid-chat. Click a node for
   details (TL;DR, abstract/PDF links, arXiv & Semantic Scholar category
   tags, figures — mined straight from the open-access PDF for journal
   papers, tables and algorithms included — code & artifacts);
   **double-click to re-seed** on it — journal papers included. LaTeX math (`$…$`) renders throughout — titles,
   abstracts, lecture beats, answers, and figure captions — via KaTeX.
3. **Declutter** — a new graph opens onto the *graph*: the controls sit folded
   to a slim bar (click its header to open them) and no paper is selected until
   you click one. Inside: Force ↔ Timeline layouts (x = publication date), relation
   on/off **filter chips**, a dual-knob **year slider** and a dual-knob
   **citation-count slider** (a log-scale min…max window over the papers on
   screen — a display filter, no re-query), drag-to-pin, focus-on-hover, and a
   **Refresh** that busts this seed's day-cached snapshot to re-fetch fresh from
   Semantic Scholar. **Hand-pick a scope** with the node selector:
   **alt-drag** a marquee to add papers to the teacher's scope (additive —
   several sweeps build one cluster), **shift-click** to add/remove one, and
   **alt-click** empty (or **Clear**) to reset. Picked papers ring cyan and the
   rest dim; the teacher then grounds only in your selection. Click the
   **Atlas** brand anytime to go home. By default the app **sizes each graph
   for you** (how many landmark citers to ship, where the Latest bands start —
   per seed); turn **"Size graphs automatically" off** in Settings ▸ Graph to
   have it ship everything it can and size the bands yourself, and each filter
   chip gains a **count slider** to trim how many of that relation you see.
4. **Learn** (the 🎓 Assistant panel):
   - **Lecture** — a narrated tour of the papers **you have on screen**,
     oldest first, over the graph as you built it (lectures never expand it —
     only the research agent does). Ask for it in the chat bar: *"lecture me
     on these"*. (There was a Lecture button in the panel until v7.21.0, and a
     `/lecture` command until v7.23.0.)
     **What it covers is your choice, not a menu's:**
     filter to the references and you get the story of how the field arrived
     here; keep only recent work and you get the current frontier; alt-drag a
     cluster and it narrates those; scope it to a single paper and it teaches
     that paper in chapters, reading its full text for the real math — **any**
     paper, not just the seed, so learning about something you found no longer
     means re-seeding the graph on it first. Four mode buttons did that carving
     for you until v7.17.0 — and in doing so *overrode* whatever you had
     filtered or selected.
     Scoping is not just hand-picking: the **filter chips** (the seed included —
     it has its own chip now), the **year range**, the **citation window** and the
     per-chip count sliders all narrow what a lecture covers, because they all
     narrow what is on screen. And the lecture takes that literally — it will
     not narrate a paper the assistant found earlier if your filters are
     currently hiding it.
     **Or say which papers in the message itself** — *"lecture me on the
     references"*, *"on the citations"*, *"on the seed"*, *"on the Bekenstein
     paper and Hawking 1975"*, *"on this paper: Attention Is All You Need"*.
     A period works too, alone or on top of any of those — *"summarize the
     papers between 2016 and 2017"*, *"the references from the 2010s"*,
     *"everything since 2020"*, *"the last five years"*. Those are selected
     on the map first, brought back on screen if a chip or slider was hiding
     them, and then narrated — so what you see ringed is what the lecture is
     about; when it finishes the ring lets go and the whole lecture stays
     lit instead (click its bubble any time to light it again, Esc to
     clear). A message that names nothing in particular narrates what is on
     screen, as before; one that names papers the graph doesn't have says so
     instead of lecturing on everything.
     **One choice the scope can't make for you, so your words make it:**
     say *history* — *"the story of"*, *"how we got here"* — and the papers
     are told as a chronological arc; otherwise they are grouped into their
     key themes. Summary is the default because a chronological arc is a
     strong claim to make about an arbitrary selection.
     The lecture is nudged to span the whole publication history it is given —
     both ends, not just the oldest, most-cited papers. Length is tunable
     (`min_beats`/`max_beats` in the lecturer's config `extras`, default 7–12).
     **The lecture arrives as a reply in the conversation**, beats and all,
     behind its own caret — open when it lands, folding itself when the next
     lecture arrives, so a conversation with four lectures in it stays
     readable. Beats light up their papers and carry the papers' **real
     figures** inline — click to enlarge.
     So the docked panel is one thing: the conversation, with the 📚 source
     scope and ▽ filters on its caret row. It was a stack of two folding
     sections from v7.10.0, a **Lecture** section above a **Chat** one, which
     was itself a fix for an older shape where the two took turns and asking a
     question tucked away the lecture you were reading.
     **You don't have to say "lecture".** *"Summarize these papers for me"*,
     *"what's the story here?"* — the lecturer answers just the same (the
     last of those arrives framed as history, because that is what it asked
     for). The composer works out which assistant you meant: phrasings that
     name a lecture outright and point at nothing in particular are matched
     outright, and anything less obvious — including *which* papers — is
     settled by a quick classifier: *"summarize this"* is a question about
     the paper you have open, *"summarize these papers"* is a lecture, and
     no pattern tells those apart. Every turn it guessed on says which
     assistant answered and offers the other in a click, so a wrong guess
     costs one line rather than a re-typed question.
   - **Ask** — the research agent answers grounded in what it actually
     reads, streaming its tool steps live (read / expand / search the
     literature / search the web / search your sources / show a figure). It
     consults **every source it has** before it commits to an answer — it
     can't know which one holds it until it looks, and an answer written from
     memory over the textbook you uploaded is the failure that matters. The
     sources also feed each other: the web names things (a chip, a model, a
     lab result) and the literature indexes them, so a web finding sends the
     agent back after **the paper behind the announcement** — the one thing of
     the two you can seed a whole graph on. Answers render in full **Markdown + math**,
     and their inline `[n]` citations are **clickable** — click one to spotlight
     that paper on the graph, click it again to clear. (Lecture beats cite the
     same way.) A tiny glyph on each chip says which click you're about to
     make: **one node lit** spotlights a paper already on the canvas, **three
     nodes wired together** builds that paper's own graph. Answers also cite their whole grounding set — click the bubble
     to re-light them all. A claim drawn from **your own uploaded sources** is
     attributed with its real title and page, resolved server-side rather than
     written out by the model.
     Underneath each answer, a line says what actually grounded it — which of
     your sources, which papers, how much of the web — computed from what the
     agent did, not from what it claims. When nothing grounded it, it says that too: Atlas grounds
     answers in real material, and is honest when it can't. A lecture gets the
     same line, saying how many papers it narrated.
     **And a turn tells you which graph it came from, once that stops being
     obvious.** The conversation survives a graph load — seed something new and
     your questions come with you — so a transcript can hold turns about
     several different graphs at once. Those older turns quietly go inert:
     their citations grey out, because the papers they point at are no longer
     loaded. So any turn answered over a graph other than the one you are
     looking at says *"From the “…” graph"* at the top, which is the difference
     between a dead link and an answer that explains itself.
   - **No graph open? Then the assistant *is* the page.** Atlas opens on a
     centred chat bar — no graph and no uploaded library required — and the
     same agent answers seedless, searching your library through its tools
     rather than being handed passages, so a greeting stays a greeting and a
     real question gets looked up first. Its citations are the way *in*:
     clicking one **maps that paper** — builds its graph, with nothing selected
     on it — and the conversation comes with you rather than being cleared, so a
     survey answer is a doorway into the graph instead of a list of links out
     to someone else's site. When a graph appears the chat collapses into the
     side panel beside it (and a 🎓 button at the top-right of the canvas
     brings it back) without dropping the thread or your place in it.
5. **Your sources** (📚) — drop in PDFs (parallel, with live embedding
   progress) or paste URLs; scope any conversation to a subset of them.
6. **Explorations** — every sitting saves itself, so there is no Save button:
   ask a question and it appears in the rail, named after what you asked, kept
   up to date as you work. Leave an answer running and start another
   exploration — it keeps going in the background and is waiting when you come
   back.
7. **Lost?** Hit the header's **?** for a guided coach-mark tour — it auto-runs
   once on first launch (the search surface) and once more on your first graph
   (the graph tools), spotlighting one control at a time; the bubble's title
   doubles as a jump select that skips straight to whichever tip you came
   back for.

---

## The codebase

The rewrite's first principle: **every package documents itself**. Start at
any folder's `README.md` — e.g. `src/atlas/agents/` (the two tiers —
orchestrators that own an outcome, workers that own one source each — plus
the event protocol and the streaming bridge), `services/sources/` (hybrid retrieval:
FTS5 + vectors + RRF), `frontend/src/README.md` (the render-tree map), or
`frontend/src/store/` (what earns a Redux slice and what stays local).

Quality gates: `uv run nox` runs the whole repo's — pre-commit hooks (file
hygiene; ruff incl. Google-style docstring rules; a repo-local
no-single-letter-identifiers AST check, notebooks included; pydoclint for
Args/Returns completeness; the frontend's prettier + oxlint incl. JSDoc
completeness and `id-length`, the frontend half of that same naming rule),
strict mypy, pytest (`test/`, 669 offline tests), and Vitest
(`frontend/test/`, offline too) — plus `cd frontend && npm run build`
(strict tsc + Vite) for the type/build check.

All of that also runs in CI (`.github/workflows/ci.yml`) on every push to
`main`, across `ubuntu-latest` and `windows-latest`. CI installs the pinned
toolchain from `.tool-versions` with mise, so it runs the *same* python / uv /
node / trivy the developer machines do — and because Trivy is genuinely on
PATH there, the security scan actually runs rather than skipping. It reuses
`bin/setup.sh` rather than restating it, with `ATLAS_SKIP_TORCH=1`, which
drops the `sources` extra: nothing in the gate needs torch, and skipping it
avoids dragging the 37 Linux CUDA packages into every run (1.0 GB → 304 MB).
The `pdf` and `corpus` extras *are* installed there — those tests build real
PDFs and query real Parquet. A second workflow (`release.yml`) fires on
`v*` tags and fails if the tag and `pyproject.toml`'s version disagree.

For the project's direction and past, two living docs sit beside the code:
**[OnePager.md](OnePager.md)** (the vision, the full feature stack, and the
open backlog) and **[docs/history.md](docs/history.md)** (the complete shipped
record, version by version).
