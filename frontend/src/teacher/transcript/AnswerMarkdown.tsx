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
 *   • `[n]` markers via `remarkCite`, made clickable when the answer's `refs`
 *     map resolves them to a graph node (glowing that one paper on click),
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
import type { PaperRef, SourceRef } from '../../api'
import { remarkCite } from './remarkCite'

const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkCite]
const REHYPE_PLUGINS = [rehypeKatex]

/**
 * Render an answer's Markdown + math + clickable `[n]` citations.
 *
 * @returns The rendered answer body.
 */
export default function AnswerMarkdown({
  text,
  refs,
  sourceRefs,
  paperRefs,
  onRefClick,
}: {
  text: string
  /** `[n]` → node-id map for this answer (undefined on old saves / no refs). */
  refs?: Record<string, string>
  /** `[n]` → paper (title + URL), the fallback when there's no graph to
   *  resolve a marker against. */
  paperRefs?: Record<string, PaperRef>
  /** `[Sn]` index → library source, for rendering a marker as its real title
   *  (undefined on old saves, or when the turn cited no library passage). */
  sourceRefs?: Record<string, SourceRef>
  /** Spotlight one paper on the graph (undefined = markers render inert). */
  onRefClick?: (nodeId: string) => void
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
        const nodeId = index && refs ? refs[index] : undefined
        if (nodeId && onRefClick) {
          return (
            <button
              type="button"
              className="cite-ref"
              title="Show this paper on the graph"
              onClick={(event) => {
                event.stopPropagation() // don't also trigger the whole-answer re-light
                onRefClick(nodeId)
              }}
            >
              {children}
            </button>
          )
        }
        // No graph to point at: the marker would otherwise be dead text with
        // nothing to say which paper it named. Fall back to the server-resolved
        // title, linking out where the paper actually lives.
        const paper = index && paperRefs ? paperRefs[index] : undefined
        if (!paper) return <>{children}</>
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
    [refs, sourceRefs, paperRefs, onRefClick],
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
