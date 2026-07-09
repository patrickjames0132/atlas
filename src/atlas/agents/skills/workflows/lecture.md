# Workflow: lecture

**Intent:** `lecture` — the user pressed the Lecture button on an open
graph.

**Input:** seed paper, the visible graph nodes, a mode
(`history` | `intuition` | `evolution` | `frontier` | `bridge`), and — bridge
mode only — a target paper.

**Steps:**

1. Scope the visible nodes to the mode's part of the story
   (`_story_nodes`): history ends AT the seed (only papers published in or
   before the seed's year), evolution starts from it (in or after), frontier
   keeps only the configured recency window (the lecturer's
   `frontier_window_months` extra, default ~5 years — the leading edge, any
   relation); intuition and bridge see everything. A lecture never expands
   nodes — pulling new papers in is the researcher's job, on explicit
   questions.
2. Delegate to the **lecturer** with the scoped node set, mode, and
   target. Stream its `Beat` events — each carries a heading, one tight
   narration paragraph, and the node ids to light up — as they arrive.
3. Emit `Done` (or `Error` if the lecturer failed).

**Events, in order:** `Beat`+ `Done` | `Error`
