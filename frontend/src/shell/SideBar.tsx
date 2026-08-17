/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The app's left rail: what the header used to be, turned on its side and
 * made collapsible — the shape ChatGPT and Claude both settled on, and for
 * the same reason. A top bar spends the scarcest axis (vertical) on chrome
 * that is mostly idle, while a rail spends the plentiful one and can be
 * folded away entirely when the map wants the room.
 *
 * It holds three bands:
 *   • **top** — the collapse toggle, and "New graph", which clears the
 *     workspace back to the landing chat;
 *   • **middle** — the saved sessions, listed like a chat history, each with
 *     a ⋮ menu for rename/delete. This is the band that made the rail worth
 *     building: saved graphs used to hide behind a drawer button, and a
 *     thing you accumulate should be visible;
 *   • **bottom** — Library, Settings, theme, tour.
 *
 * Collapsed it becomes an icon rail. Every entry keeps the glyph it already
 * had in the header (📚 🗂 ⚙ ☀/☾ ?), so folding the rail hides words rather
 * than changing vocabulary.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useRef, useState } from 'react'
import { useResizablePanel } from '../ui/useResizablePanel'
import { PROVIDER_LABEL } from '../api'
import type { Provider, SavedSessionMeta } from '../api'
import './shell.css'

/** The folded rail's width, px — `.rail.collapsed` in `shell.css`, repeated
 *  here because the unfold-by-drag has to measure from what is on screen. */
const RAIL_COLLAPSED_WIDTH = 56

/** The main-pane view a rail entry switches to. */
export type ShellView = 'workspace' | 'library'

/** Props for {@link SideBar}. */
export interface SideBarProps {
  /** The rail is expanded (labels visible); false is the icon rail. */
  open: boolean
  onToggle: () => void
  /** Which main-pane view is showing — drives the active entry. */
  view: ShellView
  onView: (view: ShellView) => void
  /** Clear the workspace and go back to the landing chat. */
  onNewGraph: () => void
  /** The saved sessions, newest-updated first. */
  sessions: SavedSessionMeta[]
  /** The session currently open, so the list can mark it. */
  openSessionId: string | null
  onOpenSession: (id: string) => void
  onRenameSession: (id: string, name: string) => void
  onDeleteSession: (id: string) => void
  /** Save the current workspace as a new session — hidden with no graph. */
  onSaveSession?: () => void
  /** A save just landed: the ＋ becomes a ✓ for a beat. Collapsed, this is
   *  the only feedback there is — the row has no label to change and the
   *  saved list it feeds isn't rendered. */
  justSaved?: boolean
  onOpenSettings: () => void
  onStartTour: () => void
  /** 'dark' | 'light' — decides which glyph the theme button shows. */
  theme: string
  onToggleTheme: () => void
  /** The academic backend graphs are built from — and, with no graph open,
   *  the one the assistant's paper searches run against. */
  provider: Provider
  onProviderChange: (provider: Provider) => void
  /** A build is in flight, so switching backend is disabled. */
  loadingGraph: boolean
  /** The open graph's seed title, shown under the brand (null = no graph). */
  seedTitle: string | null
}

/** Props for {@link ProviderPicker}. */
interface ProviderPickerProps {
  provider: Provider
  onChange: (provider: Provider) => void
  disabled: boolean
}

/**
 * The data source as a single icon + popup, for the collapsed rail.
 *
 * The expanded rail shows a labelled `<select>`, because a name is the only
 * thing this control has to say. Collapsed there is no room for one, so the
 * cylinder stands in and the choice moves into a popup.
 *
 * **One click selects and closes** — unlike the chat bar's source picker,
 * which is a multi-select and has to stay open while you tick things. This is
 * one-of-two, so a menu that lingered after the choice would just be a second
 * click to dismiss.
 *
 * @param provider The selected backend.
 * @param onChange Commit a new backend.
 * @param disabled A build is in flight, so switching is refused.
 * @returns The icon button and, when open, its menu.
 */
