# `src/library`

The Sources drawer: manage the local semantic library the teacher searches —
upload PDFs (several at once), paste a URL, list, remove.

## Design decisions worth knowing

- **Real progress bars** (browser-milestone addition): the ingest endpoint
  streams `{done, total}` chunks-embedded frames, and each upload row (and
  the URL busy row) renders a determinate bar + percent. Before the first
  progress frame the row reads "reading…" — extraction/chunking happens
  before the bar starts moving.
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
