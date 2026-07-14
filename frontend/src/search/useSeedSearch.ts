/**
 * Seed-search state for the explorer: the query box, the optional
 * date/field filters, cache-first local hits, live Semantic Scholar hits,
 * and the in-flight / failure flags HitList renders.
 *
 * The two searches race deliberately: local hits resolve near-instantly and
 * render while the live search is still in flight (or failing, when we're
 * rate-limited).
 */

import { useCallback, useState } from 'react'
import { EMPTY_FILTERS, searchLive, searchLocal } from '../api'
import type { GraphNode, LocalHit, SearchFilters } from '../api'
import { useAppSelector } from '../store'

/** What {@link useSeedSearch} returns for Atlas to wire up. */
export interface SeedSearchApi {
  /** The controlled value of the search box. */
  query: string
  setQuery: (query: string) => void
  /** The active (pre-submit, always optional) date/field filters. */
  filters: SearchFilters
  setFilters: (next: SearchFilters) => void
  /** Live S2 results (null until a search lands / after clearHits). */
  hits: GraphNode[] | null
  /** Cache-first results from previously seen graphs (null when none). */
  localHits: LocalHit[] | null
  /** The live search is still in flight. */
  searching: boolean
  /** The live search failed (rate limit / outage) — cache-only mode. */
  liveFailed: boolean
  /** Run both searches for a query (local first, live alongside). */
  runSearch: (text: string) => Promise<void>
  /** Dismiss all results (picking a hit, closing the panel, re-seeding). */
  clearHits: () => void
}

/**
 * Own the seed-search state and logic.
 *
 * @param onError Surface a search failure message (or clear one with null) —
 *                errors share Atlas's overlay with graph-load errors.
 * @returns The search state + handlers (see {@link SeedSearchApi}).
 */
export function useSeedSearch(onError: (message: string | null) => void): SeedSearchApi {
  // The local cache search is scoped to the selected provider, so a cached hit's
  // "instant" badge is truthful for the backend that would actually build it.
  const provider = useAppSelector((state) => state.workspace.provider)
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS)
  const [hits, setHits] = useState<GraphNode[] | null>(null)
  const [localHits, setLocalHits] = useState<LocalHit[] | null>(null)
  const [liveFailed, setLiveFailed] = useState(false)
  const [searching, setSearching] = useState(false)

  const clearHits = useCallback(() => {
    setHits(null)
    setLocalHits(null)
  }, [])

  /**
   * Run the seed search: local cache first (instant), live S2 alongside,
   * both under the active filters. "Nothing matched" only surfaces as an
   * error when BOTH sources come back empty; a live failure degrades to
   * cache-only rather than erroring while local hits exist.
   */
  const runSearch = useCallback(
    async (text: string) => {
      setSearching(true)
      onError(null)
      setHits(null)
      setLocalHits(null)
      setLiveFailed(false)
      // Cache-first: local hits resolve near-instantly and render while the
      // live search is still in flight (or failing, when rate-limited). Scoped
      // to the selected provider so the cached hits match what a click builds.
      const localPromise = searchLocal(text, 10, filters, provider)
      localPromise.then((local) => setLocalHits(local.length ? local : null))
      try {
        const res = await searchLive(text, 12, filters)
        setHits(res.papers)
        if (res.papers.length === 0 && (await localPromise).length === 0)
          onError(`Nothing matched "${text}" — not on Semantic Scholar, not in your cache.`)
      } catch (error) {
        setLiveFailed(true)
        if ((await localPromise).length === 0)
          onError(error instanceof Error ? error.message : String(error))
      } finally {
        setSearching(false)
      }
    },
    [onError, filters, provider],
  )

  return {
    query,
    setQuery,
    filters,
    setFilters,
    hits,
    localHits,
    searching,
    liveFailed,
    runSearch,
    clearHits,
  }
}
