# Workflow: librarian

**Intent:** `librarian` — the user asked a question in the offline library
chat. No graph required.

**Input:** the question, the session's conversation history (a separate
store from the graph Q&A — the two chats never cross-contaminate context),
and an optional `source_ids` scope (same semantics as the research workflow:
`None` = whole library, present list = only those, empty = nothing).

**Steps:**

1. **Retrieve first, deterministically:** run `services.sources.search`
   (RRF-fused FTS5 + vector search) over the scoped library with the
   question as the query. Emit one `Trace` naming how many passages were
   found and the distinct source titles they came from.
2. **Nothing found:** emit a friendly "couldn't find anything in your
   library — rephrase or upload a source" answer as `Token` prose and stop.
   The model is never engaged.
3. Otherwise delegate to the **librarian** with the passages as grounding
   context plus the question and history. Stream its `Token` prose — it
   answers only from the passages, attributing inline by source title and
   page.
4. Emit `Done` (or `Error`).

**Events, in order:** `Trace` `Token`+ `Done` | `Error`

**History:** persisted by the routes layer on success, in the
library-chat's own session store.
