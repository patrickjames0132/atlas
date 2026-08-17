/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The chat bar's search controls: the direct-search toggle, and the filter
 * popover (publication-year window + field of study) behind it.
 *
 * Both travel with the source-scope picker, for the same reason that one does:
 * they belong to the thing you are about to send. They sat *inside* the ask
 * pill until v7.11.0, which made a text box look like a toolbar; now they ride
 * beside it — a chip row under the bar with no graph, the Chat section's row
 * with one. The filters deliberately sit outside the direct-search toggle
 * rather than inside it: they bind the researcher's paper searches too, so
 * they are the bar's filters, not direct search's (see `api/search.ts`).
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useState } from 'react'
import { DEFAULT_SEARCH_OPTIONS, getFields } from '../api'
import type { Field, Provider, SearchOptions } from '../api'
import './search.css'

/** Props for {@link SearchControls}. */
export interface SearchControlsProps {
  /** Direct search is armed — the next send goes to the scout, not the
   *  researcher. */
  direct: boolean
  onDirectChange: (direct: boolean) => void
  /** The active filters (all optional; the defaults filter nothing). */
  options: SearchOptions
  onOptions: (next: SearchOptions) => void
  /** The selected provider — the field picker fetches its vocabulary, and the
   *  filter values (field ids) are provider-specific. */
  provider: Provider
  /** The filter popover is open (one shared open-slot with the other pickers
   *  in the bar, so opening one closes the others). */
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * The year slider's floor. Semantic Scholar's corpus reaches back to the
 * 1800s and the slider spans all of it — full access beats track precision
 * (a handle parked at the floor reads as "no bound" anyway).
 */
const MIN_YEAR = 1800

/** Props for {@link YearRange}. */
interface YearRangeProps {
  options: SearchOptions
  onOptions: (next: SearchOptions) => void
}

/**
 * A dual-handle slider driving the {@link SearchOptions} publication-year window.
 *
 * Both handles always carry a value, so a handle parked at a bound is read as
 * "no bound": a floor at {@link MIN_YEAR} folds to `yearFrom = null` and a
 * ceiling at the current year folds to `yearTo = null`. That keeps a full-width
 * slider identical to the no-op {@link DEFAULT_SEARCH_OPTIONS} year window (and
 * off the active-option badge), while losing nothing — the endpoints are the
 * widest bounds the corpus can answer anyway.
 *
 * @param options   The active option set (its year window is read + written).
 * @param onOptions Commit a new option set upward.
 * @returns The rendered year-range row.
 */
function YearRange({ options, onOptions }: YearRangeProps) {
  const maxYear = new Date().getFullYear()
  const lo = options.yearFrom ?? MIN_YEAR
  const hi = options.yearTo ?? maxYear

  /**
   * Commit a new [lo, hi] window, folding either bound back to null.
   *
   * @param nextLo The new earliest year (folds to null at {@link MIN_YEAR}).
   * @param nextHi The new latest year (folds to null at the current year).
   */
  const commit = (nextLo: number, nextHi: number) => {
    onOptions({
      ...options,
      yearFrom: nextLo <= MIN_YEAR ? null : nextLo,
      yearTo: nextHi >= maxYear ? null : nextHi,
    })
  }

  /**
   * A year's position along the track as a 0–100 percentage.
   *
   * @param year The year to place.
   * @returns The position percentage.
   */
  const pct = (year: number) => ((year - MIN_YEAR) / (maxYear - MIN_YEAR)) * 100

  return (
    <div className="filter-row year-row">
      <span className="filter-label">Published</span>
      <div className="year-slider">
        <div className="year-track" />
        <div className="year-fill" style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }} />
        {/* Two overlapping range inputs share one track; the low handle jumps
            on top once it reaches the far right so it stays grabbable there. */}
        <input
          type="range"
          className="year-range"
          style={{ zIndex: lo >= maxYear ? 5 : 3 }}
          min={MIN_YEAR}
          max={maxYear}
          value={lo}
          aria-label="Earliest publication year"
          onChange={(event) => commit(Math.min(Number(event.target.value), hi), hi)}
        />
        <input
          type="range"
          className="year-range"
          style={{ zIndex: 4 }}
          min={MIN_YEAR}
          max={maxYear}
          value={hi}
          aria-label="Latest publication year"
          onChange={(event) => commit(lo, Math.max(Number(event.target.value), lo))}
        />
      </div>
      <span className="year-readout">
        {lo} – {hi}
      </span>
    </div>
  )
}

