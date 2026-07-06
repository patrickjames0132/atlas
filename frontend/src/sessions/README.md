# `src/sessions`

The Sessions drawer: name-and-save the current workspace, reopen or update
a saved one, delete old ones. Restoring costs no API calls.

## Design decisions worth knowing

- **Save/restore are the parent's job** — the drawer never sees the live
  graph or chat; it calls `onSave(name, id?)` / `onOpen(id)` and the shell
  (which owns that state) does the work. The drawer owns only its list,
  the name field, and busy/error flags.
- **Update = overwrite in place**: `onSave` with an existing id keeps the
  session's name and bumps it to the top (list is ordered by last-updated).
- The save-name pre-fills with the current seed's title on each open.
- Borrows `sources.css` for the shared drawer chrome, adding only its own
  row-action styles — the two drawers deliberately look alike.

## Who uses it / verified

Rendered by the shell behind the header's 🗂 toggle. `tsc` strict + oxlint;
save → reopen → update round trips are browser-milestone items.
