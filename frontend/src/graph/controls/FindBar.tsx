/**
 * The find control — a round 🔍 button pinned to the graph area's top-right
 * corner that expands into a rounded input pill on click (Google-Maps style,
 * Patrick's pick after the always-open pill read as floating in no-man's
 * land). Zero chrome until wanted; collapses again when the box empties.
 *
 * Spotlights on-screen papers by title/author substring: purely lexical and
 * local, no API call — the header's seed search is the one that fetches.
 * Matching itself lives in `model.findMatches`; GraphExplorer owns the query
 * state and routes the matches through the highlight machinery.
 */

import { useState } from 'react'
import '../graph.css'

/**
 * Render the find control: the collapsed 🔍 toggle, or — once opened or while
 * a query is live — the input pill with the hit count and a ✕.
 *
 * @param query The current box contents (state lives in GraphExplorer).
 * @param onQuery Report the box's new contents ('' clears the find).
 * @param count Matching on-screen papers, or null when the box is empty.
 * @returns The floating find control.
 */
export default function FindBar({
  query,
  onQuery,
  count,
}: {
  query: string
  onQuery: (query: string) => void
  count: number | null
}) {
  const [open, setOpen] = useState(false)
  // A live query pins the pill open regardless of focus — the hit count (and
  // the spotlight it explains) shouldn't vanish because the user clicked away.
  const expanded = open || query !== ''

  if (!expanded) {
    return (
      <button
        className="graph-find-toggle"
        data-tour="find"
        onClick={() => setOpen(true)}
        aria-label="Find a paper on screen"
        title="Find a paper among those on screen (title or author) — local only, fetches nothing"
      >
        🔍
      </button>
    )
  }
  return (
    <div className="graph-find" data-tour="find">
      <input
        autoFocus
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event) => {
          // Esc in the box: first press clears the query, a second collapses
          // the pill (the global Esc-clears-all deliberately skips form
          // controls).
          if (event.key !== 'Escape') return
          if (query) onQuery('')
          else {
            event.currentTarget.blur()
            setOpen(false)
          }
        }}
        onBlur={() => {
          // Clicking away from an empty box tidies the pill back to the 🔍.
          if (!query) setOpen(false)
        }}
        placeholder="Find on graph…"
        aria-label="Find a paper among those on screen (title or author)"
        title="Spotlight on-screen papers by title or author — local only, fetches nothing"
      />
      {count !== null && (
        <span className="find-status">
          {count} hit{count === 1 ? '' : 's'}
          <button
            className="link-btn"
            onClick={() => {
              onQuery('')
              setOpen(false)
            }}
            aria-label="Clear the find"
          >
            ✕
          </button>
        </span>
      )}
    </div>
  )
}
