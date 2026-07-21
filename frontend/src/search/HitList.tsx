/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The seed-search results panel: cache-first local hits render immediately,
 * live hits from the selected provider (Semantic Scholar / OpenAlex) stream in
 * under them (deduped against the local ones), and clicking any hit loads its
 * graph. Both the cache section and the live section are labeled with the active
 * provider, so it's clear which backend the results come from. When the query
 * named a paper the analyst recognized, its verified match leads the live list.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { GraphNode, LocalHit } from '../api'
import { formatPubDate } from '../graph/model'
import MathText from '../notation/MathText'
import './search.css'

/** Props for {@link HitList}. */
export interface HitListProps {
  /** Live results from the selected provider (null until the search lands). */
  hits: GraphNode[] | null
  /** Cache-first results from previously seen graphs (null when none). */
  localHits: LocalHit[] | null
  /** The live search is still in flight. */
  searching: boolean
  /** The live search failed (rate limit / outage) — cache-only mode. */
  liveFailed: boolean
  /** Display name of the active provider ("Semantic Scholar" / "OpenAlex") —
   *  the live-search section is labeled with it. */
  providerLabel: string
  /** Load a graph for the picked seed (a provider node id / arXiv id). */
  onPick: (seed: string) => void
  /** Dismiss the panel. */
  onClose: () => void
}

/**
 * Reference-style authors: "A & B" up to two names, "A et al." beyond —
 * a hit list wants recognition, not the full roster.
 *
 * @param authors The comma-separated author string, when known.
 * @returns The abbreviated form, or null when there are no authors.
 */
function refAuthors(authors?: string | null): string | null {
  if (!authors) return null
  const names = authors.split(', ')
  if (names.length <= 2) return names.join(' & ')
  return `${names[0]} et al.`
}

/**
 * Render the pick-a-paper panel. Visible from the moment a search starts —
 * the "Searching…" note is immediate feedback while the analyst + S2 work,
 * and cache hits render the instant they resolve, never gated on the live
 * search.
 *
 * @returns The rendered hit panel, or null when there's nothing to show.
 */
export default function HitList({
  hits,
  localHits,
  searching,
  liveFailed,
  providerLabel,
  onPick,
  onClose,
}: HitListProps) {
  if (!hits && !localHits && !searching) return null
  return (
    <div className="hit-list">
      <div className="hit-head">
        Pick a paper to explore
        <button className="link-btn" onClick={onClose}>
          ✕
        </button>
      </div>
      {localHits && (
        <>
          <div className="hit-sub">From your {providerLabel} cache</div>
          {localHits.map((hit) => (
            <button key={hit.id} className="hit" onClick={() => onPick(hit.arxiv_id ?? hit.id)}>
              <div className="hit-title">
                <MathText>{hit.title}</MathText>
                {hit.has_graph && (
                  <span
                    className="hit-badge"
                    title="Graph snapshot cached — explores without hitting the API"
                  >
                    instant
                  </span>
                )}
              </div>
              <div className="hit-meta">
                {refAuthors(hit.authors) ? `${refAuthors(hit.authors)} · ` : ''}
                {hit.year ?? '—'} · {(hit.citation_count ?? 0).toLocaleString()} citations
              </div>
            </button>
          ))}
        </>
      )}
      {localHits && (searching || hits || liveFailed) && (
        <div className="hit-sub">From {providerLabel}</div>
      )}
      {searching && (
        <div className="hit-note">
          <span className="spin" /> Searching {providerLabel}…
        </div>
      )}
      {liveFailed && (
        <div className="hit-note">Live search unavailable — showing cached papers only.</div>
      )}
      {hits && hits.length === 0 && !searching && (
        <div className="hit-note">No results from {providerLabel}.</div>
      )}
      {hits
        ?.filter((hit) => !localHits?.some((local) => local.id === hit.id))
        .map((hit) => (
          <button key={hit.id} className="hit" onClick={() => onPick(hit.arxiv_id ?? hit.id)}>
            <div className="hit-title">
              <MathText>{hit.title}</MathText>
            </div>
            <div className="hit-meta">
              <span className="hit-date">{formatPubDate(hit.pub_date, hit.year)}</span>
              {' · '}
              {refAuthors(hit.authors) ? `${refAuthors(hit.authors)} · ` : ''}
              {(hit.citation_count ?? 0).toLocaleString()} citations
            </div>
          </button>
        ))}
    </div>
  )
}
