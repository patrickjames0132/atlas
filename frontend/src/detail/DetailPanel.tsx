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
import { BADGE_COLOR, BADGE_LABEL } from '../graph/theme'
import MathText from '../notation/MathText'
import { useResizablePanel } from '../ui/useResizablePanel'
import './detail.css'

/** Props for {@link DetailPanel}. */
export interface DetailPanelProps {
  /** The selected node, already merged with any hydrated detail fields. */
  node: VNode
  /** Heading for the provider field-of-study tag section ("Semantic Scholar
   *  tags" / "OpenAlex tags"), naming who classified the paper. */
  fieldsLabel: string
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

/**
 * Compact count for repo metadata: 1400 → "1.4k", 2100000 → "2.1M".
 *
 * @param count The raw count.
 * @returns The abbreviated form.
 */
function fmtCount(count: number): string {
  if (count >= 1e6) return `${(count / 1e6).toFixed(1).replace(/\.0$/, '')}M`
  if (count >= 1e3) return `${(count / 1e3).toFixed(1).replace(/\.0$/, '')}k`
  return String(count)
}

/**
 * One link-out row in the "Code & artifacts" section.
 *
 * @returns The rendered link row.
 */
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
 * "Machine Learning" categories) and a **provider tags** section — the graph
 * provider's own field classification (S2's coarse fields of study, e.g.
 * "Computer Science", or OpenAlex's finer topic labels). Each section renders
 * only when it has tags — a non-arXiv paper shows the provider section alone.
 *
 * @returns The rendered tag sections, or null when there are no tags at all.
 */
function CategoryTags({
  categories,
  fieldsOfStudy,
  fieldsLabel,
}: {
  categories?: CategoriesResponse
  fieldsOfStudy: string[]
  fieldsLabel: string
}) {
  const arxivCats = categories?.available ? categories.categories : []
  if (arxivCats.length === 0 && fieldsOfStudy.length === 0) return null
  return (
    <div className="detail-cat-groups" data-tour="detail-tags">
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
          <div className="detail-cat-head">{fieldsLabel}</div>
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

/**
 * The paper's implementations (HF Papers): GitHub repo, models, datasets, Spaces.
 *
 * @returns The rendered "Code & artifacts" section.
 */
function CodeSection({ code }: { code: CodeLinksResponse }) {
  const { totals } = code
  const totalParts = [
    totals.models > 0 && `${fmtCount(totals.models)} models`,
    totals.datasets > 0 && `${fmtCount(totals.datasets)} datasets`,
    totals.spaces > 0 && `${fmtCount(totals.spaces)} Spaces`,
  ].filter(Boolean)
  return (
    <div className="detail-code" data-tour="detail-code">
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

/**
 * Render the detail panel for the selected paper.
 *
 * @returns The docked, resizable detail panel.
 */
export default function DetailPanel({
  node,
  fieldsLabel,
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
  // Both citing relations show one "citation" badge (BADGE_LABEL), so dedupe by
  // displayed label — a node that's somehow both a landmark and latest never
  // renders "CITATION" twice. Map keeps the first relation seen for each label
  // (its colour), in node.rels order.
  const badges = new Map<string, string>()
  for (const rel of node.rels) {
    const label = BADGE_LABEL[rel] ?? rel
    if (!badges.has(label)) badges.set(label, rel)
  }
  return (
    <aside className="detail" data-tour="details" style={{ width }}>
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
        {[...badges].map(([label, rel]) => (
          <span key={label} className="badge" style={{ color: BADGE_COLOR[rel] }}>
            {label}
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
      <CategoryTags
        categories={categories}
        fieldsOfStudy={node.fields_of_study ?? []}
        fieldsLabel={fieldsLabel}
      />
      {(node.tldr || node.abstract) && (
        <div className="detail-summary-group" data-tour="detail-summary">
          <div className="detail-summary-head">{node.tldr ? 'TL;DR' : 'Abstract'}</div>
          <p className="detail-summary">
            <MathText>{node.tldr || node.abstract || ''}</MathText>
          </p>
        </div>
      )}
      <div className="detail-actions" data-tour="detail-actions">
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
        <div className="detail-figs" data-tour="detail-figures">
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