function ProviderPicker({ provider, onChange, disabled }: ProviderPickerProps) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rail-provider-mini">
      <button
        type="button"
        className="rail-item"
        onClick={() => setOpen((prev) => !prev)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="menu"
        title={`Data source: ${PROVIDER_LABEL[provider]}`}
        aria-label={`Data source: ${PROVIDER_LABEL[provider]}`}
      >
        <span className="rail-glyph" aria-hidden="true">
          {/* A database cylinder: two ellipses and the sides between them. */}
          <svg viewBox="0 0 16 16" focusable="false">
            <ellipse
              cx="8"
              cy="3.9"
              rx="5.2"
              ry="2.1"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
            />
            <path
              d="M2.8 3.9v8.2c0 1.16 2.33 2.1 5.2 2.1s5.2-.94 5.2-2.1V3.9"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
            />
            <path
              d="M2.8 8c0 1.16 2.33 2.1 5.2 2.1s5.2-.94 5.2-2.1"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
            />
          </svg>
        </span>
      </button>
      {open && (
        <>
          <div className="rail-menu-scrim" onClick={() => setOpen(false)} />
          <div className="rail-menu rail-menu-right" role="menu">
            {(Object.keys(PROVIDER_LABEL) as Provider[]).map((key) => (
              <button
                key={key}
                type="button"
                role="menuitemradio"
                aria-checked={key === provider}
                onClick={() => {
                  setOpen(false)
                  if (key !== provider) onChange(key)
                }}
              >
                <span className="rail-tick" aria-hidden="true">
                  {key === provider ? '✓' : ''}
                </span>
                {PROVIDER_LABEL[key]}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/** Props for {@link SessionRow}. */
interface SessionRowProps {
  session: SavedSessionMeta
  active: boolean
  onOpen: () => void
  onRename: (name: string) => void
  onDelete: () => void
}

/**
 * One saved session in the rail: a click opens it, a ⋮ menu renames or
 * deletes it.
 *
 * Rename edits **in place** rather than in a modal — the row is the label, so
 * editing it where it sits is both shorter and clearer about what is being
 * named. Enter commits, Escape abandons, and blur commits too (a click
 * elsewhere reads as "done", not "cancel").
 *
 * @param session The saved session's metadata row.
 * @param active  This session is the one currently open.
 * @param onOpen  Restore this session.
 * @param onRename Commit a new name.
 * @param onDelete Remove it.
 * @returns The rendered row.
 */
function SessionRow({ session, active, onOpen, onRename, onDelete }: SessionRowProps) {
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
      <button type="button" className="rail-session-open" onClick={onOpen} title={session.name}>
        <span className="rail-dot" aria-hidden="true" />
        <span className="rail-label">{session.name}</span>
      </button>
      <button
        type="button"
        className="rail-more"
        onClick={() => setMenuOpen((prev) => !prev)}
        aria-label={`Options for ${session.name}`}
        aria-expanded={menuOpen}
      >
        ⋮
      </button>
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

/**
 * Render the left rail.
 *
 * @returns The rail, expanded or collapsed.
 */
export default function SideBar({
  open,
  onToggle,
  view,
  onView,
  onNewGraph,
  sessions,
  openSessionId,
  onOpenSession,
  onRenameSession,
  onDeleteSession,
  onSaveSession,
  justSaved = false,
  onOpenSettings,
  onStartTour,
  theme,
  onToggleTheme,
  provider,
  onProviderChange,
  loadingGraph,
  seedTitle,
}: SideBarProps) {
  const collapsed = !open
  // Same drag-to-resize the two right-docked panels use, mirrored. The width
  // only applies while expanded — collapsed is a fixed icon rail, and a
  // 300px-wide strip of icons would be absurd.
  // Dragging the handle well past the 180px floor folds the rail instead of
  // stopping dead there — the gesture already means "I want this space back".
  // 130px is 50px of deliberate overshoot, so bottoming out isn't enough. The
  // folded rail keeps the handle, so the same pull the other way brings it
  // back: 96px is 40px past the icon rail's own 56.
  const { width, onHandlePointerDown, dragging } = useResizablePanel('atlas.railWidth', 240, {
    min: 180,
    max: 380,
    side: 'left',
    fold: { collapsed, collapsedWidth: RAIL_COLLAPSED_WIDTH, closeAt: 130, openAt: 96, onToggle },
  })

  return (
    <nav
      className={`rail${collapsed ? ' collapsed' : ''}${dragging ? ' dragging' : ''}`}
      data-tour="rail"
      aria-label="Main"
      style={collapsed ? undefined : { width }}
    >
      <div className="rail-top">
        {/* Brand row: the whole row is the collapse toggle. "Atlas" and the
            open graph's title are labels rather than controls, but a hover
            highlight that stopped at the glyph made the row look like an icon
            button with two words parked beside it — so the row is one target,
            the way every other entry below it is, and the seed reads as a
            subtitle to the app name, which is what it is. */}
        <button
          type="button"
          className="rail-item rail-brandrow"
          onClick={onToggle}
          title={open ? 'Collapse the menu' : 'Expand the menu'}
          aria-label={open ? 'Collapse the menu' : 'Expand the menu'}
          aria-expanded={open}
        >
          {/* The panel glyph both apps use: a rectangle with its left column
              filled, which reads as "there is a rail here" at either state. */}
          <span className="rail-glyph" aria-hidden="true">
            <svg viewBox="0 0 16 16" focusable="false">
              <rect
                x="1.6"
                y="2.6"
                width="12.8"
                height="10.8"
                rx="2"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.3"
              />
              <line x1="6.2" y1="2.6" x2="6.2" y2="13.4" stroke="currentColor" strokeWidth="1.3" />
            </svg>
          </span>
          {open && (
            <>
              <span className="rail-brand">Atlas</span>
              {/* Its own tooltip inside the button's: the row's says what the
                  click does, and the seed — the one thing here that truncates
                  — says what it is in full. */}
              {seedTitle && (
                <span className="rail-seed" title={seedTitle}>
                  {seedTitle}
                </span>
              )}
            </>
          )}
        </button>

        <button
          type="button"
          className="rail-item"
          data-tour="new-graph"
          onClick={onNewGraph}
          title="Start fresh — clears the graph and the conversation"
        >
          <span className="rail-glyph" aria-hidden="true">
            ✎
          </span>
          {open && <span className="rail-label">New graph</span>}
        </button>
      </div>

      {/* The saved list is EXPANDED-ONLY, which is what ChatGPT's collapsed
          rail does too: a column of identical 🗂 glyphs distinguishes nothing,
          and titles are the whole point of the list. Collapsed, the rail is
          actions. */}
      <div className="rail-scroll">
        {open && sessions.length > 0 && <p className="rail-heading">Saved graphs</p>}
        {open &&
          sessions.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              active={session.id === openSessionId}
              onOpen={() => onOpenSession(session.id)}
              onRename={(name) => onRenameSession(session.id, name)}
              onDelete={() => onDeleteSession(session.id)}
            />
          ))}
        {open && sessions.length === 0 && (
          <p className="rail-empty">
            Saved graphs appear here. Explore a paper, then save it to come back to it.
          </p>
        )}
      </div>

      <div className="rail-bottom">
        {/* The data source. It lived over the canvas for one build and sat on
            top of the graph controls; it belongs here, where it is also
            reachable with NO graph open — which matters, because it decides
            which backend the assistant's own paper searches hit (v6.14.0),
            and the canvas version was gated on a graph existing.

            Expanded-only, like the saved list: a bare 🌐 glyph can't show
            which source is selected, and that is the only thing this control
            has to say at a glance. */}
        {!open && (
          <ProviderPicker provider={provider} onChange={onProviderChange} disabled={loadingGraph} />
        )}
        {open && (
          <label className="rail-provider" data-tour="provider">
            <span className="rail-provider-label">Data source</span>
            <select
              value={provider}
              onChange={(event) => onProviderChange(event.target.value as Provider)}
              disabled={loadingGraph}
              title="Which academic database graphs are built from — references, citations and the seed all come from this one source"
            >
              {(Object.keys(PROVIDER_LABEL) as Provider[]).map((key) => (
                <option key={key} value={key}>
                  {PROVIDER_LABEL[key]}
                </option>
              ))}
            </select>
          </label>
        )}
        {onSaveSession && (
          <button
            type="button"
            className={`rail-item${justSaved ? ' just-saved' : ''}`}
            onClick={onSaveSession}
            title="Save this graph and conversation"
          >
            {/* Both glyphs stay mounted and cross-fade. A transition (rather
                than a keyframe animation) gives the exit for free as the
                reverse of the entrance — swapping the element instead made
                the ✓ appear with a flourish and then disappear in one
                frame. */}
            <span className="rail-glyph rail-save-glyph" aria-hidden="true">
              <span className={`glyph-face${justSaved ? '' : ' shown'}`}>＋</span>
              <span className={`glyph-face glyph-check${justSaved ? ' shown' : ''}`}>✓</span>
            </span>
            {open && (
              <span className="rail-label rail-save-label">
                <span className={`glyph-face${justSaved ? '' : ' shown'}`}>Save this graph</span>
                <span className={`glyph-face${justSaved ? ' shown' : ''}`}>Saved</span>
              </span>
            )}
          </button>
        )}
        <button
          type="button"
          className={`rail-item${view === 'library' ? ' active' : ''}`}
          data-tour="library-btn"
          onClick={() => onView(view === 'library' ? 'workspace' : 'library')}
          title="Your library — books, PDFs, and pages the assistant can search"
          aria-pressed={view === 'library'}
        >
          <span className="rail-glyph" aria-hidden="true">
            📚
          </span>
          {open && <span className="rail-label">Library</span>}
        </button>
        <button
          type="button"
          className="rail-item"
          data-tour="settings-btn"
          onClick={onOpenSettings}
          title="Settings — the app's configuration, editable in place"
        >
          <span className="rail-glyph" aria-hidden="true">
            ⚙
          </span>
          {open && <span className="rail-label">Settings</span>}
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={onToggleTheme}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {/* The icon shows the ACTION, not the state — like a play button
              showing ▶ while paused. The U+FE0E forces text presentation:
              without it the sun renders as colour emoji and sizes the row
              differently from the moon. */}
          <span className="rail-glyph" aria-hidden="true">
            {theme === 'dark' ? '☀︎' : '☾'}
          </span>
          {open && (
            <span className="rail-label">{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          )}
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={onStartTour}
          title="A quick guided tour of the tools on screen"
        >
          <span className="rail-glyph" aria-hidden="true">
            ?
          </span>
          {open && <span className="rail-label">Take the tour</span>}
        </button>
      </div>

      {/* Present in both states, and doing a different job in each: it sizes
          the open rail, and it is the only way to *pull* the folded one back
          open — a collapsed edge you can't grab would make the drag-to-collapse
          a one-way door. */}
      <div
        className="rail-handle"
        onPointerDown={onHandlePointerDown}
        role="separator"
        aria-orientation="vertical"
        aria-label={open ? 'Resize the menu' : 'Drag right to open the menu'}
      />
    </nav>
  )
}
