/**
 * The seed-search results panel: cache-first local hits render immediately,
 * live arXiv hits stream in under them (deduped against the local ones), and
 * clicking any hit loads its graph. arXiv hits show their publication date.
 */

import type { ArxivHit, LocalHit } from '../api'
import { formatPubDate } from '../graph/model'
import './search.css'

/** Props for {@link HitList}. */
export interface HitListProps {
  /** Live arXiv results (null until the search lands / when dismissed). */
  hits: ArxivHit[] | null
  /** Cache-first results from previously seen graphs (null when none). */
  localHits: LocalHit[] | null
  /** The live arXiv search is still in flight. */
  searching: boolean
  /** The live arXiv search failed (rate limit / outage) — cache-only mode. */
  arxivFailed: boolean
  /** Load a graph for the picked seed (an arXiv id or S2 paperId). */
  onPick: (seed: string) => void
  /** Dismiss the panel. */
  onClose: () => void
}

/**
 * Render the pick-a-paper panel. Returns null when there's nothing to show
 * (no local hits resolved and no live search outcome yet).
 */
export default function HitList({
  hits,
  localHits,
  searching,
  arxivFailed,
  onPick,
  onClose,
}: HitListProps) {
  if (!hits && !localHits) return null
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
                {h.authors ? `${h.authors} · ` : ''}
                {h.year ?? '—'} ·{' '}
                {(h.citation_count ?? 0).toLocaleString()} citations
              </div>
            </button>
          ))}
        </>
      )}
      {localHits && (searching || hits || arxivFailed) && (
        <div className="hit-sub">From arXiv</div>
      )}
      {searching && <div className="hit-note">Searching arXiv…</div>}
      {arxivFailed && (
        <div className="hit-note">
          arXiv search unavailable — showing cached papers only.
        </div>
      )}
      {hits && hits.length === 0 && !searching && (
        <div className="hit-note">No results from arXiv.</div>
      )}
      {hits
        ?.filter((h) => !localHits?.some((l) => l.arxiv_id === h.arxiv_id))
        .map((h) => (
          <button key={h.arxiv_id} className="hit" onClick={() => onPick(h.arxiv_id)}>
            <div className="hit-title">{h.title}</div>
            <div className="hit-meta">
              <span className="hit-date">{formatPubDate(h.published)}</span>
              {' · '}
              {h.authors} · {h.arxiv_id}
            </div>
          </button>
        ))}
    </div>
  )
}
