/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Shared exploration and thread rows, with consistent rename/delete controls.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { useEffect, useRef, useState } from 'react'
import type { SavedSessionMeta } from '../api'
/** Props for {@link SessionRow}. */
interface SessionRowProps {
  session: Pick<SavedSessionMeta, 'name'>
  active: boolean
  /** This exploration still has a stream running (here or in the background). */
  working?: boolean
  editable?: boolean
  expanded?: boolean
  onToggle?: () => void
  onOpen: () => void
  onRename: (name: string) => void
  onDelete: () => void
}

/**
 * One saved exploration in the rail: a click opens it, a ⋮ menu renames or
 * deletes it.
 *
 * Rename edits **in place** rather than in a modal — the row is the label, so
 * editing it where it sits is both shorter and clearer about what is being
 * named. Enter commits, Escape abandons, and blur commits too (a click
 * elsewhere reads as "done", not "cancel").
 *
 * @param session The saved exploration's metadata row.
 * @param active  This exploration is the one currently open.
 * @param working This exploration still has a stream running.
 * @param editable Whether rename and delete are available.
 * @param expanded Whether child threads are shown.
 * @param onToggle Toggle child threads.
 * @param onOpen  Restore this exploration.
 * @param onRename Commit a new name.
 * @param onDelete Remove it.
 * @returns The rendered row.
 */
export default function SessionRow({
  session,
  active,
  working = false,
  editable = true,
  expanded,
  onToggle,
  onOpen,
  onRename,
  onDelete,
}: SessionRowProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.name)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  /** Commit the edited name, unless it's unchanged. */
  const commit = () => {
    setEditing(false)
    const next = draft.trim()
    if (next && next !== session.name) onRename(next)
    else setDraft(session.name)
  }

  if (editing) {
    return (
      <div className="rail-item rail-session editing">
        <input
          ref={inputRef}
          className="rail-rename"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') commit()
            // Escape abandons — and stops here, or the graph's own Escape
            // handler would clear the canvas selection behind the rail.
            if (event.key === 'Escape') {
              event.stopPropagation()
              setDraft(session.name)
              setEditing(false)
            }
          }}
          onBlur={commit}
          aria-label={`Rename ${session.name}`}
        />
      </div>
    )
  }

  return (
    <div className={`rail-item rail-session${active ? ' active' : ''}`}>
      {onToggle && (
        <button
          type="button"
          className="rail-caret"
          aria-label={`${expanded ? 'Collapse' : 'Expand'} ${session.name}`}
          aria-expanded={expanded}
          onClick={onToggle}
        >
          <svg
            viewBox="0 0 16 16"
            aria-hidden="true"
            style={{ transform: expanded ? 'rotate(90deg)' : undefined }}
          >
            <path d="m6 3 5 5-5 5" />
          </svg>
        </button>
      )}
      <button type="button" className="rail-session-open" onClick={onOpen} title={session.name}>
        {!onToggle && <span className="rail-dot" aria-hidden="true" />}
        <span className="rail-label">{session.name}</span>
        {/* Deliberately the only status the rail shows. It is not chatter
            about saving — it is the one thing a reader cannot otherwise know
            once they have walked away from a running answer. */}
        {working && (
          <span className="rail-working" role="status" aria-label="Still working">
            <span className="rail-working-dot" />
            <span className="rail-working-dot" />
            <span className="rail-working-dot" />
          </span>
        )}
      </button>
      {editable && (
        <button
          type="button"
          className="rail-more"
          onClick={() => setMenuOpen((prev) => !prev)}
          aria-label={`Options for ${session.name}`}
          aria-expanded={menuOpen}
        >
          ⋮
        </button>
      )}
      {menuOpen && (
        <>
          {/* A click anywhere else closes it — cheaper and more reliable than
              a document listener, and it can't leak past unmount. */}
          <div className="rail-menu-scrim" onClick={() => setMenuOpen(false)} />
          <div className="rail-menu" role="menu">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false)
                setDraft(session.name)
                setEditing(true)
              }}
            >
              ✎ Rename
            </button>
            <button
              type="button"
              role="menuitem"
              className="danger"
              onClick={() => {
                setMenuOpen(false)
                onDelete()
              }}
            >
              🗑 Delete
            </button>
          </div>
        </>
      )}
    </div>
  )
}