/**
 * Render the direct-search toggle and the filter popover beside it.
 *
 * @returns The two inline controls (and the popover, when open).
 */
export default function SearchControls({
  direct,
  onDirectChange,
  options,
  onOptions,
  provider,
  open,
  onOpenChange,
}: SearchControlsProps) {
  // The field vocabulary loads lazily the first time the popover opens, so the
  // common no-filter path never pays the fetch. null = not yet loaded.
  const [fieldOptions, setFieldOptions] = useState<Field[] | null>(null)
  // Each provider has its own field vocabulary — drop the cached options when
  // the provider changes so the next open refetches the right one.
  useEffect(() => {
    setFieldOptions(null)
  }, [provider])
  useEffect(() => {
    if (open && fieldOptions === null) getFields(provider).then(setFieldOptions)
  }, [open, fieldOptions, provider])

  const activeCount =
    (options.yearFrom != null ? 1 : 0) + (options.yearTo != null ? 1 : 0) + options.fields.length

  /**
   * Add a field to the filter (deduped).
   *
   * @param fieldId The provider field id to add (an S2 field name / an OpenAlex
   *                numeric field id).
   */
  const addField = (fieldId: string) => {
    if (!fieldId || options.fields.includes(fieldId)) return
    onOptions({ ...options, fields: [...options.fields, fieldId] })
  }

  /**
   * Remove one field from the filter.
   *
   * @param fieldId The field id to drop.
   */
  const removeField = (fieldId: string) => {
    onOptions({ ...options, fields: options.fields.filter((other) => other !== fieldId) })
  }

  return (
    <div className="search-controls">
      <button
        type="button"
        className={`bar-toggle ${direct ? 'on' : ''}`}
        data-tour="direct-search"
        aria-pressed={direct}
        onClick={() => onDirectChange(!direct)}
        title={
          direct
            ? 'Direct search is on — your next message looks up papers and lists them, with no answer written'
            : 'Direct search: look up papers and list them to pick from, instead of asking the assistant a question'
        }
      >
        <span aria-hidden="true">🔍</span>
        <span className="toggle-label">Find papers</span>
      </button>
      <button
        type="button"
        className={`bar-toggle ${activeCount ? 'on' : ''}`}
        data-tour="search-filters"
        onClick={() => onOpenChange(!open)}
        title="Restrict which papers can be found — by publication year or field of study. Applies to direct search AND to the assistant's own paper searches."
      >
        {/* A funnel, drawn rather than borrowed from the emoji table: docked in
            the side panel the labels collapse away and this is all that's
            left, so it has to render identically everywhere. */}
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path
            d="M2.5 3.2h11l-4.2 5v4.3l-2.6 1.3V8.2z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
        <span className="toggle-label">Filters</span>
        {activeCount ? <span className="toggle-count">{activeCount}</span> : null}
      </button>

      {open && (
        <div className="filter-pop">
          <button
            type="button"
            className="link-btn filter-close"
            onClick={() => onOpenChange(false)}
            aria-label="Close the filters"
          >
            ✕
          </button>
          <YearRange options={options} onOptions={onOptions} />
          <div className="filter-row">
            <span className="filter-label">Field</span>
            <select
              className="cat-select"
              value=""
              aria-label="Add a field-of-study filter"
              onChange={(event) => addField(event.target.value)}
            >
              <option value="">{fieldOptions === null ? 'Loading fields…' : 'Add a field…'}</option>
              {fieldOptions?.map((field) => (
                <option key={field.id} value={field.id}>
                  {field.name}
                </option>
              ))}
            </select>
          </div>
          {options.fields.length > 0 && (
            <div className="filter-cats">
              {options.fields.map((fieldId) => (
                <button
                  key={fieldId}
                  className="cat-chip"
                  onClick={() => removeField(fieldId)}
                  title="Remove this field filter"
                >
                  {fieldOptions?.find((field) => field.id === fieldId)?.name ?? fieldId} ✕
                </button>
              ))}
            </div>
          )}
          <div className="filter-foot">
            <span className="filter-hint">
              Applies to every paper search — direct, and the assistant’s own. Citation links on the
              graph are never filtered.
            </span>
            {activeCount > 0 && (
              <button className="link-btn" onClick={() => onOptions(DEFAULT_SEARCH_OPTIONS)}>
                Reset
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
