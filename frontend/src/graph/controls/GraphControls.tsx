/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The declutter panel over the graph: layout toggle (Force / Timeline),
 * relation filter chips, the dual-knob year range slider, the dual-knob
 * citation-count window slider, the visible-count readout, and the pin/fit
 * actions — all under a header bar that collapses the whole panel to a slim
 * strip (the find control's collapse-until-wanted idea, panel-sized), giving
 * the canvas its ~272px back when the user isn't filtering.
 *
 * Purely presentational — all state lives in GraphExplorer; this just renders
 * it and fires the callbacks. The one exception is the collapsed flag, which
 * is local like the find control's own open/closed: nothing else reads it.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useState } from 'react'
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
  /** Show the per-chip count sliders — true only while the build is user-sized
   *  (the settings modal's automatic sizing turned off). An adaptive build is
   *  already trimmed by the backend, so the sliders stay out of the way.
   *  Optional, defaulting off: a caller with no interest in caps renders the
   *  plain chips it always did. */
  showRelCaps?: boolean
  /** How many papers of each relation to show; a missing key means all. */
  relCaps?: Record<string, number>
  /** How many papers each relation holds in the graph (the sliders' bounds). */
  relTotals?: Record<string, number>
  /** Set one relation's display cap (the full total means "no cap"). */
  onRelCap?: (type: string, cap: number) => void
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
  /** How many nodes the teacher currently lights up (0 = none). */
  litCount: number
  /** Drop every highlight at once — hand-picked selection and teacher glow
   *  alike (the same reset Esc runs). */
  onClearAll: () => void
  /** How many nodes the user has pinned (shown in the Release label). */
  pinnedCount: number
  /** Unpin every node and reheat the simulation so the layout re-settles —
   *  useful bare (nothing pinned) to re-condense a drifted force graph. */
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
  /** The guided tour is walking the panel's stops — expand a collapsed panel
   *  so its targets can be spotlighted (it never re-collapses; no tidy-up). */
  stagedOpen?: boolean
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
  showRelCaps = false,
  relCaps = {},
  relTotals = {},
  onRelCap,
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
  litCount,
  onClearAll,
  pinnedCount,
  onReleaseAll,
  onFit,
  onRefresh,
  refreshing,
  providerNote,
  stagedOpen,
}: GraphControlsProps) {
  // Collapsed to the slim header bar? Local, like the find control's own
  // open/closed — nothing else needs to know.
  const [collapsed, setCollapsed] = useState(false)
  // The tour staging 'controls' expands a collapsed panel so its stops have
  // something to spotlight. It never re-collapses on the way out — the same
  // no-tidy-up call as the detail panel's staged seed selection.
  useEffect(() => {
    if (stagedOpen) setCollapsed(false)
  }, [stagedOpen])

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

  // One readout string for the expanded footer AND the collapsed bar: a
  // hand-pick wins over the plain filter count, and its denominator is the
  // SHOWN papers — honest to the teacher scope (selected ∩ visible).
  const countReadout =
    selectedCount > 0
      ? `${selectedCount} / ${visibleCount} papers selected`
      : `${visibleCount} / ${totalCount} papers shown`

  return (
    <div className={`controls${collapsed ? ' collapsed' : ''}`}>
      <button
        className="ctrl-head"
        data-tour="controls-head"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((wasCollapsed) => !wasCollapsed)}
        title={
          collapsed
            ? 'Reopen the graph controls'
            : 'Collapse the controls to a slim bar and free up the canvas'
        }
      >
        <span>Graph controls</span>
        {collapsed && <span className="ctrl-head-count">{countReadout}</span>}
        <span className="ctrl-head-caret" aria-hidden="true">
          {collapsed ? '▾' : '▴'}
        </span>
      </button>

      <div className="ctrl-body" hidden={collapsed}>
        <div className="layout-toggle" data-tour="layout">
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
        {/* Two layouts, one control. With automatic sizing on it's the plain
            wrapping pill row it has always been. With it off, each chip becomes
            the label atop its own count slider — the chip is still the on/off
            toggle (highlighted while on), it just now heads a slider that trims
            how many of that relation show. */}
        {showRelCaps ? (
          <div className="rel-caps" data-tour="relations">
            {REL_TYPES.map((type) => {
              const on = enabled.has(type)
              const total = relTotals[type] ?? 0
              // A slider only under a chip that's on and has more than one paper
              // to trim; otherwise the chip stands alone (still a toggle).
              const showSlider = on && total > 1
              const cap = relCaps[type] ?? total
              return (
                <div
                  key={type}
                  className="rel-cap-group"
                  style={{ '--c': REL_COLOR[type] } as CSSProperties}
                >
                  <div className="rel-cap-head">
                    <button
                      className={`rel-toggle ${on ? 'on' : ''}`}
                      onClick={() => onToggleType(type)}
                      title={on ? `Hide ${REL_LABEL[type]}` : `Show ${REL_LABEL[type]}`}
                    >
                      <i />
                      {REL_LABEL[type]}
                    </button>
                    {showSlider && (
                      <span className="rel-cap-count">
                        {cap}/{total}
                      </span>
                    )}
                  </div>
                  {showSlider && (
                    <input
                      className="rel-cap-slider"
                      type="range"
                      min={1}
                      max={total}
                      value={cap}
                      // The filled portion up to the thumb, as a CSS var the
                      // track gradient reads — the single-knob analog of the
                      // range sliders' `.range-fill`.
                      style={{ '--fill': `${(cap / total) * 100}%` } as CSSProperties}
                      onChange={(event) => onRelCap?.(type, Number(event.target.value))}
                      title={`Show the ${cap} most-cited of ${total} ${REL_LABEL[type]}`}
                      aria-label={`${REL_LABEL[type]} shown`}
                    />
                  )}
                </div>
              )
            })}
          </div>
        ) : (
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
        )}

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
              Citations <b>{loCitations.toLocaleString()}</b> –{' '}
              <b>{hiCitations.toLocaleString()}</b>
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
          <span className="count-readout">{countReadout}</span>
          <div className="ctrl-btns" data-tour="actions">
            <button
              className="mini-btn"
              onClick={onReleaseAll}
              title="Unpin every node and re-settle the layout"
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
            <button
              className="mini-btn"
              onClick={onClearAll}
              disabled={selectedCount === 0 && litCount === 0}
              title="Clear every highlight and hand-picked selection (Esc does the same)"
            >
              Clear
            </button>
          </div>
        </div>
        <div className="ctrl-select" data-tour="selector">
          <span
            className="select-hint"
            title="Hand-pick papers to scope the AI teacher's lectures and answers to them"
          >
            ⌥ alt-drag to add papers to the teacher's scope · ⇧ shift-click one · esc clears all
            highlights
          </span>
        </div>

        <div className="ctrl-hint" data-tour="hint">
          {layout === 'timeline'
            ? 'papers placed left→right by year · double-click to re-seed'
            : 'drag to pin · double-click a node to re-seed'}
        </div>

        {providerNote && <div className="provider-note">ⓘ {providerNote}</div>}
      </div>
    </div>
  )
}
