/**
 * The declutter panel over the graph: layout toggle (Force / Timeline),
 * relation filter chips, the dual-knob year range slider, the visible-count
 * readout, and the pin/fit actions.
 *
 * Purely presentational — all state lives in GraphExplorer; this just renders
 * it and fires the callbacks.
 */

import { Fragment, type CSSProperties } from 'react'
import { REL_COLOR, REL_LABEL, REL_TYPES } from '../theme'
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
  /** Per-relation pool sizes — each slider's maximum (what the paper has). */
  counts: Record<string, number>
  /** Per-relation visible count (each slider's current value). */
  limits: Record<string, number>
  /** Set one relation's visible count. */
  onLimit: (type: string, value: number) => void
  /** The base graph's year range (slider bounds). */
  minYear: number
  maxYear: number
  /** The selected year window. */
  yearLo: number
  yearHi: number
  onYearLo: (year: number) => void
  onYearHi: (year: number) => void
  /** Visible vs. total node counts for the readout. */
  visibleCount: number
  totalCount: number
  /** How many nodes the user has pinned (0 disables Release). */
  pinnedCount: number
  /** Unpin every node. */
  onReleaseAll: () => void
  /** Re-center the graph (zoomToFit). */
  onFit: () => void
  /** Bust this seed's cached snapshot and re-fetch it from Semantic Scholar. */
  onRefresh: () => void
  /** A graph load/refresh is in flight (disables Refresh). */
  refreshing: boolean
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
  counts,
  limits,
  onLimit,
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
  onRefresh,
  refreshing,
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

  return (
    <div className="controls">
      <div className="layout-toggle">
        <button className={layout === 'force' ? 'on' : ''} onClick={() => onLayout('force')}>
          Force
        </button>
        <button className={layout === 'timeline' ? 'on' : ''} onClick={() => onLayout('timeline')}>
          Timeline
        </button>
      </div>
      <div className="ctrl-rels">
        {REL_TYPES.map((type) => {
          const poolMax = counts[type] ?? 0
          const on = enabled.has(type)
          const shown = on ? Math.min(limits[type] ?? 0, poolMax) : 0
          return (
            <Fragment key={type}>
              <button
                className={`rel-toggle ${on ? 'on' : ''}`}
                onClick={() => onToggleType(type)}
                style={{ '--c': REL_COLOR[type] } as CSSProperties}
                title={on ? `Hide ${REL_LABEL[type]}` : `Show ${REL_LABEL[type]}`}
              >
                <i />
                {REL_LABEL[type]}
              </button>
              <input
                type="range"
                className="rel-slider"
                style={{ '--c': REL_COLOR[type] } as CSSProperties}
                min={0}
                max={poolMax}
                value={shown}
                disabled={!on || poolMax === 0}
                aria-label={`${REL_LABEL[type]} shown`}
                onChange={(event) => onLimit(type, Number(event.target.value))}
              />
              <em className="rel-count">
                {shown}
                <span className="rel-max">/{poolMax}</span>
              </em>
            </Fragment>
          )
        })}
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
      <div className="ctrl-hint">
        {layout === 'timeline'
          ? 'papers placed left→right by year · double-click to re-seed'
          : 'drag to pin · double-click a node to re-seed'}
      </div>
    </div>
  )
}
