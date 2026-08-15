/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Render an agent answer as Markdown + LaTeX. The researcher replies in
 * Markdown (headers, bold, lists, tables) with `$…$` math and
 * inline `[n]` citation markers; this turns all three into real output:
 *   • Markdown structure via remark-gfm,
 *   • math via remark-math + rehype-katex (the same KaTeX the rest of the app
 *     uses through `MathText` — beats, the detail panel, and search hits keep
 *     `MathText`; only answers get the fuller Markdown treatment),
 *   • `[n]` markers via `remarkCite`, made clickable when the answer's `graphRefs`
 *     map resolves them to a graph node (glowing that one paper on click) —
 *     and, with no graph to glow, resolved through `paperRefs` into a button
 *     that maps that paper instead,
 *   • `[Sn, p.N]` markers, rendered as the library source's real title and
 *     page from the answer's `sourceRefs` map.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useMemo } from 'react'
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import type { PaperRef, Provider, SourceRef } from '../../api'
import { PROVIDER_LABEL } from '../../api'
import { remarkCite } from './remarkCite'

const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkCite]
const REHYPE_PLUGINS = [rehypeKatex]

/**
 * One node, lit — the companion to `GraphGlyph`, marking the chips that
 * spotlight a paper already on the canvas. Deliberately the *same* motif with
 * the meaningful difference carried by the shape: one node glowing rather than
 * three wired together, which is exactly how the two clicks differ.
 *
 * @returns The inline glyph.
 */
function SpotlightGlyph() {
  return (
    <svg className="cite-ref-glyph" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      <circle
        cx="6"
        cy="6"
        r="4.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
        opacity="0.5"
      />
      <circle cx="6" cy="6" r="1.9" fill="currentColor" />
    </svg>
  )
}

/**
 * Three nodes and two edges — the app's own motif for "this builds a map",
 * marking the citation chips that seed a graph apart from the ones that
 * spotlight a paper already on it. Drawn rather than typed: no glyph in the
 * unicode block reads as a citation graph, and the ones that come close
 * (⁂, ⌗) render inconsistently across fonts. `currentColor` so it inherits
 * the chip's own colour through hover and focus.
 *
 * @returns The inline glyph.
 */
function GraphGlyph() {
  return (
    <svg className="cite-ref-glyph" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      <line x1="2.5" y1="9" x2="6" y2="3.5" stroke="currentColor" strokeWidth="1" />
      <line x1="6" y1="3.5" x2="9.5" y2="8" stroke="currentColor" strokeWidth="1" />
      <circle cx="6" cy="3" r="1.6" fill="currentColor" />
      <circle cx="2.5" cy="9.2" r="1.4" fill="currentColor" />
      <circle cx="9.5" cy="8.2" r="1.4" fill="currentColor" />
    </svg>
  )
}

/**
 * Render an answer's Markdown + math + clickable `[n]` citations.
 *
 * @returns The rendered answer body.
 */
