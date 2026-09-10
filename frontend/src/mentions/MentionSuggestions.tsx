/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention dropdown: the paper candidates for what is being typed,
 * shown above the composer.
 *
 * Above rather than below because the composer sits at the bottom of the panel
 * and a list below it would open off-screen. Each row is the **title** over
 * `authors • venue • year` — the venue earns its place here specifically,
 * since two papers with near-identical titles have to be told apart before one
 * is picked, and where it was published is what does that.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { MentionPaper } from '../api'
import './mentions.css'

/** Props for {@link MentionSuggestions}. */
export interface MentionSuggestionsProps {
  /** The candidates to show, in the order the backend ranked them. */
  papers: MentionPaper[]
  /** Index of the row the keyboard is on — Enter accepts it. */
  highlighted: number
  /** A lookup is in flight; the list may be stale or empty. */
  loading: boolean
  /** Accept a row (click). */
  onPick: (paper: MentionPaper) => void
  /** Move the keyboard selection onto a row (hover), so mouse and keyboard
   *  never disagree about which row Enter would take. */
  onHighlight: (index: number) => void
}

/**
 * One row's byline: `authors • venue • year`, skipping whatever is missing so
 * a sparse record doesn't render orphaned separators.
 *
 * @param paper The candidate paper.
 * @returns The byline text, possibly empty.
 */
function byline(paper: MentionPaper): string {
  return [paper.authors, paper.venue, paper.year].filter(Boolean).join(' • ')
}

/**
 * Render the mention dropdown.
 *
 * @param props See {@link MentionSuggestionsProps}.
 * @returns The suggestion panel.
 */
export default function MentionSuggestions({
  papers,
  highlighted,
  loading,
  onPick,
  onHighlight,
}: MentionSuggestionsProps) {
  return (
    <div className="mention-panel" role="listbox" aria-label="Paper suggestions">
      <div className="mention-head">
        All paper results
        {loading && <span className="spin mention-spin" role="status" aria-label="Searching" />}
      </div>
      {papers.length === 0 && loading && <div className="mention-empty">Searching…</div>}
      {papers.map((paper, index) => (
        <button
          key={paper.id}
          type="button"
          role="option"
          aria-selected={index === highlighted}
          className={`mention-row${index === highlighted ? ' on' : ''}`}
          // Pointer-down, not click: the composer's blur would otherwise close
          // the panel before a click could land on it.
          onMouseDown={(event) => {
            event.preventDefault()
            onPick(paper)
          }}
          onMouseEnter={() => onHighlight(index)}
        >
          <span className="mention-icon" aria-hidden="true">
            📄
          </span>
          <span className="mention-text">
            <span className="mention-title">{paper.title}</span>
            {byline(paper) && <span className="mention-meta">{byline(paper)}</span>}
          </span>
        </button>
      ))}
    </div>
  )
}
