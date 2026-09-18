/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention dropdown: the sibling threads and paper candidates for what
 * is being typed, shown above the composer.
 *
 * Above rather than below because the composer sits at the bottom of the panel
 * and a list below it would open off-screen. Two sections, threads first: the
 * reader's other discussions in this exploration, then the paper results. A
 * paper row is the **title** over `authors • venue • year` — the venue earns
 * its place here specifically, since two papers with near-identical titles
 * have to be told apart before one is picked, and where it was published is
 * what does that.
 *
 * No row is highlighted until the reader arrows onto or hovers one, and the
 * footer says what Enter will do *right now*: with nothing chosen it sends the
 * message as typed; on a paper that is the whole message it opens that paper;
 * on a paper inside a sentence it completes the title; on a thread it attaches
 * the discussion. The hint changes with the state because the two jobs Enter
 * has — send what I typed, take what I chose — are told apart only by whether
 * a row is lit, and a reader should not have to remember that rule.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { MentionPaper } from '../api'
import type { MentionChoice, MentionThread } from './parse'
import './mentions.css'

/** Props for {@link MentionSuggestions}. */
export interface MentionSuggestionsProps {
  /** The sibling threads matching the query, listed first. */
  threads: MentionThread[]
  /** The paper candidates to show, in the order the backend ranked them. */
  papers: MentionPaper[]
  /** Index of the row the keyboard is on, counted across threads then
   *  papers — Enter accepts it. -1 when no row is selected. */
  highlighted: number
  /** Whether the mention being typed is the whole message, so Enter on a
   *  chosen paper opens it rather than completing it into a sentence. */
  whole: boolean
  /** A lookup is in flight; the list may be stale or empty. */
  loading: boolean
  /** What the lookup is doing right now, in the server's own words, or null.
   *  One line that replaces itself, not a phase history. */
  step?: string | null
  /** Accept a row (click). */
  onPick: (choice: MentionChoice) => void
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
 * The footer line: what Enter does in the current state.
 *
 * @param choice The row the keyboard is on, or null.
 * @param whole  Whether the mention is the whole message.
 * @returns The hint text.
 */
export function hintFor(choice: MentionChoice | null, whole: boolean): string {
  if (!choice) {
    return whole
      ? 'Enter searches for what you typed · ↑↓ to choose a row'
      : 'Enter sends your message · ↑↓ to choose a row'
  }
  if (choice.kind === 'thread') return 'Enter attaches this discussion'
  return whole
    ? 'Enter opens this paper · Tab adds it to your message instead'
    : 'Enter adds this paper to your question'
}

/**
 * Render the mention dropdown.
 *
 * @param props See {@link MentionSuggestionsProps}.
 * @returns The suggestion panel.
 */
export default function MentionSuggestions({
  threads,
  papers,
  highlighted,
  whole,
  loading,
  step,
  onPick,
  onHighlight,
}: MentionSuggestionsProps) {
  // The paper section exists once a lookup could have run: results are up,
  // or one is in flight. Below the query floor there is neither, and the
  // threads stand alone.
  const showPapers = papers.length > 0 || loading
  const rows: MentionChoice[] = [
    ...threads.map((thread): MentionChoice => ({ kind: 'thread', thread })),
    ...papers.map((paper): MentionChoice => ({ kind: 'paper', paper })),
  ]
  return (
    <div className="mention-panel">
      {/* Only the rows scroll. The footer sits outside the scrolling box so
          it stays in view however long the list gets — with eight rows up
          it used to be below the fold, which is exactly when it is needed. */}
      <div className="mention-list" role="listbox" aria-label="Mention suggestions">
        {threads.length > 0 && (
          <>
            <div className="mention-head">Discussions in this exploration</div>
            {threads.map((thread, index) => (
              <button
                key={`thread:${thread.id}`}
                type="button"
                role="option"
                aria-selected={index === highlighted}
                className={`mention-row${index === highlighted ? ' on' : ''}`}
                onMouseDown={(event) => {
                  event.preventDefault()
                  onPick({ kind: 'thread', thread })
                }}
                onMouseEnter={() => onHighlight(index)}
              >
                <span className="mention-icon" aria-hidden="true">
                  💬
                </span>
                <span className="mention-text">
                  <span className="mention-title">{thread.title}</span>
                </span>
              </button>
            ))}
          </>
        )}
        {showPapers && (
          <div className="mention-head">
            All paper results
            {loading && <span className="spin mention-spin" role="status" aria-label="Searching" />}
          </div>
        )}
        {/* The live phase line: what the lookup is waiting on, named by the
          server. It shows whether or not results are up yet, because the
          provisional cached list lands first and the reader should still be
          able to tell that more is coming — and which of the three phases
          (cache, provider, nickname resolve) is taking the time. `aria-live`
          so the change is announced without stealing focus from the textarea
          they are still typing in. */}
        {(step || (papers.length === 0 && loading)) && (
          <div className="mention-step" aria-live="polite">
            {step ?? 'Searching…'}
          </div>
        )}
        {papers.map((paper, index) => {
          // Rows are numbered across both sections, threads first, so the
          // keyboard walks one list.
          const row = threads.length + index
          return (
            <button
              key={`paper:${paper.id}`}
              type="button"
              role="option"
              aria-selected={row === highlighted}
              className={`mention-row${row === highlighted ? ' on' : ''}`}
              // Pointer-down, not click: the composer's blur would otherwise
              // close the panel before a click could land on it.
              onMouseDown={(event) => {
                event.preventDefault()
                onPick({ kind: 'paper', paper })
              }}
              onMouseEnter={() => onHighlight(row)}
            >
              <span className="mention-icon" aria-hidden="true">
                📄
              </span>
              <span className="mention-text">
                <span className="mention-title">{paper.title}</span>
                {byline(paper) && <span className="mention-meta">{byline(paper)}</span>}
              </span>
            </button>
          )
        })}
      </div>
      {/* What Enter does right now — the one thing the reader most needs to
          know, since nothing is pre-selected and the list looks like it
          might grab their Enter. */}
      <div className="mention-hint">{hintFor(rows[highlighted] ?? null, whole)}</div>
    </div>
  )
}
