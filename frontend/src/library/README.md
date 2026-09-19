# `src/library`

The Library modal (user-facing label "Library" / "Your library" since
2026-07-14; the component keeps its original `Sources` name): manage the
local semantic library the teacher searches — upload PDFs (several at once),
paste a URL, list, remove.

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
- Upload/ingest progress state is modal-local (`useState` where it's used),
  but **the source list lives in the store's `library` slice**: every
  mutation here (upload, URL ingest, delete) re-loads it through
  `loadLibrary`, and the modal re-loads on open — so the teacher panel's
  source-scope picker sees a new source the moment it lands instead of
  after a page reload.

## Who uses it / verified

Rendered by the shell behind the header's 📚 toggle. `tsc` strict +
oxlint; upload progress and failure-lingering are browser-milestone items.


## A modal (v7.32.0)

The Library is a centred dialog over the workspace, the same shell as
Settings (`.library-backdrop` / `.library-modal` in `sources.css` mirror
`settings.css`'s scrim and card; only the size differs, this being one
column). It has had three shapes: a right-hand drawer to v7.8.0, then a
**main-pane view** the rail switched to — the drawer's 400px was too narrow
for a growing list, and the view hid the workspace, which the `variant` prop
let the tour keep staging as a drawer — and now the modal, because the rail's
two management entries, Library and Settings, should open the same kind of
thing, and a full-pane detour for a list-and-upload form was more page than
the job needed. The `variant` prop and the `ShellView` state that drove the
pane went with it.

Whatever the wrapper, the workspace behind it stays **mounted** and untouched.
Visiting the library is a detour, not a teardown: unmounting would cost the
graph and the conversation, which is the same reasoning that keeps `Teacher`
at one position in the tree.
