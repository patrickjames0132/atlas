# Workflow: lecture

**Intent:** `lecture` — the reader asked for one in the chat bar, and the
router sent the message here.

**Input:** seed paper, the nodes the reader has **scoped** — resolved by the
frontend under one contract shared with the research workflow
(`frontend/src/scope/README.md`, v7.24.0): what the message asked for
("lecture me on the references", "…on the Bekenstein paper", "…from the
2010s"), else their hand-picked selection, else what passes their view
filters; held on the canvas as the turn's scope before this is called —
the `framing` (`summary` | `history`) read off the message, and — for a
bridge lecture only — a target paper.

**Steps:**

1. Take the scoped nodes as the subject. The caller sends what is on screen —
   visible after the reader's filters, narrowed to their hand-picked
   selection when there is one — and `_story_nodes` passes it through, sorting
   oldest-first and **adding nothing** (not even the seed: a reader who
   selected one paper wants a lecture on that paper). An empty scope falls
   back to the seed, because a lecture has to be about something. It does
   **not** re-derive a node set of its own: until v7.17.0 four mode buttons each
   carved their own slice out of the graph here, which silently overrode
   whatever the reader had selected. A lecture never expands nodes — pulling
   new papers in is the researcher's job, on explicit questions.
2. Delegate to the **lecturer** with the scoped node set, the framing, and the
   target. Two shapes are read off the request rather than chosen: a target
   means the bridge lecture, and a scope of exactly one paper — any paper, not
   just the seed — means the solo lecture, which teaches that paper in chapters
   from its full text. The framing (summary / history) is the reader's own
   choice and the only input the scope cannot express. Stream its `Beat`
   events — each carries a heading, one tight narration paragraph, and the node
   ids to light up (every paper the beat discusses, including the ones it only
   cites inline) — as they arrive.
3. Emit `Done` (or `Error` if the lecturer failed).

**Events, in order:** `Beat`+ `Done` | `Error`
