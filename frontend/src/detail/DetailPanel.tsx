/**
 * The right-hand paper detail panel: relation badges, title, authors, the
 * TL;DR / abstract, code & artifact links (Hugging Face Papers), lazily-loaded
 * figures (ar5iv), and the paper actions (abstract/PDF links, pin,
 * explore-from-here).
 */

import type { CodeLinksResponse, FiguresResponse } from '../api'
import type { VNode } from '../graph/model'
import { formatPubDate } from '../graph/model'
import { REL_COLOR } from '../graph/theme'
import './detail.css'

/** Props for {@link DetailPanel}. */
export interface DetailPanelProps {
  /** The selected node, already merged with any hydrated detail fields. */
  node: VNode
  /** The node's figures, once fetched (undefined while not yet requested). */
  figures?: FiguresResponse
  /** The figure fetch for THIS node is still in flight. */
  figuresLoading: boolean
  /** The node's code & artifact links, once fetched (undefined until then). */
  codeLinks?: CodeLinksResponse
  /** Whether the node is currently pinned in place. */
  isPinned: boolean
  /** Pin/unpin the node. */
  onTogglePin: () => void
  /** Close the panel. */
  onClose: () => void
  /** Re-seed the whole graph on this paper (hidden for the current seed). */
  onExplore: (id: string) => void
}

/** Compact count for repo metadata: 1400 → "1.4k", 2100000 → "2.1M". */
function fmtCount(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

/** One link-out row in the "Code & artifacts" section. */
function CodeRow({
  href,
  icon,
  label,
  meta,
}: {
  href: string
  icon: string
  label: string
  meta?: string
}) {
  return (
    <a className="code-row" href={href} target="_blank" rel="noreferrer">
      <span className="code-icon">{icon}</span>
      <span className="code-label">{label}</span>
      {meta && <span className="code-meta">{meta}</span>}
    </a>
  )
}

/** The paper's implementations (HF Papers): GitHub repo, models, datasets, Spaces. */
function CodeSection({ code }: { code: CodeLinksResponse }) {
  const { totals } = code
  const totalParts = [
    totals.models > 0 && `${fmtCount(totals.models)} models`,
    totals.datasets > 0 && `${fmtCount(totals.datasets)} datasets`,
    totals.spaces > 0 && `${fmtCount(totals.spaces)} Spaces`,
  ].filter(Boolean)
  return (
    <div className="detail-code">
      <div className="detail-code-head">Code &amp; artifacts</div>
      {code.github && (
        <CodeRow
          href={code.github.url}
          icon="⌨"
          label={code.github.url.replace('https://github.com/', '')}
          meta={code.github.stars > 0 ? `★ ${fmtCount(code.github.stars)}` : undefined}
        />
      )}
      {code.models.slice(0, 3).map((m) => (
        <CodeRow key={m.id} href={m.url} icon="🤖" label={m.id}
          meta={m.likes > 0 ? `♥ ${fmtCount(m.likes)}` : undefined} />
      ))}
      {code.datasets.slice(0, 2).map((d) => (
        <CodeRow key={d.id} href={d.url} icon="🗃" label={d.id}
          meta={d.likes > 0 ? `♥ ${fmtCount(d.likes)}` : undefined} />
      ))}
      {code.spaces.slice(0, 2).map((s) => (
        <CodeRow key={s.id} href={s.url} icon={s.emoji || '🚀'} label={s.id} />
      ))}
      {code.paper_url && (
        <a className="code-more" href={code.paper_url} target="_blank" rel="noreferrer">
          {totalParts.length > 0
            ? `${totalParts.join(' · ')} on HF Papers ↗`
            : 'View on HF Papers ↗'}
        </a>
      )}
    </div>
  )
}

/** Render the detail panel for the selected paper. */
export default function DetailPanel({
  node,
  figures,
  figuresLoading,
  codeLinks,
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
          <button className="explore-btn" onClick={() => onExplore(node.id)}>
            Explore from here →
          </button>
        )}
      </div>
      {codeLinks && codeLinks.available && <CodeSection code={codeLinks} />}
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
    </aside>
  )
}
