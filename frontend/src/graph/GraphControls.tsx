/**
 * The declutter panel over the graph: layout toggle (Force / Timeline),
 * relation filter chips, the dual-knob year range slider, the visible-count
 * readout, and the pin/fit actions.
 *
 * Purely presentational — all state lives in GraphExplorer; this just renders
 * it and fires the callbacks.
 */

import type { CSSProperties } from 'react'
import { REL_COLOR, REL_LABEL, REL_TYPES } from './theme'
import './graph.css'

/** Props for {@link GraphControls}. */
export interface GraphControlsProps {
  /** Current layout mode. */
  layout: 'force' | 'timeline'
  /** Switch layout (pins/releases year columns as needed). */
  onLayout: (mode: 'force' | 'timeline') => void
  /** The relation types currently shown. */
  enabled: Set<string>
  /** Toggle one relation type on/off. */
  onToggleType: (t: string) => void
  /** Per-relation node counts (from the base graph, chips show these). */
  counts: Record<string, number>
  /** The base graph's year range (slider bounds). */
  minYear: number
  maxYear: number
  /** The selected year window. */
  yearLo: number
  yearHi: number
  onYearLo: (y: number) => void
  onYearHi: (y: number) => void
  /** Visible vs. total node counts for the readout. */
  visibleCount: number
  totalCount: number
  /** How many nodes the user has pinned (0 disables Release). */
  pinnedCount: number
  /** Unpin every node. */
  onReleaseAll: () => void
  /** Re-center the graph (zoomToFit). */
  onFit: () => void
}

/** Render the graph's control panel. */
export default function GraphControls({
  layout,
  onLayout,
  enabled,
  onToggleType,
  counts,
  minYear,
  maxYear,
  yearLo,
  yearHi,
  onYearLo,
  onYearHi,
  visibleCount,
  totalCount,
  pinnedCount,
  onReleaseAll,
  onFit,
}: GraphControlsProps) {
  // The year slider only makes sense when the graph spans more than one year.
  const showYears = maxYear > minYear
  const yearSpan = maxYear - minYear
  /** Position (0–100%) of a year along the range track, for the fill + knobs. */
  const yearPct = (y: number) => (yearSpan ? ((y - minYear) / yearSpan) * 100 : 0)

  return (
    <div className="controls">
      <div className="layout-toggle">
        <button className={layout === 'force' ? 'on' : ''} onClick={() => onLayout('force')}>
          Force
        </button>
        <button
          className={layout === 'timeline' ? 'on' : ''}
          onClick={() => onLayout('timeline')}
        >
          Timeline
        </button>
      </div>
      <div className="ctrl-chips">
        {REL_TYPES.map((t) => (
          <button
            key={t}
            className={`chip ${enabled.has(t) ? 'on' : ''}`}
            onClick={() => onToggleType(t)}
            style={{ '--c': REL_COLOR[t] } as CSSProperties}
          >
            <i />
            {REL_LABEL[t]}
            <em>{counts[t]}</em>
          </button>
        ))}
      </div>

      {showYears && (
        <div className="years">
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
              onChange={(e) => onYearLo(Math.min(Number(e.target.value), yearHi))}
            />
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearHi}
              aria-label="Latest year"
              onChange={(e) => onYearHi(Math.max(Number(e.target.value), yearLo))}
            />
          </div>
        </div>
      )}

      <div className="ctrl-foot">
        <span className="count-readout">
          {visibleCount} / {totalCount} papers
        </span>
        <div className="ctrl-btns">
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
        </div>
      </div>
      <div className="ctrl-hint">
        {layout === 'timeline'
          ? 'papers placed left→right by year · double-click to re-seed'
          : 'drag to pin · double-click a node to re-seed'}
      </div>
    </div>
  )
}
