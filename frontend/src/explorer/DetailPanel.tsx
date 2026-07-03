/**
 * The right-hand paper detail panel: relation badges, title, authors, the
 * TL;DR / abstract, lazily-loaded figures (ar5iv), and the paper actions
 * (abstract/PDF links, pin, explore-from-here).
 */

import type { FiguresResponse } from '../api'
import type { VNode } from './model'
import { formatPubDate } from './model'
import { REL_COLOR } from './theme'

/** Props for {@link DetailPanel}. */
export interface DetailPanelProps {
  /** The selected node, already merged with any hydrated detail fields. */
  node: VNode
  /** The node's figures, once fetched (undefined while not yet requested). */
  figures?: FiguresResponse
  /** The figure fetch for THIS node is still in flight. */
  figuresLoading: boolean
  /** Whether the node is currently pinned in place. */
  isPinned: boolean
  /** Pin/unpin the node. */
  onTogglePin: () => void
  /** Close the panel. */
  onClose: () => void
  /** Re-seed the whole graph on this paper (hidden for the current seed). */
  onExplore: (id: string) => void
}

/** Render the detail panel for the selected paper. */
export default function DetailPanel({
  node,
  figures,
  figuresLoading,
  isPinned,
  onTogglePin,
  onClose,
  onExplore,
}: DetailPanelProps) {
  return (
    <aside className="detail">
      <button className="link-btn close" onClick={onClose}>
        ✕
      </button>
      <div className="detail-badges">
        {node.rels.map((r) => (
          <span key={r} className="badge" style={{ color: REL_COLOR[r] }}>
            {r}
          </span>
        ))}
      </div>
      <h2>{node.title}</h2>
      <div className="detail-meta">
        {node.authors && <div>{node.authors}</div>}
        <div>
          {formatPubDate(node.pub_date, node.year)} ·{' '}
          {(node.citation_count ?? 0).toLocaleString()} citations
        </div>
      </div>
      {(node.tldr || node.abstract) && (
        <p className="detail-summary">
          {node.tldr ? (
            <>
              <strong>TL;DR </strong>
              {node.tldr}
            </>
          ) : (
            node.abstract
          )}
        </p>
      )}
      {node.arxiv_id && !figures && figuresLoading && (
        <div className="detail-figs-hint">Loading figures…</div>
      )}
      {figures && figures.available && figures.figures.length > 0 && (
        <div className="detail-figs">
          <div className="detail-figs-head">Figures</div>
          {figures.figures.map((f, i) => (
            <figure key={i} className="detail-fig">
              <img src={f.image} alt={f.caption || `Figure ${i + 1}`} loading="lazy" />
              {f.caption && <figcaption>{f.caption}</figcaption>}
            </figure>
          ))}
        </div>
      )}
      <div className="detail-actions">
        {node.url && (
          <a href={node.url} target="_blank" rel="noreferrer">
            Abstract ↗
          </a>
        )}
        {node.url && node.arxiv_id && (
          <a href={node.url.replace('/abs/', '/pdf/')} target="_blank" rel="noreferrer">
            PDF ↗
          </a>
        )}
        <button className="ghost-btn" onClick={onTogglePin}>
          {isPinned ? 'Unpin' : 'Pin'}
        </button>
        {!node.is_seed && (
          <button onClick={() => onExplore(node.id)}>Explore from here →</button>
        )}
      </div>
    </aside>
  )
}
