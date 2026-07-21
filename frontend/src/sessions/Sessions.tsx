/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The Sessions drawer (Phase 4): save the current workspace — the graph as it
 * stands (every node/edge, including the ones the agent discovered) plus the
 * teacher transcript — and reopen a saved one later without rebuilding it from
 * Semantic Scholar. Listing/deleting is handled here; saving and restoring are
 * the parent's job (it holds the live graph + chat), reached via onSave/onOpen.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { useCallback, useEffect, useState } from 'react'
import { deleteSession, listSessions, type SavedSessionMeta } from '../api'
import '../library/sources.css'
import './sessions.css'

/**
 * A saved session's timestamp as a short human date.
 *
 * @param ts The Unix timestamp (seconds).
 * @returns E.g. "Jul 9, 2026".
 */
function when(ts: number): string {
  const date = new Date(ts * 1000)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * Render the Sessions drawer: save the workspace, reopen or delete a save.
 *
 * @returns The drawer, or null while closed.
 */
export default function Sessions({
  open,
  onClose,
  onSave,
  onOpen,
  canSave,
  defaultName,
}: {
  open: boolean
  onClose: () => void
  // Save the current workspace; an id overwrites that saved session in place.
  onSave: (name: string, id?: string) => Promise<SavedSessionMeta>
  onOpen: (id: string) => void
  canSave: boolean
  defaultName: string
}) {
  const [items, setItems] = useState<SavedSessionMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setItems(await listSessions())
    setLoading(false)
  }, [])

  // Refresh the list and pre-fill the save name with the current seed each open.
  useEffect(() => {
    if (!open) return
    refresh()
    setName(defaultName)
    setError(null)
  }, [open, refresh, defaultName])

  const onSaveClick = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault()
      if (!canSave || busy) return
      setError(null)
      setBusy(true)
      try {
        await onSave(name.trim() || defaultName || 'Untitled session')
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(false)
      }
    },
    [canSave, busy, onSave, name, defaultName, refresh],
  )

  // Overwrite an existing saved session with the current workspace, keeping its
  // name. It jumps to the top of the list (ordered by last-updated) on refresh.
  const onUpdate = useCallback(
    async (session: SavedSessionMeta) => {
      if (!canSave || busy) return
      setError(null)
      setBusy(true)
      try {
        await onSave(session.name, session.id)
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(false)
      }
    },
    [canSave, busy, onSave, refresh],
  )

  const onDelete = useCallback(
    async (id: string) => {
      await deleteSession(id)
      await refresh()
    },
    [refresh],
  )

  if (!open) return null

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside
        className="sources-drawer"
        data-tour="sessions-panel"
        role="dialog"
        aria-label="Saved sessions"
      >
        <header className="sources-head">
          <span>Saved sessions</span>
          <button className="link-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <p className="sources-blurb">
          Save the current graph — including papers the teacher discovered — and its chat, then
          reopen it anytime. Restoring costs no API calls.
        </p>

        <form className="src-url session-save" onSubmit={onSaveClick}>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={canSave ? 'Name this session…' : 'Load a graph to save it'}
            aria-label="Session name"
            disabled={!canSave || busy}
          />
          <button className="src-btn" type="submit" disabled={!canSave || busy}>
            {busy ? 'Saving…' : '💾 Save'}
          </button>
        </form>
        {error && <div className="sources-error">{error}</div>}

        <div className="sources-list">
          {loading && items.length === 0 ? (
            <div className="sources-empty">Loading…</div>
          ) : items.length === 0 ? (
            <div className="sources-empty">No saved sessions yet.</div>
          ) : (
            items.map((session) => (
              <div key={session.id} className="source-row">
                <button
                  className="session-open"
                  onClick={() => onOpen(session.id)}
                  title="Reopen this graph + chat"
                >
                  <div className="source-title">🗂 {session.name}</div>
                  <div className="source-sub">
                    {session.seed_title ? `${session.seed_title} · ` : ''}
                    {session.n_nodes} paper{session.n_nodes === 1 ? '' : 's'} ·{' '}
                    {when(session.updated_at)}
                  </div>
                </button>
                <div className="session-row-actions">
                  {canSave && (
                    <button
                      className="link-btn"
                      onClick={() => onUpdate(session)}
                      disabled={busy}
                      title="Overwrite this saved session with the current graph + chat"
                    >
                      Update
                    </button>
                  )}
                  <button
                    className="link-btn"
                    onClick={() => onDelete(session.id)}
                    aria-label={`Delete ${session.name}`}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  )
}
