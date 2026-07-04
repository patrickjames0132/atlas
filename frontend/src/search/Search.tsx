/**
 * The seed-search form: the query box + Explore button, plus the optional
 * (never required) pre-submit filters — a publication-year window and an
 * arXiv category picker fed by the backend's taxonomy endpoint.
 *
 * Rendered inside AtlasHeader, but it belongs to the search concern — its
 * results (HitList) and state (useSeedSearch) live alongside it here. Filter
 * state lives in useSeedSearch (via Atlas) so runSearch reads it directly;
 * this component only renders and edits it.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getTaxonomy } from '../api'
import type { SearchFilters, TaxonomyGroup } from '../api'
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

/** arXiv's first year — the year slider's floor. */
const MIN_YEAR = 1991

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
 * active-filter badge), while losing nothing — 1991 and the current year are
 * the widest bounds arXiv can return anyway.
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
  // The taxonomy loads lazily the first time the filter popover opens, so the
  // common no-filter path never pays the fetch. null = not yet loaded.
  const [groups, setGroups] = useState<TaxonomyGroup[] | null>(null)
  useEffect(() => {
    if (open && groups === null) getTaxonomy().then(setGroups)
  }, [open, groups])

  const activeCount =
    (filters.yearFrom != null ? 1 : 0) +
    (filters.yearTo != null ? 1 : 0) +
    filters.categories.length

  /** Add a category code to the filter (deduped). */
  const addCategory = (code: string) => {
    if (!code || filters.categories.includes(code)) return
    onFilters({ ...filters, categories: [...filters.categories, code] })
  }

  /** Remove one category code from the filter. */
  const removeCategory = (code: string) => {
    onFilters({ ...filters, categories: filters.categories.filter((c) => c !== code) })
  }

  return (
    <div className="search-box">
      <form className="seed-search" onSubmit={onSubmit}>
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
          title="Optional filters: publication year and arXiv category"
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
            <span className="filter-label">Category</span>
            <select
              className="cat-select"
              value=""
              aria-label="Add an arXiv category filter"
              onChange={(e) => addCategory(e.target.value)}
            >
              <option value="">
                {groups === null ? 'Loading categories…' : 'Add a category…'}
              </option>
              {groups?.map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.categories.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.code} — {c.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {filters.categories.length > 0 && (
            <div className="filter-cats">
              {filters.categories.map((code) => (
                <button
                  key={code}
                  className="cat-chip"
                  onClick={() => removeCategory(code)}
                  title="Remove this category filter"
                >
                  {code} ✕
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
                onClick={() => onFilters({ yearFrom: null, yearTo: null, categories: [] })}
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
