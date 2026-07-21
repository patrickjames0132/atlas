/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Render a string with its LaTeX math ($…$, $$…$$, \(…\), \[…\]) typeset by
 * KaTeX and everything else as plain text. Use this anywhere paper text reaches
 * an HTML surface — detail panel, lecture beats, chat answers, search hits — so
 * `$\beta_2$` shows as β₂ instead of raw source.
 *
 * KaTeX renders to HTML, so this only works in the DOM. Graph node labels are
 * painted on a canvas; they use {@link latexToUnicode} instead.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

import { splitMath } from './splitMath'

/**
 * One math run, typeset by KaTeX into trusted (self-sanitised) markup.
 *
 * @returns The rendered KaTeX span.
 */
function MathSpan({ value, display }: { value: string; display: boolean }) {
  // `throwOnError: false` degrades invalid LaTeX to a red-rendered source string
  // rather than throwing — a malformed formula never takes down the surface.
  const html = useMemo(
    () => katex.renderToString(value, { throwOnError: false, displayMode: display }),
    [value, display],
  )
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}

/**
 * Typeset the LaTeX math in `children`. Falls back to rendering the raw string
 * (or nothing, for null/empty) when there's no math, so it's safe to wrap every
 * text surface unconditionally.
 *
 * @returns The interleaved plain/typeset spans, or null for empty input.
 */
export default function MathText({ children }: { children: string | null | undefined }) {
  const segments = useMemo(() => (children ? splitMath(children) : []), [children])
  if (!children) return null
  return (
    <>
      {segments.map((segment, index) =>
        segment.kind === 'text' ? (
          <span key={index}>{segment.value}</span>
        ) : (
          <MathSpan key={index} value={segment.value} display={segment.display} />
        ),
      )}
    </>
  )
}
