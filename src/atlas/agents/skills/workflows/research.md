# Workflow: research

**Intent:** `research` — the user asked a question. The one Q&A workflow;
since v6.7.0 it serves both chats, with a graph open and without (the
`librarian` intent and its playbook were retired with the agent).

**Input:** the question, the session's conversation history, an optional
library scope (`source_ids`), and — when a graph is open — the seed paper,
the visible nodes, the provider, and any lectures already played:

- `None` — no scope; the researcher may search the whole library.
- a present list — the researcher is pinned to exactly those sources: only they
  appear in its context, and every source search is forced to them.
- an empty list — "no sources selected": source search is disabled
  entirely.

**No seed and no nodes is legitimate**, not an error — that's the graph-free
chat. The researcher runs with an empty numbered list, which `find_papers`
can still fill.

**Steps:**

1. Delegate to the **researcher** with all inputs. The researcher first
   decides whether the turn is `conversational` (a greeting, a thank-you, a
   meta question — no tools, just a reply) or `answered`. For an `answered`
   turn with a library present, it **must reach retrieval before it commits
   to an answer**; an output validator bounces one that doesn't (see
   `researcher/main.py`'s `_must_have_looked`). It then investigates via its
   tools — reading papers, expanding the graph, searching S2, the web and the
   library, attaching figures — each step within its budget. The sources feed
   each other: when the web scout names something specific, the researcher
   sends the paper scout after the paper behind that name, because only a
   paper can be seeded into a graph (see the researcher's README, "The join").
2. Forward its events as they arrive: `SourceRefs` (the numbered library the
   answer's `[Sn]` markers resolve against, ahead of the prose), `Trace`
   (each tool step, so the user watches the agent work), `Discovery` (papers
   expansion/search added — the frontend merges them into the live graph),
   `Figure` (an attached figure to interleave at its `<<FIG n>>` marker),
   `Token` (answer prose).
3. Emit `Cited` (the node ids the answer draws on — papers actually read
   plus any named in the structured result) and `Provenance` (the observed
   record of what grounded the answer), then `Done` (or `Error`).

**Events, in order:** `SourceRefs`? (`Trace` | `Discovery` | `Figure`)*
`Token`+ `Cited` `Provenance` `Done` | `Error`

**History:** the routes layer persists the turn (question + final prose)
only on success, capped to the recent window, with `<<FIG n>>` markers
stripped — they're render directives, not conversation content. The two
chat surfaces keep separate stores, so a graph conversation and a
library-only one never cross-contaminate context.
