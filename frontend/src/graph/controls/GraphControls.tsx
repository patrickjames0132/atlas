/**
 * The declutter panel over the graph: layout toggle (Force / Timeline),
 * relation filter chips, the dual-knob year range slider, the dual-knob
 * citation-count window slider, the visible-count readout, and the pin/fit
 * actions.
 *
 * Purely presentational — all state lives in GraphExplorer; this just renders
 * it and fires the callbacks.
 */

import type { CSSProperties } from 'react'
import { REL_COLOR, REL_LABEL, REL_TYPES } from '../theme'
import { CITE_SLIDER_STEPS, citationThreshold } from '../model'
import '../graph.css'

/** Props for {@link GraphControls}. */
export interface GraphControlsProps {
  /** Current layout mode. */
  layout: 'force' | 'timeline'
  /** Switch layout (pins/releases year columns as needed). */
  onLayout: (mode: 'force' | 'timeline') => void
  /** The relation types currently shown. */
  enabled: Set<string>
  /** Toggle one relation type on/off. */
  onToggleType: (type: string) => void
  /** The base graph's year range (slider bounds). */
  minYear: number
  maxYear: number
  /** The selected year window. */
  yearLo: number
  yearHi: number
  onYearLo: (year: number) => void
  onYearHi: (year: number) => void
  /** The citation-count range in the graph (the citation slider's bounds). */
  minCitations: number
  maxCitations: number
  /** The citation window's knob positions (each 0…{@link CITE_SLIDER_STEPS}). */
  citeLo: number
  citeHi: number
  onCiteLo: (value: number) => void
  onCiteHi: (value: number) => void
  /** Visible vs. total node counts for the readout. */
  visibleCount: number
  totalCount: number
  /** How many nodes are hand-picked into the teacher's scope (0 = none). */
  selectedCount: number
  /** Clear the hand-picked selection. */
  onClearSelection: () => void
  /** How many nodes the user has pinned (0 disables Release). */
  pinnedCount: number
  /** Unpin every node. */
  onReleaseAll: () => void
  /** Re-center the graph (zoomToFit). */
  onFit: () => void
  /** Bust this seed's cached snapshot and re-fetch it from the provider. */
  onRefresh: () => void
  /** A graph load/refresh is in flight (disables Refresh). */
  refreshing: boolean
  /** A provider-specific caveat to surface below the controls (e.g. S2's ~10k
   *  citer-offset limit), or null when the active provider has none. */
  providerNote?: string | null
}

/**
 * Render the graph's control panel.
 *
 * @returns The declutter panel (toggle, chips, sliders, actions, hint).
 */