export default function AnswerMarkdown({
  text,
  graphRefs,
  sourceRefs,
  paperRefs,
  onRefClick,
  onGraphIds,
  onPaperSeed,
  provider,
}: {
  text: string
  /** `[n]` → node-id map for this answer (undefined on old saves / none). */
  graphRefs?: Record<string, string>
  /** `[n]` → paper (title + URL), the fallback when there's no graph to
   *  resolve a marker against. */
  paperRefs?: Record<string, PaperRef>
  /** `[Sn]` index → library source, for rendering a marker as its real title
   *  (undefined on old saves, or when the turn cited no library passage). */
  sourceRefs?: Record<string, SourceRef>
  /** Spotlight one paper on the graph (undefined = markers render inert). */
  onRefClick?: (nodeId: string) => void
  /** Every paper id the workspace currently holds. A `[n]` resolving to an id
   *  outside it renders greyed and inert — see the stale branch below.
   *  Undefined skips the check entirely (nothing to check against). */
  onGraphIds?: Set<string>
  /** Build a graph seeded on a cited paper — the graph-free counterpart of
   *  `onRefClick`, which needs a graph to point at. Undefined falls back to
   *  linking out to the paper's own page. */
  onPaperSeed?: (nodeId: string, refProvider?: Provider) => void
  /** The backend currently selected. Only used to warn, in the tooltip, when a
   *  citation was minted by the *other* one — mapping it moves the workspace
   *  there, and a reader deserves to know that before clicking. */
  provider?: Provider
}) {
  const components = useMemo<Components>(
    () => ({
      // Links always open in a new tab — an answer lives in a docked panel.
      a: ({ href, children }) => (
        <a href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      ),
      // The synthetic citation element from remarkCite. Clickable only when its
      // index resolves to a node; otherwise it degrades to the bare `[n]` text.
      citeref: ({ index, children }: { index?: string; children?: ReactNode }) => {
        const nodeId = index && graphRefs ? graphRefs[index] : undefined
        // Cited a paper that isn't on the graph any more. Only reachable since
        // a chat-seeded jump started carrying the conversation across a graph
        // change: the marker resolved fine when it was written, and the paper
        // it names is real, but clicking would now highlight nothing. Render
        // it as quiet, inert text that says so rather than a live-looking
        // control that no-ops.
        if (nodeId && onGraphIds && !onGraphIds.has(nodeId)) {
          return (
            <span className="cite-ref cite-ref-stale" title="Not on the graph currently open">
              {children}
            </span>
          )
        }
        if (nodeId && onRefClick) {
          return (
            <button
              type="button"
              className="cite-ref cite-ref-spot"
              title="Show this paper on the graph"
              onClick={(event) => {
                event.stopPropagation() // don't also trigger the whole-answer re-light
                onRefClick(nodeId)
              }}
            >
              {children}
              <SpotlightGlyph />
            </button>
          )
        }
        // No graph to point at, but the server resolved the marker to a real
        // paper — so the click *maps* it. The chip stays the bare `[n]` the
        // prose was written around (a full title inline derailed the sentence,
        // twice over when two papers back a claim); the title moves to the
        // tooltip, and the glyph marks this as the chip that builds a graph
        // rather than lighting one up. That difference is worth signalling in
        // shape and not only in colour: one is a reversible highlight, the
        // other rebuilds the workspace, and a reader shouldn't discover which
        // by clicking.
        const paper = index && paperRefs ? paperRefs[index] : undefined
        if (!paper) return <>{children}</>
        if (onPaperSeed) {
          // A citation minted by the other backend still maps — it just takes
          // the workspace with it, since its id resolves nowhere else. Say so
          // in the tooltip rather than letting the dropdown change under them.
          const elsewhere =
            paper.provider && provider && paper.provider !== provider ? paper.provider : null
          return (
            <button
              type="button"
              className="cite-ref cite-ref-seed"
              title={
                elsewhere
                  ? `Map this paper's citations, switching to ${PROVIDER_LABEL[elsewhere]} — ${paper.title}`
                  : `Map this paper's citations — ${paper.title}`
              }
              onClick={(event) => {
                event.stopPropagation() // don't also trigger the whole-answer re-light
                onPaperSeed(paper.node_id, paper.provider)
              }}
            >
              {children}
              <GraphGlyph />
            </button>
          )
        }
        // Nowhere to seed (an old save re-read outside a live workspace):
        // degrade to the link-out this used to be. The title carries here
        // because a bare `[n]` with nothing behind it really would be dead.
        if (!paper.url) return <span className="source-ref">({paper.title})</span>
        return (
          <a
            className="cite-ref"
            href={paper.url}
            target="_blank"
            rel="noreferrer"
            title={paper.title}
            onClick={(event) => event.stopPropagation()}
          >
            ({paper.title})
          </a>
        )
      },
      // A library citation from remarkCite. The model wrote `[S2, p.460]`; the
      // reader gets the source's real title and page. Unresolved (a
      // hallucinated index, or an old save with no map) degrades to the raw
      // marker, same as an unresolved `[n]`.
      sourceref: ({
        index,
        page,
        children,
      }: {
        index?: string
        page?: string
        children?: ReactNode
      }) => {
        const source = index && sourceRefs ? sourceRefs[index] : undefined
        if (!source) return <>{children}</>
        return (
          <span className="source-ref" title={source.title}>
            ({source.title}
            {page ? `, p.${page}` : ''})
          </span>
        )
      },
    }),
    [graphRefs, sourceRefs, paperRefs, onRefClick, onGraphIds, onPaperSeed, provider],
  )

  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
