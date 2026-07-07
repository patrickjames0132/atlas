# Workflow: lecture

**Intent:** `lecture` — the user pressed the Lecture button on an open
graph.

**Input:** seed paper, the visible graph nodes, a mode
(`history` | `intuition` | `bridge`), and — bridge mode only — a target
paper.

**Steps:**

1. **History mode only, when the seed has an id:** run the
   `history_backfill` tool first. It walks backward through references from
   the oldest visible papers (day-cached hops, capped per hop, stopping at a
   year floor or the hop budget) so the story can open at the field's roots
   instead of mid-stream. Stream its `Trace` events (hop progress) and
   `Discovery` events (ancestor nodes + edges for the live graph), and merge
   the discovered nodes into the node set the lecturer will narrate over.
   S2 failures on a hop are noted and skipped — a failed hop never aborts
   the lecture. If nothing older was found, one final `Trace` says so.
2. Delegate to the **lecturer** with the (possibly enriched) node set, mode,
   and target. Stream its `Beat` events — each carries a heading, one tight
   narration paragraph, and the node ids to light up — as they arrive.
3. Emit `Done` (or `Error` if the lecturer failed; backfill problems are
   never fatal).

**Events, in order:** [`Trace`* `Discovery`*] `Beat`+ `Done` | `Error`
