/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Direct search: find a paper to drop into the graph, under optional
 * date / field-of-study filters.
 *
 * Since v7.6.0 the backend behind this is the paper scout run on its own —
 * one agent that writes its own queries, looks at what came back and searches
 * again — rather than the old expand-once-then-search. The filters it takes
 * are binding server-side, not hints. The separate instant cache search that
 * used to race this one is gone: the scout consults that cache itself, so
 * there is one search path again instead of two.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { readSSE } from './sse'
import type { TraceEvent } from './agents'
import type { GraphNode, Provider } from './graph'

/** Live callbacks for a direct search, which streams its progress. */
export interface DirectSearchHandlers {
  /** Papers already in the local snapshot cache, delivered in milliseconds —
   *  a provisional list to paint while the scout is still on its first
   *  provider call. Superseded by the returned result. Never fires when a
   *  field filter is active (the cache can't honor one). */
  onCached?: (papers: GraphNode[]) => void
  /** One lookup the scout just issued — rendered as a trace chip, live. */
  onTrace?: (trace: TraceEvent) => void
  /** Papers a lookup just turned up. Fires once per productive lookup, so the
   *  list grows while the scout is still working rather than appearing whole
   *  at the end. The final result supersedes the accumulation. */
  onPapers?: (papers: GraphNode[]) => void
  /** Abort signal, so a superseded search stops mid-flight. */
  signal?: AbortSignal
}

/**
 * The `/api/search` response: the echoed query, its hits, and the scout's own
 * account of the search. Hits are full graph-node shapes (the same type a
 * graph neighbor has).
 */
export interface LiveSearchResponse {
  /** The echoed query. `q` is the wire name — it's the `?q=` request
   *  parameter the backend echoes back verbatim (see routes/search.py), not
   *  a name we get to choose. */
  // oxlint-disable-next-line id-length -- wire key, see above
  q: string
  count: number
  papers: GraphNode[]
  /** The scout's one- or two-sentence account of what it found and what it
   *  couldn't — a negative result ("nothing indexed after 2021") is a real
   *  finding, and the transcript shows it above the list. */
  summary: string
  /** Every lookup it actually made, in reader-facing words, for the trace
   *  chips. Not all are queries — a semantic hop reads "similar to: <title>"
   *  and a title match "title: <title>". */
  queries: string[]
}

/**
 * Optional search filters. Everything is optional — the defaults mean "search
 * everything" — and none of it applies to an explicit arXiv id/URL lookup,
 * which resolves to exactly that paper.
 *
 * These are **binding**, not hints: they ride in the scout's deps rather than
 * its prompt, so no wording the model chooses can widen them (it may narrow
 * further inside them). They apply to the researcher's paper searches too —
 * one filter set for the whole chat bar, not one per mode.
 */
export interface SearchOptions {
  /** Earliest publication year (inclusive), or null for no floor. */
  yearFrom: number | null
  /** Latest publication year (inclusive), or null for no ceiling. */
  yearTo: number | null
  /** Fields of study to restrict to (any-of); empty = all fields. Values are
   *  provider-specific — S2 field names, OpenAlex numeric field ids. */
  fields: string[]
}

/** The default options: no filters at all — a genuinely unrestricted search. */
export const DEFAULT_SEARCH_OPTIONS: SearchOptions = {
  yearFrom: null,
  yearTo: null,
  fields: [],
}

/**
 * Append a search-option set to a query string (omitting defaults).
 *
 * @param params  The query string being built (mutated in place).
 * @param options The active options, or undefined for the defaults.
 */
function applyOptions(params: URLSearchParams, options?: SearchOptions): void {
  if (!options) return
  if (options.yearFrom != null) params.set('year_from', String(options.yearFrom))
  if (options.yearTo != null) params.set('year_to', String(options.yearTo))
  if (options.fields.length) params.set('fields', options.fields.join(','))
}

/**
 * Direct search: send the paper scout after a seed paper, alone.
 *
 * Accepts keywords, a title, an author, or a description of what's wanted. A
 * pasted arXiv id/URL never reaches here — the caller routes that straight to
 * the graph, which is exact and needs no model.
 *
 * @param query    The search query.
 * @param limit    Maximum hits per lookup (default 12).
 * @param options  Optional binding date/field filters (see
 *                 {@link SearchOptions}).
 * @param provider Which backend to search ('s2' / 'openalex') — matches the
 *                 graph provider so a hit explores under the backend that found it.
 * @param handlers Live callbacks — the scout's lookups arrive as `trace`
 *                 frames while it works, so the chips render as they happen
 *                 rather than all at once at the end.
 * @returns The echoed query plus its hits, the scout's summary, and every
 *          lookup it made.
 * @throws When the request fails or the stream ends without a result. A
 *         provider outage does NOT throw — the scout degrades internally and
 *         says so in the summary.
 */
export async function searchLive(
  query: string,
  limit = 12,
  options?: SearchOptions,
  provider: Provider = 's2',
  handlers: DirectSearchHandlers = {},
): Promise<LiveSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit), provider })
  applyOptions(params, options)
  const res = await fetch(`/api/search?${params.toString()}`, { signal: handlers.signal })
  let result: LiveSearchResponse | null = null
  let failure: string | null = null
  await readSSE(res, (event, data) => {
    if (event === 'cached') handlers.onCached?.((data as { papers: GraphNode[] }).papers)
    else if (event === 'trace') handlers.onTrace?.(data as TraceEvent)
    else if (event === 'papers') handlers.onPapers?.((data as { papers: GraphNode[] }).papers)
    else if (event === 'result') result = data as LiveSearchResponse
    else if (event === 'error') failure = (data as { message: string }).message
  })
  if (failure) throw new Error(failure)
  if (!result) throw new Error('Search ended without a result.')
  return result
}

/** One field-of-study option for the search filter picker: `id` is the filter
 *  value sent to the backend, `name` the label shown. For S2 the id is the field
 *  name itself; for OpenAlex it's the numeric field id (`topics.field.id`). */
export interface Field {
  id: string
  name: string
}

/**
 * Fetch the selected provider's field vocabulary (`/api/taxonomy/<provider>`)
 * for the search filter's field picker — S2's ~20 fields of study or OpenAlex's
 * 26 top-level fields. Both come back as `{id, name}` pairs, so the picker is
 * provider-agnostic (show `name`, send `id`).
 *
 * Never throws — failures degrade to an empty list, which simply renders the
 * picker without options.
 *
 * @param provider Which backend's vocabulary to fetch ('s2' / 'openalex').
 * @returns The field options (empty on any failure).
 */
export async function getFields(provider: Provider): Promise<Field[]> {
  try {
    const res = await fetch(`/api/taxonomy/${provider}`)
    if (!res.ok) return []
    return ((await res.json()) as { fields: Field[] }).fields ?? []
  } catch {
    return []
  }
}
