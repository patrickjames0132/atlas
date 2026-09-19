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

import { Fragment, useEffect, useState } from 'react'
import ThreadList from './ThreadList'
import { useResizablePanel } from '../ui/useResizablePanel'
import { PROVIDER_LABEL } from '../api'
import type { Provider, SavedSessionMeta } from '../api'
import './shell.css'
import SessionRow from './SessionRow'

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
  /** Clear the workspace and start a fresh exploration. */
  onNewGraph: () => void
  /** The saved explorations, newest-updated first. */
  sessions: SavedSessionMeta[]
  /** The exploration currently open, so the list can mark it. */
  openSessionId: string | null
  /**
   * Explorations with a stream still running — including ones the reader has
   * moved away from, which is the point: an answer left running is visibly
   * still running.
   */
  workingSessionIds?: string[]
  onOpenSession: (id: string) => void
  onRenameSession: (id: string, name: string) => void
  onDeleteSession: (id: string) => void
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
  /** The rail is expanded, so the entry shows its label like every other. */
  labelled: boolean
}

/**
 * The data-source glyph: a database cylinder — two ellipses and the sides
 * between them.
 *
 * @returns The inline SVG, sized by the `.rail-glyph` it sits in.
 */
function DatabaseGlyph() {
  return (
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
  )
}

/**
 * The data source, as a rail entry in either state.
 *
 * **Expanded** it is a native `<select>` dressed as a rail row: the cylinder
 * in the glyph lane, the chosen backend's name on the label column, a caret
 * at the far end, and the browser's own list on click. It lines up with
 * Library and Settings beneath it — the bordered box it was until v7.31.0
 * had its own left edge and its own text column, the one thing on the rail
 * that lined up with nothing. The row shows the *choice* rather than the
 * word "Data source" because a native select can only display its selected
 * option; the heading is the tooltip's job. (A custom popup was tried first:
 * beside the rail it sat a whole rail-width from its entry, and above the
 * entry it looked like a second control. The browser's list is anchored
 * where readers expect a select's to be.)
 *
 * **Collapsed** there is no width to show a value in, so the cylinder stands
 * alone and the choice moves into a popup opening to the right of the rail.
 * **One click there selects and closes** — unlike the chat bar's source
 * picker, which is a multi-select and has to stay open while you tick
 * things. This is one-of-two, so a menu that lingered after the choice would
 * just be a second click to dismiss.
 *
 * @param provider The selected backend.
 * @param onChange Commit a new backend.
 * @param disabled A build is in flight, so switching is refused.
 * @param labelled The rail is expanded, so the entry shows its value.
 * @returns The rail entry and, collapsed and open, its menu.
 */
function ProviderPicker({ provider, onChange, disabled, labelled }: ProviderPickerProps) {
  const [open, setOpen] = useState(false)
  const title = `Data source: ${PROVIDER_LABEL[provider]} — which academic database graphs are built from; references, citations and the seed all come from this one source`
  if (labelled)
    return (
      <label className="rail-item rail-provider-row" data-tour="provider" title={title}>
        <span className="rail-glyph" aria-hidden="true">
          <DatabaseGlyph />
        </span>
        <select
          value={provider}
          onChange={(event) => {
            onChange(event.target.value as Provider)
            // A select keeps focus after its list closes, and browsers count
            // that focus as keyboard-visible even off a mouse click — so the
            // row stayed lit after every choice. The choice is made; let go.
            event.target.blur()
          }}
          disabled={disabled}
          aria-label="Data source"
        >
          {(Object.keys(PROVIDER_LABEL) as Provider[]).map((key) => (
            <option key={key} value={key}>
              {PROVIDER_LABEL[key]}
            </option>
          ))}
        </select>
      </label>
    )
  return (
    <div className="rail-provider" data-tour="provider">
      <button
        type="button"
        className="rail-item"
        onClick={() => setOpen((prev) => !prev)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="menu"
        title={title}
        aria-label={`Data source: ${PROVIDER_LABEL[provider]}`}
      >
        <span className="rail-glyph" aria-hidden="true">
          <DatabaseGlyph />
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
  workingSessionIds = [],
  onOpenSession,
  onRenameSession,
  onDeleteSession,
  onOpenSettings,
  onStartTour,
  theme,
  onToggleTheme,
  provider,
  onProviderChange,
  loadingGraph,
  seedTitle,
}: SideBarProps) {
  const [expandedId, setExpandedId] = useState(openSessionId)
  useEffect(() => setExpandedId(openSessionId), [openSessionId])
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
          title="Start a new exploration — clears the graph and the conversation. The one you're leaving is already saved."
        >
          <span className="rail-glyph" aria-hidden="true">
            ✎
          </span>
          {open && <span className="rail-label">New Exploration</span>}
        </button>
      </div>

      {/* The saved list is EXPANDED-ONLY, which is what ChatGPT's collapsed
          rail does too: a column of identical 🗂 glyphs distinguishes nothing,
          and titles are the whole point of the list. Collapsed, the rail is
          actions. */}
      <div className="rail-scroll">
        {open && sessions.length > 0 && <p className="rail-heading">Explorations</p>}
        {open &&
          sessions.map((session) => (
            <Fragment key={session.id}>
              <SessionRow
                session={session}
                expanded={session.id === openSessionId && expandedId === session.id}
                onToggle={() => {
                  if (session.id !== openSessionId) {
                    onOpenSession(session.id)
                    setExpandedId(session.id)
                  } else setExpandedId(expandedId === session.id ? null : session.id)
                }}
                active={session.id === openSessionId}
                working={workingSessionIds.includes(session.id)}
                onOpen={() => onOpenSession(session.id)}
                onRename={(name) => onRenameSession(session.id, name)}
                onDelete={() => onDeleteSession(session.id)}
              />
              {session.id === openSessionId && expandedId === session.id && (
                <ThreadList explorationId={session.id} />
              )}
            </Fragment>
          ))}
        {open && sessions.length === 0 && (
          <p className="rail-empty">
            Your explorations appear here and save themselves — ask a question or open a paper, and
            you can come back to it.
          </p>
        )}
      </div>

      <div className="rail-bottom">
        {/* The data source. It lived over the canvas for one build and sat on
            top of the graph controls; it belongs here, where it is also
            reachable with NO graph open — which matters, because it decides
            which backend the assistant's own paper searches hit (v6.14.0),
            and the canvas version was gated on a graph existing. */}
        <ProviderPicker
          provider={provider}
          onChange={onProviderChange}
          disabled={loadingGraph}
          labelled={open}
        />
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
