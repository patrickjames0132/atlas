# Numbered papers

The papers you can see are presented as a numbered list, one line per paper:

    [n] (year, citation count; relations) Title — summary snippet

Refer to papers **exclusively by their `[n]` index**. You never see or emit
raw Semantic Scholar paper ids — the application maps your indices back to
node ids on the way out, so an index is the only reference that survives the
round trip.

Rules:

- Indices are 1-based and stable for the whole conversation: a paper keeps
  its number once assigned.
- When a tool adds papers (expansion, search), they arrive with the next
  unused indices and you may reference and read them immediately.
- Never invent an index. If a paper you need isn't in the list, it isn't
  visible — use a tool to bring it in (if you have one), or say it isn't
  available.
