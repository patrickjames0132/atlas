# `settings/` — the settings modal

A config-file editor in the style of Claude Desktop's settings window: a left
sidebar (search field + grouped nav items) and a right content pane of
label-left / control-right rows separated by hairline dividers. Opened from
the header's ⚙ button (`Atlas.tsx` holds the visibility state, like the other
overlays).

## Design decisions worth knowing

- **The config file is the single source of truth.** The modal loads the
  active `config.json` on open (`GET /api/settings`), edits a **local draft**,
  and writes the *whole* object back on Save (`PUT /api/settings`). The server
  validates before writing anything and applies accepted writes to the running
  app in place — no restart; a rejected save comes back as a **per-field**
  error list (`{path, message}` each), rendered in the footer as one readable
  line per bad setting rather than a wall of raw Pydantic text. Hand-edits and modal edits are therefore
  the same thing, and sections the modal doesn't render round-trip untouched
  (the `AtlasConfig` type keeps unknown sections via index signatures).
- **Explicit Save/Discard, not autosave.** A dirty draft (deep-compare against
  the last-loaded config) raises a footer bar; nothing touches the file until
  Save. Cheap to reason about, and a bad edit can't half-apply.
- **The config-file row is different** — it sits at the bottom of *General*
  (it's a setting about the file, not a section of its own) and applies
  *immediately* via `PUT /api/settings/location`, because it isn't part of
  the file's contents; the modal then reloads everything from the new file.
- **Number fields carry their config field's floor** (`NumberInput`): the
  spinner stops there and a typed-in lower value is clamped, so a bounded
  knob can't reach the save bar looking valid. The server still validates —
  this is the second line, not the only one.
- **The Graph section is browser state, not the config file.** Its four rows
  (`adaptive` plus the three band-shape numbers) read and write
  `graph/buildShape.ts` directly and apply **immediately**, so they never
  appear in the Save bar — the same write-through the config-file location row
  uses, for the same reason: they aren't part of the file's contents. The
  build shape belongs to the person exploring and changes between one build and
  the next, so it rides on each graph request instead (see `graph/README.md`).
  They're rendered as small components that call `useBuildShape()` themselves,
  which is why the `RowDef.control` signature didn't need widening for
  non-config rows.
- **Two rebuild timings, on purpose.** The `adaptive` switch rebuilds the graph
  **immediately** — one click is a complete intent. The three band-shape number
  inputs rebuild on **modal close**, because they write on every keystroke and
  rebuilding per character would hammer the provider. Neither is wired through
  this component: `Atlas.tsx` watches the store (the switch via a `useBuildShape`
  effect, the numbers via a `sameBuild` comparison on close), so the modal stays
  a settings editor that knows nothing about the graph.
- **`adaptive` is a switch, not a checkbox** (`.settings-switch`) — a real
  checkbox stays in the markup for keyboard and screen readers, visually hidden,
  with the track and knob painted from `:checked` / `:focus-visible`.
- **The band fields grey out — but keep showing their values — while automatic
  sizing is on** (`input:disabled` in `settings.css`), so it reads as "this is
  what's in use, tunable once you switch sizing off" rather than as empty or
  still-editable. The cluster-start field's `auto` placeholder already looked
  muted; this brings the two number fields to match.
- **The citations-corpus path lives under Data Providers ▸ Semantic Scholar**,
  not a section of its own — it's an S2 setting (`storage.s2_corpus`, the offline
  corpus the s2 provider draws its citers from), so it sits with the rest of
  the S2 connection knobs.
- **General carries the browser-level defaults** — default data source
  and colour theme — which config *seeds* and an in-app control then
  overrides per browser (the header dropdown, the ☀/☾ toggle). Both are
  defaults, not locks; see `ui/README.md` for the theme store's rule.
- **Rows are data too** (`ROW_DEFS`): each row carries its section, group
  heading, label/hint text, and control renderer — one registry drives
  rendering *and* the PyCharm-style search, which reaches individual settings
  (nav narrows to sections with a matching row; the pane shows the matching
  rows; the active section auto-jumps to the first hit).
- **The 📁 button is a backend picker.** A browser's file input never reveals
  absolute paths, so `POST /api/settings/pick` opens the OS chooser on the
  server's machine (same machine in this app's model) and the modal switches
  to whatever was picked. A missing default `config.json` is auto-created
  from the example server-side, so there's always a writable file.
