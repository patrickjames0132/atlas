/**
 * The seed-search form: the query box + Explore button that kicks off a
 * keyword search (or jumps straight to a graph for a pasted arXiv id/URL —
 * the routing lives in Atlas's onSubmit).
 *
 * Rendered inside AtlasHeader, but it belongs to the search concern — its
 * results (HitList) and state (useSeedSearch) live alongside it here.
 */

import type { FormEvent } from 'react'
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
}

/** Render the seed-search form. */
export default function Search({
  query,
  onQueryChange,
  onSubmit,
  searching,
  loadingGraph,
}: SearchProps) {
  return (
    <form className="seed-search" onSubmit={onSubmit}>
      <input
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Search a paper by title, or paste an arXiv id / URL…"
        aria-label="Search for a paper to explore"
      />
      <button type="submit" disabled={searching || loadingGraph}>
        {searching ? 'Searching…' : 'Explore'}
      </button>
    </form>
  )
}
