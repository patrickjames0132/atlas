/**
 * The seed-search form: the query box + Explore button, plus the optional
 * (never required) pre-submit filters — a publication-year window and a
 * field-of-study picker fed by the backend's S2 vocabulary endpoint.
 *
 * Rendered inside AtlasHeader, but it belongs to the search concern — its
 * results (HitList) and state (useSeedSearch) live alongside it here. Filter
 * state lives in useSeedSearch (via Atlas) so runSearch reads it directly;
 * this component only renders and edits it.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getFields } from '../api'
import type { SearchFilters } from '../api'
import './search.css'

/** Props for {@link Search}. */
export interface SearchProps {
  /** The controlled search box value. */
  query: string
  onQueryChange: (q: string) => void
  /** Submit handler (routes to graph-load or keyword search). */
  onSubmit: (e: FormEvent) => void
  /** A search is in flight (disables the button, swaps its label). */
  searching: boolean
  /** A graph is loading (also disables the button). */
  loadingGraph: boolean
  /** The active filters (all optional; empty = search everything). */
  filters: SearchFilters
  onFilters: (f: SearchFilters) => void
}

/**
 * The year slider's floor. Semantic Scholar's corpus reaches back to the
 * 1800s and the slider spans all of it — full access beats track precision
 * (a handle parked at the floor reads as "no bound" anyway).
 */
const MIN_YEAR = 1800

/** Props for {@link YearRange}. */
interface YearRangeProps {
  filters: SearchFilters
  onFilters: (f: SearchFilters) => void
}

/**
 * A dual-handle slider driving the {@link SearchFilters} publication-year window.
 *
 * Both handles always carry a value, so a handle parked at a bound is read as
 * "no bound": a floor at {@link MIN_YEAR} folds to `yearFrom = null` and a
 * ceiling at the current year folds to `yearTo = null`. That keeps a full-width
 * slider identical to the no-op {@link EMPTY_FILTERS} state (and off the
 * active-filter badge), while losing nothing — the endpoints are the widest
 * bounds the corpus can answer anyway.
 *
 * @param filters   The active filter set (its year window is read + written).
 * @param onFilters Commit a new filter set upward.
 */
function YearRange({ filters, onFilters }: YearRangeProps) {
  const maxYear = new Date().getFullYear()
  const lo = filters.yearFrom ?? MIN_YEAR
  const hi = filters.yearTo ?? maxYear

  /** Commit a new [lo, hi] window, folding either bound back to null. */
  const commit = (nextLo: number, nextHi: number) => {
    onFilters({
      ...filters,
      yearFrom: nextLo <= MIN_YEAR ? null : nextLo,
      yearTo: nextHi >= maxYear ? null : nextHi,
    })
  }

  /** A year's position along the track as a 0–100 percentage. */
  const pct = (v: number) => ((v - MIN_YEAR) / (maxYear - MIN_YEAR)) * 100

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
          onChange={(e) => commit(Math.min(Number(e.target.value), hi), hi)}
        />
        <input
          type="range"
          className="year-range"
          style={{ zIndex: 4 }}
          min={MIN_YEAR}
          max={maxYear}
          value={hi}
          aria-label="Latest publication year"
          onChange={(e) => commit(lo, Math.max(Number(e.target.value), lo))}
        />
      </div>
      <span className="year-readout">
        {lo} – {hi}
      </span>
    </div>
  )
}

/** Render the seed-search form with its collapsible filter popover. */
export default function Search({
  query,
  onQueryChange,
  onSubmit,
  searching,
  loadingGraph,
  filters,
  onFilters,
}: SearchProps) {
  const [open, setOpen] = useState(false)
  // The field vocabulary loads lazily the first time the filter popover
  // opens, so the common no-filter path never pays the fetch. null = not
  // yet loaded.
  const [fieldOptions, setFieldOptions] = useState<string[] | null>(null)
  useEffect(() => {
    if (open && fieldOptions === null) getFields().then(setFieldOptions)
  }, [open, fieldOptions])

  const activeCount =
    (filters.yearFrom != null ? 1 : 0) +
    (filters.yearTo != null ? 1 : 0) +
    filters.fields.length

  /** Add a field of study to the filter (deduped). */
  const addField = (field: string) => {
    if (!field || filters.fields.includes(field)) return
    onFilters({ ...filters, fields: [...filters.fields, field] })
  }

  /** Remove one field of study from the filter. */
  const removeField = (field: string) => {
    onFilters({ ...filters, fields: filters.fields.filter((f) => f !== field) })
  }

  return (
    <div className="search-box">
      <form
        className="seed-search"
        onSubmit={(e) => {
          setOpen(false) // collapse the filter popover once a search is fired
          onSubmit(e)
        }}
      >
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search a paper by title, or paste an arXiv id / URL…"
          aria-label="Search for a paper to explore"
        />
        <button
          type="button"
          className={`filter-toggle ${activeCount ? 'on' : ''}`}
          onClick={() => setOpen((o) => !o)}
          title="Optional filters: publication year and field of study"
        >
          Filters{activeCount ? ` · ${activeCount}` : ''}
        </button>
        <button type="submit" disabled={searching || loadingGraph}>
          {searching ? 'Searching…' : 'Explore'}
        </button>
      </form>

      {open && (
        <div className="filter-pop">
          <YearRange filters={filters} onFilters={onFilters} />
          <div className="filter-row">
            <span className="filter-label">Field</span>
            <select
              className="cat-select"
              value=""
              aria-label="Add a field-of-study filter"
              onChange={(e) => addField(e.target.value)}
            >
              <option value="">
                {fieldOptions === null ? 'Loading fields…' : 'Add a field…'}
              </option>
              {fieldOptions?.map((field) => (
                <option key={field} value={field}>
                  {field}
                </option>
              ))}
            </select>
          </div>
          {filters.fields.length > 0 && (
            <div className="filter-cats">
              {filters.fields.map((field) => (
                <button
                  key={field}
                  className="cat-chip"
                  onClick={() => removeField(field)}
                  title="Remove this field filter"
                >
                  {field} ✕
                </button>
              ))}
            </div>
          )}
          <div className="filter-foot">
            <span className="filter-hint">
              Optional — applies to the next search (ignored for a pasted id/URL).
            </span>
            {activeCount > 0 && (
              <button
                className="link-btn"
                onClick={() => onFilters({ yearFrom: null, yearTo: null, fields: [] })}
              >
                Clear all
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