- **Agent knobs edit `llm.agents` extras**: a blank input shows the code
  default as a placeholder; typing writes an override into the entry's
  `extras`; clearing deletes the override.
- **Every section carries a one-paragraph `blurb`** saying what it is for.
- **Library is a section of four sub-pages** (since v7.29.0; the config
  block is `sources`, the app calls the feature the Library): *General*
  holds the master switch `semantic_enabled`, and *Embedding*, *Chunking*
  and *Retrieval* mirror the three typed sub-blocks of `config.sources`.
  The switch sat on the section's landing page at first, above the links —
  the reasoning being that a sub-page of one field wastes space — and moved
  to its own General page because a control on a landing page reads as
  part of the navigation. The row filter still supports a section's own
  rows: in a section with `pages`, a row with no `page` shows on the landing
  page only, never repeated on every sub-page; nothing uses it now. The number
  fields (`SourcesNumber`) refuse to be cleared, unlike an agent knob: the
  file always carries a value here, there is no code default to fall back
  to. The backend's embedder cache is keyed on the config that loaded it, so
  a saved model/device edit applies live (see `services/sources/README.md`).
- **Every vendor group ends in an "Apply Default Models" button** (v7.29.0,
  `VendorApply`, a `bare` row — no label column, the control alone where a
  label would start) that puts the **lecturer and researcher** on the
  vendor's *advanced* model and the **summarizer and both scouts** on its
  *light* one (`ADVANCED_AGENTS`), the same split `config.example.json`
  ships with, leaving the knobs alone — and then **moves the modal to Agent
  Settings**, where every agent's row shows the new vendor: the change is
  visible where it happened, not implied by a Save bar. That is why
  `RowDef.control` takes a fourth argument, `goToPage`. The button's tooltip
  names both picks before it is pressed; with no credential in the draft or
  nothing listed it is disabled and the tooltip says why (enter the key and
  Save, or the key/server could not be listed). It was briefly a labelled
  row, "Run every agent here", with a caption line under the button — the
  label only restated the button and the caption was clutter. The picks are the backend's:
  `GET /api/settings/models` returns `tiers` per listed vendor, ranked by name
  on the newest-first listing (`routes/settings.py`'s `_tiers`: Sonnet/Haiku,
  mainline gpt-/-mini, Flash/Flash-Lite — never Pro on Google, it 429s on the
  free tier — and Ollama by parameter count). Two earlier shapes are worth
  not retrying: a row of its own at the top of the page (vendor select +
  model select + Apply) was bulky, and one model for every agent was the wrong
  idea anyway — the long generations and the short structured calls want
  different models; and a pill button on the group heading beside a cost
  badge looked stray. Under the credentials, it reads as the next step after
  entering a key.
- **The modal has its own tour** (v7.29.0): the ringed **?** beside the ✕
  (`.settings-help`) mounts the shared `Tour` engine over `SETTINGS_TOUR`
  (`tour/steps.ts`), *inside* the modal so it stacks above it. Steps carry a
  `stage` of `<section>` or `<section>/<page>`, which `onTourStage` turns into
  a nav click (and clears any search) before the step is measured, so the walk
  drives the modal's own nav; targets are `data-tour` anchors on the search
  box, the nav, the help button, and individual rows via `RowDef.tour`. It
  auto-runs once ever on the first open (`TOUR_KEYS.settings`), like the app's
  two phases, then only from the button; Done, Skip, ✕ and Esc all mark it
  seen.
