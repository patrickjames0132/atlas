# Workflow: research

**Intent:** `research` — the user asked a question with a graph open.

**Input:** the question, seed paper, the visible graph nodes, the session's
conversation history, and an optional library scope (`source_ids`):

- `None` — no scope; the researcher may search the whole library.
- a present list — the researcher is pinned to exactly those sources: only they
  appear in its context, and every source search is forced to them.
- an empty list — "no sources selected": source search is disabled
  entirely.

**Steps:**

1. Delegate to the **researcher** with all inputs. The researcher investigates via
   its tools (reading papers, expanding the graph, searching S2 and the
   library, attaching figures), each step within its budget.
2. Forward its events as they arrive: `Trace` (each tool step, so the user
   watches the agent work), `Discovery` (papers expansion/search added —
   the frontend merges them into the live graph), `Figure` (an attached
   figure to interleave at its `<<FIG n>>` marker), `Token` (answer prose).
3. Emit `Cited` (the node ids the answer draws on — papers actually read
   plus any named in the structured result), then `Done` (or `Error`).

**Events, in order:** (`Trace` | `Discovery` | `Figure`)* `Token`+ `Cited`
`Done` | `Error`

**History:** the routes layer persists the turn (question + final prose)
only on success, capped to the recent window, with `<<FIG n>>` markers
stripped — they're render directives, not conversation content.
