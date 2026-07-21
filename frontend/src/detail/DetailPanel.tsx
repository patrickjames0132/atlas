/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The right-hand paper detail panel: relation badges, title, authors, the
 * TL;DR / abstract, its own arXiv category tags, code & artifact links
 * (Hugging Face Papers), lazily-loaded figures (ar5iv, or floats mined from
 * the paper's open-access PDF for papers off arXiv — click-to-enlarge via
 * the shared lightbox), and the paper actions (abstract/PDF links, pin,
 * explore-from-here).
 *
 * The late-arriving sections (summary hydration, arXiv tags, code links,
 * figures) load behind ONE joint gate: while any of the node's fetches is
 * still in flight, every one of those sections holds its place with a
 * shimmering skeleton, and they all reveal together in a single paint once
 * the last answer lands (Patrick's call — figures beating the abstract in
 * read as jank; empty sections simply don't appear at the reveal). The
 * node-local parts (badges, title, meta, actions) render instantly — they
 * never load, so they never pop. Skeletons are anonymous gray shapes — no
 * section heads — because a section may turn out empty and a named header
 * that then vanishes would be its own jank.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useState } from 'react'
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
  /** The node's summary hydration (abstract/TL;DR) is still in flight —
   *  the summary section holds its place with a skeleton. */
  detailLoading?: boolean
  /** Heading for the provider field-of-study tag section ("Semantic Scholar
   *  tags" / "OpenAlex tags"), naming who classified the paper. */
  fieldsLabel: string
  /** The node's figures, once fetched (undefined while still in flight —
   *  the fetch fires for every paper, and failures cache as unavailable, so
   *  undefined can only mean pending). arXiv papers join the panel's joint
   *  loading gate; papers off arXiv reveal theirs when the (slower) OA-PDF
   *  mining answers, without holding the rest of the panel hostage. */
  figures?: FiguresResponse
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
  /** Generate a TL;DR for a paper that has none (resolves once the node's
   *  `tldr` is merged in). The ONLY surface allowed to trigger a generation —
   *  it runs on the explicit TL;DR toggle, never automatically, so unread
   *  papers never bill. */
  onGenerateTldr?: () => Promise<void>
}

/**
 * The one summary section: the abstract by default, a TL;DR view one click
 * away. Both providers land here — S2 papers usually bring their own TL;DR,
 * and a paper without one (every OpenAlex paper, plus S2's gaps) generates
 * it via `onGenerateTldr` on the FIRST toggle only: the ✦ on the tab marks
 * that clicking it runs Claude once (then the server's cache serves it
 * forever). Papers with only one of the two render it plainly, no tabs.
 *
 * @returns The summary section, or null when the node has neither text.
 */
function SummarySection({
  node,
  onGenerateTldr,
}: {
  node: VNode
  onGenerateTldr?: () => Promise<void>
}) {
  const [view, setView] = useState<'abstract' | 'tldr'>('abstract')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // A different paper resets the section to its abstract-first default.
  useEffect(() => {
    setView('abstract')
    setPending(false)
    setError(null)
  }, [node.id])
  if (!node.tldr && !node.abstract) return null
  const canGenerate = !!onGenerateTldr && !!node.abstract
  const showTabs = !!node.abstract && (!!node.tldr || canGenerate)
  // No abstract means the TL;DR is all there is to show (and vice versa).
  const shown = node.abstract ? view : 'tldr'
  const onTldrTab = () => {
    setView('tldr')
    if (node.tldr || pending || !canGenerate) return
    setPending(true)
    setError(null)
    onGenerateTldr!()
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setPending(false))
  }
  return (
    <div className="detail-summary-group" data-tour="detail-summary">
      {showTabs ? (
        <div className="detail-summary-tabs">
          <button className={shown === 'abstract' ? 'on' : ''} onClick={() => setView('abstract')}>
            Abstract
          </button>
          <button
            className={shown === 'tldr' ? 'on' : ''}
            onClick={onTldrTab}
            title={
              node.tldr
                ? undefined
                : 'Generate a one-sentence TL;DR with Claude — runs once, then it’s cached for good'
            }
          >
            TL;DR{node.tldr ? '' : ' ✦'}
          </button>
        </div>
      ) : (
        <div className="detail-summary-head">{shown === 'tldr' ? 'TL;DR' : 'Abstract'}</div>
      )}
      {shown === 'tldr' && !node.tldr ? (
        <p className={`detail-summary ${error ? 'detail-summary-error' : 'detail-summary-muted'}`}>
          {pending ? 'Summarizing…' : (error ?? '')}
        </p>
      ) : (
        <p className="detail-summary">
          <MathText>{(shown === 'tldr' ? node.tldr : node.abstract) || ''}</MathText>
        </p>
      )}
    </div>
  )
}

