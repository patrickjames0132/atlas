/**
 * The seed-search results panel: cache-first local hits render immediately,
 * live Semantic Scholar hits stream in under them (deduped against the local
 * ones), and clicking any hit loads its graph. When the query named a paper
 * the analyst recognized, its verified match leads the live list.
 */

import type { GraphNode, LocalHit } from '../api'
import { formatPubDate } from '../graph/model'
import './search.css'

/** Props for {@link HitList}. */
export interface HitListProps {
  /** Live S2 results (null until the search lands / when dismissed). */
  hits: GraphNode[] | null
  /** Cache-first results from previously seen graphs (null when none). */
  localHits: LocalHit[] | null
  /** The live search is still in flight. */
  searching: boolean
  /** The live search failed (rate limit / outage) — cache-only mode. */
  liveFailed: boolean
  /** Load a graph for the picked seed (an arXiv id or S2 paperId). */
  onPick: (seed: string) => void
  /** Dismiss the panel. */
  onClose: () => void
}

/**
 * Reference-style authors: "A & B" up to two names, "A et al." beyond —
 * a hit list wants recognition, not the full roster.
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
 */
export default function HitList({
  hits,
  localHits,
  searching,
  liveFailed,
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
          <div className="hit-sub">From your cache</div>
          {localHits.map((h) => (
            <button
              key={h.id}
              className="hit"
              onClick={() => onPick(h.arxiv_id ?? h.id)}
            >
              <div className="hit-title">
                {h.title}
                {h.has_graph && (
                  <span
                    className="hit-badge"
                    title="Graph snapshot cached — explores without hitting the API"
                  >
                    instant
                  </span>
                )}
              </div>
              <div className="hit-meta">
                {refAuthors(h.authors) ? `${refAuthors(h.authors)} · ` : ''}
                {h.year ?? '—'} ·{' '}
                {(h.citation_count ?? 0).toLocaleString()} citations
              </div>
            </button>
          ))}
        </>
      )}
      {localHits && (searching || hits || liveFailed) && (
        <div className="hit-sub">From Semantic Scholar</div>
      )}
      {searching && <div className="hit-note">Searching Semantic Scholar…</div>}
      {liveFailed && (
        <div className="hit-note">
          Live search unavailable — showing cached papers only.
        </div>
      )}
      {hits && hits.length === 0 && !searching && (
        <div className="hit-note">No results from Semantic Scholar.</div>
      )}
      {hits
        ?.filter((h) => !localHits?.some((l) => l.id === h.id))
        .map((h) => (
          <button key={h.id} className="hit" onClick={() => onPick(h.arxiv_id ?? h.id)}>
            <div className="hit-title">{h.title}</div>
            <div className="hit-meta">
              <span className="hit-date">{formatPubDate(h.pub_date, h.year)}</span>
              {' · '}
              {refAuthors(h.authors) ? `${refAuthors(h.authors)} · ` : ''}
              {(h.citation_count ?? 0).toLocaleString()} citations
            </div>
          </button>
        ))}
    </div>
  )
}
