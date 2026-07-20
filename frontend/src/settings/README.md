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

## Verified by

`frontend/test/settings/` (drafting, dirty detection, save/error paths, the
location switch) plus the backend contract in `test/atlas/routes/test_settings.py`.