/**
 * A shimmering placeholder block holding a loading section's place. Purely
 * decorative (hidden from the accessibility tree); shape comes from the
 * variant class.
 *
 * @returns The skeleton element.
 */
function Skeleton({ variant }: { variant: 'line' | 'line-short' | 'chip' | 'row' | 'fig' }) {
  return <span className={`skel skel-${variant}`} aria-hidden="true" />
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
 * While the arXiv-tag fetch is in flight (`arxivPending`), that section's
 * slot holds a chip skeleton instead of popping in later.
 *
 * @returns The rendered tag sections, or null when there are no tags at all.
 */
function CategoryTags({
  categories,
  arxivPending,
  fieldsOfStudy,
  fieldsLabel,
}: {
  categories?: CategoriesResponse
  arxivPending: boolean
  fieldsOfStudy: string[]
  fieldsLabel: string
}) {
  const arxivCats = categories?.available ? categories.categories : []
  if (arxivCats.length === 0 && fieldsOfStudy.length === 0 && !arxivPending) return null
  return (
    <div className="detail-cat-groups" data-tour="detail-tags">
      {arxivPending ? (
        <div className="detail-cats">
          <Skeleton variant="chip" />
          <Skeleton variant="chip" />
        </div>
      ) : (
        arxivCats.length > 0 && (
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
        )
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
  detailLoading,
  fieldsLabel,
  figures,
  codeLinks,
  categories,
  onEnlarge,
  isPinned,
  onTogglePin,
  onClose,
  onExplore,
  onGenerateTldr,
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
  // ONE joint gate for every loadable section. The arXiv-keyed fetches fire
  // on first open for every arXiv paper and cache their failures, so an
  // undefined response with an arxiv_id can only mean "in flight"; summary
  // hydration reports through `detailLoading`. While ANY of them is pending,
  // every loadable section shows its skeleton — even one whose answer came
  // back early — and the whole set reveals in a single paint at the end.
  const pending =
    !!detailLoading ||
    (!!node.arxiv_id &&
      (categories === undefined || codeLinks === undefined || figures === undefined))
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
        {node.authors && <div>Authors: {node.authors}</div>}
        {node.venue && (
          <div className="detail-venue" title="Publication venue">
            Publisher: <i>{node.venue}</i>
          </div>
        )}
        <div>
          {formatPubDate(node.pub_date, node.year)} · {(node.citation_count ?? 0).toLocaleString()}{' '}
          citations
        </div>
      </div>
      <CategoryTags
        categories={pending ? undefined : categories}
        arxivPending={pending && !!node.arxiv_id}
        fieldsOfStudy={node.fields_of_study ?? []}
        fieldsLabel={fieldsLabel}
      />
      {pending ? (
        <div className="detail-summary-skel">
          <Skeleton variant="line" />
          <Skeleton variant="line" />
          <Skeleton variant="line-short" />
        </div>
      ) : (
        <SummarySection node={node} onGenerateTldr={onGenerateTldr} />
      )}
      <div className="detail-actions" data-tour="detail-actions">
        {node.url && (
          <a href={node.url} target="_blank" rel="noreferrer">
            Abstract ↗
          </a>
        )}
        {node.url && node.arxiv_id ? (
          <a href={node.url.replace('/abs/', '/pdf/')} target="_blank" rel="noreferrer">
            PDF ↗
          </a>
        ) : (
          node.oa_pdf && (
            <a href={node.oa_pdf} target="_blank" rel="noreferrer">
              PDF ↗
            </a>
          )
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
      {pending && node.arxiv_id && (
        <div className="detail-code-skel">
          <Skeleton variant="row" />
          <Skeleton variant="row" />
        </div>
      )}
      {!pending && codeLinks && codeLinks.available && <CodeSection code={codeLinks} />}
      {pending && node.arxiv_id && (
        <div className="detail-figs-skel">
          <Skeleton variant="fig" />
        </div>
      )}
      {!pending && figures && figures.available && figures.figures.length > 0 && (
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