- **The Agents section is two nav sub-pages of foldable groups** (since
  v7.13.0): *Model Providers* and *Agent Settings*, reached from the sidebar
  tree rather than a tab strip inside the pane. Sub-pages show only while their
  section is selected — the nav is somewhere to navigate, not an outline of
  everything — and the pane's heading becomes a breadcrumb (`Agents › Model
  Providers`). Tabs were tried first and framed the two as views of one thing,
  which they aren't: one holds vendor credentials, the other per-agent tuning.
- **A section with sub-pages opens on its own landing page** (`page === ''`):
  the blurb plus a plain text link per sub-page. Dropping the reader straight
  into an arbitrary first child never says what the section as a whole is, and
  the landing page costs one click to skip. Clicking the parent in the nav
  always returns there. The links are links, not cards — a boxed row per
  sub-page reads as a control worth deliberating over, when these are only the
  way through.
- **An agent group opens with what the agent is** (`GROUP_BLURBS`, v7.29.0):
  an italic, muted paragraph under the heading, above the knobs, with clear
  air before the first row (a left rule and a translucent card were tried
  and dropped as too cute). The Model row's hint
  used to carry the job description and it was the wrong place — that row is
  only the LLM driving the agent, and its hint now says so plus what kind of
  model suits (small and fast for the scouts, quality for the lecturer and
  researcher, a cloud vendor for the web scout). The description is the
  group's because the whole group *is* the agent.
- **Group headings fold their own rows.** Both sub-pages keep the modal's
  ordinary label-hint-control row; what folds is the heading, so the layout
  matches every other section and long pages can still be tidied. Groups are
  **open on arrival** — folding is for putting away a section you are done
  with, not a wall to dismantle first — so state is tracked as the set of
  *folded* names. The heading is a `<button>` and therefore needs an explicit
  `font: inherit`, or it renders in the platform UI font.
- **One group per vendor, every vendor listed.** Every vendor the backend
  can build gets a group whether configured or not: the two free paths are
  precisely what a newcomer has *not* set up, so listing only what already
  works would hide the options most worth finding. `GET /api/settings/models`
  returns `{models: {vendor: [...]}, vendors: [...], known: [...], tiers}`,
  and `known` is what drives that. (The headings carried a cost badge —
  `paid` / `free tier` — from v7.13.0 to v7.29.0; it went as clutter, and the
  free vendors' key-field hints already say they cost nothing.) OpenAI's
  `base_url` — the OpenAI-compatible-server hook — is config-file-only since
  v7.29.0: a row for it was superfluous for the one-key common case.
- **An agent's model is two controls, not one string.** The single
  `"vendor:model"` dropdown this replaced made the vendor invisible — a prefix
  inside a long string — where the real fact is that **each agent picks its own
  vendor**. Changing vendor rewrites both halves, since an Anthropic model name
  under an `ollama:` prefix is a config that cannot run. A value the listing no
  longer offers is preserved as its own option at either level rather than
  silently rewritten.
- **Both controls are `<select>`s, and the model list is fetched live**
  (v7.14.0). The model names used to be hardcoded server-side for Google and
  OpenAI, and that list rotted: it shipped in v7.13.0 naming the 2.5-era Gemini
  models and was answering `404 ... no longer available to new users` within
  weeks, with a dropdown offering nothing but dead options. The fix belongs in
  the backend, not the control — `routes/settings.py` now asks every vendor's
  own API what it has (see its `KNOWN_MODELS`, demoted to an offline
  fallback). A brief attempt to solve it in the UI instead, by making the model
  field an `<input list=>` combobox, is worth knowing about so nobody retries
  it: a `<datalist>` is filtered by whatever text the box already holds, so a
  field set to `claude-haiku-4-5` offered the two ids containing that string
  and hid the other eight. A dropdown shows everything, which is the job.
- **Search ignores sub-pages and folding both.** A query has to reach every
  matching row, and an unselected sub-page or a fold hiding one is the thing
  search exists to avoid.

## Verified by

`frontend/test/settings/` (drafting, dirty detection, save/error paths, the
location switch, the Library landing/sub-page split and its edits, a
vendor's one-click crew, the tour's auto-run and ?-launch) plus the backend
contract in `test/atlas/routes/test_settings.py`.


## The one row that isn't a setting: Drop cache (v7.6.0)

Every other row edits `draft` and is saved by the modal's Save. `DropCacheButton`
edits nothing — it's an **action**, and it takes effect the moment you confirm.
It lives here anyway because "empty the derived data" is app maintenance, which
is what this modal is for, and because there is nowhere better: the graph
toolbar is about the graph you can see, not the ones on disk.

Three decisions inside it:

- **Two-step, not `window.confirm`.** A native dialog blocks the whole page
  (and any automated session driving it), and the warning worth showing is too
  specific for a one-liner: what goes, and — the part a reader actually needs —
  what emphatically does not. **Saved sessions and the library are untouched.**
  A cache entry can be refetched; a session is the only copy of something the
  reader made, and lives in a different store.
- **It reports a count** (`Dropped 1,204 cached entries.` / `Already empty.`)
  rather than claiming success blankly, so you can tell a real drop from a
  no-op.
- **It borrows the row controls' shape rather than inventing one.** The modal
  styles its controls by element selector (`.settings-row-control input,
  select`), and `<button>` was never in that list — so this first shipped as a
  raw platform button, white-on-dark and obviously foreign. Same padding,
  radius, border and background now; only the destructive confirm differs, in
  red, and it sits behind Cancel in the reading order.