export default function GraphControls({
  layout,
  onLayout,
  enabled,
  onToggleType,
  minYear,
  maxYear,
  yearLo,
  yearHi,
  onYearLo,
  onYearHi,
  minCitations,
  maxCitations,
  citeLo,
  citeHi,
  onCiteLo,
  onCiteHi,
  visibleCount,
  totalCount,
  selectedCount,
  onClearSelection,
  pinnedCount,
  onReleaseAll,
  onFit,
  onRefresh,
  refreshing,
  providerNote,
}: GraphControlsProps) {
  // The year slider only makes sense when the graph spans more than one year.
  const showYears = maxYear > minYear
  const yearSpan = maxYear - minYear
  /**
   * Position of a year along the range track, for the fill + knobs.
   *
   * @param year The year to place.
   * @returns The position as a 0–100 percentage.
   */
  const yearPct = (year: number) => (yearSpan ? ((year - minYear) / yearSpan) * 100 : 0)

  // The citation slider only earns its space when the neighbors span a citation
  // range to bound a window against (a flat/empty range gives nothing to trim).
  const showCitations = maxCitations > minCitations
  // The knob positions are linear (0…STEPS); the counts they read out are the
  // log-mapped thresholds across the graph's min…max. The fill/knobs sit at the
  // raw position percentage.
  const loCitations = citationThreshold(citeLo, minCitations, maxCitations)
  const hiCitations = citationThreshold(citeHi, minCitations, maxCitations)
  const citePct = (position: number) => (position / CITE_SLIDER_STEPS) * 100

  return (
    <div className="controls">
      <div className="layout-toggle" data-tour="layout">
        <button className={layout === 'force' ? 'on' : ''} onClick={() => onLayout('force')}>
          Force
        </button>
        <button className={layout === 'timeline' ? 'on' : ''} onClick={() => onLayout('timeline')}>
          Timeline
        </button>
      </div>
      <div className="ctrl-rels" data-tour="relations">
        {REL_TYPES.map((type) => {
          const on = enabled.has(type)
          return (
            <button
              key={type}
              className={`rel-toggle ${on ? 'on' : ''}`}
              onClick={() => onToggleType(type)}
              style={{ '--c': REL_COLOR[type] } as CSSProperties}
              title={on ? `Hide ${REL_LABEL[type]}` : `Show ${REL_LABEL[type]}`}
            >
              <i />
              {REL_LABEL[type]}
            </button>
          )
        })}
      </div>

      {showYears && (
        <div className="years" data-tour="years">
          <div className="years-label">
            Years <b>{yearLo}</b> – <b>{yearHi}</b>
          </div>
          <div className="range-dual">
            <div className="range-track" />
            <div
              className="range-fill"
              style={{
                left: `${yearPct(yearLo)}%`,
                width: `${yearPct(yearHi) - yearPct(yearLo)}%`,
              }}
            />
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearLo}
              aria-label="Earliest year"
              onChange={(event) => onYearLo(Math.min(Number(event.target.value), yearHi))}
            />
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearHi}
              aria-label="Latest year"
              onChange={(event) => onYearHi(Math.max(Number(event.target.value), yearLo))}
            />
          </div>
        </div>
      )}

      {showCitations && (
        <div className="cites" data-tour="citations">
          <div className="cites-label">
            Citations <b>{loCitations.toLocaleString()}</b> – <b>{hiCitations.toLocaleString()}</b>
          </div>
          <div className="range-dual">
            <div className="range-track" />
            <div
              className="range-fill"
              style={{
                left: `${citePct(citeLo)}%`,
                width: `${citePct(citeHi) - citePct(citeLo)}%`,
              }}
            />
            <input
              type="range"
              min={0}
              max={CITE_SLIDER_STEPS}
              value={citeLo}
              aria-label="Fewest citations"
              onChange={(event) => onCiteLo(Math.min(Number(event.target.value), citeHi))}
            />
            <input
              type="range"
              min={0}
              max={CITE_SLIDER_STEPS}
              value={citeHi}
              aria-label="Most citations"
              onChange={(event) => onCiteHi(Math.max(Number(event.target.value), citeLo))}
            />
          </div>
        </div>
      )}

      <div className="ctrl-foot">
        <span className="count-readout">
          {visibleCount} / {totalCount} papers
        </span>
        <div className="ctrl-btns" data-tour="actions">
          <button
            className="mini-btn"
            onClick={onReleaseAll}
            disabled={pinnedCount === 0}
            title="Unpin every node"
          >
            Release {pinnedCount || ''}
          </button>
          <button className="mini-btn" onClick={onFit} title="Re-center the graph">
            Fit
          </button>
          <button
            className="mini-btn"
            onClick={onRefresh}
            disabled={refreshing}
            title="Bust this paper's cached snapshot and re-fetch from Semantic Scholar"
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
      <div className="ctrl-select" data-tour="selector">
        <span
          className="select-hint"
          title="Hand-pick papers to scope the AI teacher's lectures and answers to them"
        >
          ⌥ alt-drag to add papers to the teacher's scope · ⇧ shift-click one · alt-click empty to
          clear
        </span>
        {selectedCount > 0 && (
          <span className="select-status">
            <b>{selectedCount}</b> picked
            <button
              className="link-btn"
              onClick={onClearSelection}
              title="Clear the hand-picked selection — the teacher grounds in every visible paper again"
            >
              clear
            </button>
          </span>
        )}
      </div>

      <div className="ctrl-hint" data-tour="hint">
        {layout === 'timeline'
          ? 'papers placed left→right by year · double-click to re-seed'
          : 'drag to pin · double-click a node to re-seed'}
      </div>

      {providerNote && <div className="provider-note">ⓘ {providerNote}</div>}
    </div>
  )
}
