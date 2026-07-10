/**
 * The right-hand paper detail panel: relation badges, title, authors, the
 * TL;DR / abstract, its own arXiv category tags, code & artifact links
 * (Hugging Face Papers), lazily-loaded figures (ar5iv, click-to-enlarge via
 * the shared lightbox), and the paper actions (abstract/PDF links, pin,
 * explore-from-here).
 */

import type { AnswerFigure, CategoriesResponse, CodeLinksResponse, FiguresResponse } from '../api'
import type { VNode } from '../graph/model'
import { formatPubDate } from '../graph/model'
import { REL_COLOR } from '../graph/theme'
import MathText from '../notation/MathText'
import { useResizablePanel } from '../ui/useResizablePanel'
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
  /** The node's own arXiv category tags, once fetched (undefined until then). */
  categories?: CategoriesResponse
  /** Open a figure full-screen (the shared lightbox — GraphExplorer owns it). */
  onEnlarge: (figure: AnswerFigure) => void
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
function fmtCount(count: number): string {
  if (count >= 1e6) return `${(count / 1e6).toFixed(1).replace(/\.0$/, '')}M`
  if (count >= 1e3) return `${(count / 1e3).toFixed(1).replace(/\.0$/, '')}k`
  return String(count)
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

/**
 * A paper's category tags, split into **provider-labeled sections** so it's
 * clear who tagged what: an **arXiv tags** section (its own `cs.LG` →
 * "Machine Learning" categories) and a **Semantic Scholar tags** section
 * (S2's coarser field-of-study classification, e.g. "Computer Science").
 * Each section renders only when it has tags — a non-arXiv paper shows the
 * S2 section alone.
 */
function CategoryTags({
  categories,
  fieldsOfStudy,
}: {
  categories?: CategoriesResponse
  fieldsOfStudy: string[]
}) {
  const arxivCats = categories?.available ? categories.categories : []
  if (arxivCats.length === 0 && fieldsOfStudy.length === 0) return null
  return (
    <div className="detail-cat-groups">
      {arxivCats.length > 0 && (
        <div className="detail-cat-group">
          <div className="detail-cat-head">arXiv tags</div>
          <div className="detail-cats">
            {arxivCats.map((category) => (
              <span key={category.code} className="detail-cat" title={category.code}>
                {category.name}
              </span>
            ))}
          </div>
        </div>
      )}
      {fieldsOfStudy.length > 0 && (
        <div className="detail-cat-group">
          <div className="detail-cat-head">Semantic Scholar tags</div>
          <div className="detail-cats">
            {fieldsOfStudy.map((field) => (
              <span key={field} className="detail-cat s2">
                {field}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
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
      {code.models.slice(0, 3).map((model) => (
        <CodeRow
          key={model.id}
          href={model.url}
          icon="🤖"
          label={model.id}
          meta={model.likes > 0 ? `♥ ${fmtCount(model.likes)}` : undefined}
        />
      ))}
      {code.datasets.slice(0, 2).map((dataset) => (
        <CodeRow
          key={dataset.id}
          href={dataset.url}
          icon="🗃"
          label={dataset.id}
          meta={dataset.likes > 0 ? `♥ ${fmtCount(dataset.likes)}` : undefined}
        />
      ))}
      {code.spaces.slice(0, 2).map((space) => (
        <CodeRow key={space.id} href={space.url} icon={space.emoji || '🚀'} label={space.id} />
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
  categories,
  onEnlarge,
  isPinned,
  onTogglePin,
  onClose,
  onExplore,
}: DetailPanelProps) {
  const { width, onHandlePointerDown, dragging } = useResizablePanel('atlas.detailWidth', 340)
  return (
    <aside className="detail" style={{ width }}>
      <div
        className={`panel-resize-handle${dragging ? ' dragging' : ''}`}
        onPointerDown={onHandlePointerDown}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
      />
      <button className="link-btn close" onClick={onClose}>
        ✕
      </button>
      <div className="detail-badges">
        {node.rels.map((rel) => (
          <span key={rel} className="badge" style={{ color: REL_COLOR[rel] }}>
            {rel}
          </span>
        ))}
      </div>
      <h2>
        <MathText>{node.title}</MathText>
      </h2>
      <div className="detail-meta">
        {node.authors && <div>{node.authors}</div>}
        <div>
          {formatPubDate(node.pub_date, node.year)} · {(node.citation_count ?? 0).toLocaleString()}{' '}
          citations
        </div>
      </div>
      <CategoryTags categories={categories} fieldsOfStudy={node.fields_of_study ?? []} />
      {(node.tldr || node.abstract) && (
        <p className="detail-summary">
          {node.tldr ? (
            <>
              <strong>TL;DR </strong>
              <MathText>{node.tldr}</MathText>
            </>
          ) : (
            <MathText>{node.abstract}</MathText>
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
          {figures.figures.map((figure, index) => (
            <figure key={index} className="detail-fig">
              <button
                type="button"
                className="detail-fig-btn"
                onClick={() =>
                  onEnlarge({ image: figure.image, caption: figure.caption, title: null })
                }
                title="Click to enlarge"
                aria-label="Enlarge figure"
              >
                <img
                  src={figure.image}
                  alt={figure.caption || `Figure ${index + 1}`}
                  loading="lazy"
                />
              </button>
              {figure.caption && (
                <figcaption>
                  <MathText>{figure.caption}</MathText>
                </figcaption>
              )}
            </figure>
          ))}
        </div>
      )}
    </aside>
  )
}
