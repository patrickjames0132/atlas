# `src/library`

The Sources drawer: manage the local semantic library the teacher searches —
upload PDFs (several at once), paste a URL, list, remove.

## Design decisions worth knowing

- **Parallel uploads, capped at 3** (`runPool`, an in-file single-consumer
  helper per the hybrid rule), with per-file progress rows: successes drop
  out once they land in the library list below; **failures linger with
  their messages** — the backend's user-facing `SourceError` text
  ("no extractable text — is it scanned?") surfacing exactly where the
  user needs it.
- **The availability warning** renders off the list response's `available`
  flag — the UI explains a disabled semantic search instead of failing
  mysteriously. (Ingestion genuinely requires embeddings; chat retrieval
  degrades without them.)
- All state is drawer-local (`useState` where it's used); the drawer
  refreshes its list on every open.

## Who uses it / verified

Rendered by the shell behind the header's 📚 toggle. `tsc` strict +
oxlint; upload progress and failure-lingering are browser-milestone items.
