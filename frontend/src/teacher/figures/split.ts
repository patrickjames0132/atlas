/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The figure interleaver: pairing `<<FIG n>>` markers in streamed prose with
 * the figures the researcher attached, so images render inline exactly where the
 * model placed them.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { AnswerFigure } from '../../api'

/** A complete inline-figure marker the agent placed in its prose ("<<FIG 2>>"). */
const FIG_MARKER = /<<FIG (\d+)>>/g
/** A partial marker at the very end of streaming prose — held out of the render
 * so a marker split across token chunks never flashes raw before completing. */
const FIG_TAIL = /<<(?:F(?:I(?:G(?: ?(?:\d+>?)?)?)?)?)?$/

/**
 * Split answer prose on `<<FIG n>>` markers, pairing each marker with the
 * attached figure whose `slot` is n. Returns the interleaved text/figure
 * parts, plus the figures whose marker never appeared in the prose — those
 * render at the end of the bubble (the pre-inline fallback, which also covers
 * old saved sessions whose figures carry no slot).
 *
 * @param text    The (possibly still-streaming) answer prose.
 * @param figures The figures the agent attached, slot-tagged.
 * @returns The interleaved `parts` plus the unreferenced `leftover` figures.
 */
export function splitAnswer(
  text: string,
  figures?: AnswerFigure[],
): { parts: (string | AnswerFigure)[]; leftover: AnswerFigure[] } {
  const figs = figures ?? []
  const clean = text.replace(FIG_TAIL, '')
  const used = new Set<number>()
  const parts: (string | AnswerFigure)[] = []
  // Text accumulates in a buffer so a marker with no matching figure (e.g. a
  // slot the agent invented) just disappears — its surrounding paragraphs stay
  // joined by their own newlines instead of gluing together.
  let buf = ''
  const flush = () => {
    const trimmed = buf.replace(/^\n+|\n+$/g, '') // outer blank lines only; keep internal breaks
    if (trimmed) parts.push(trimmed)
    buf = ''
  }
  let last = 0
  for (const match of clean.matchAll(FIG_MARKER)) {
    buf += clean.slice(last, match.index)
    last = (match.index ?? 0) + match[0].length
    const slot = Number(match[1])
    const fig = figs.find((figure) => figure.slot === slot)
    if (fig && !used.has(slot)) {
      used.add(slot)
      flush()
      parts.push(fig)
    }
  }
  buf += clean.slice(last)
  flush()
  if (parts.length === 0) parts.push('')
  return { parts, leftover: figs.filter((figure) => figure.slot == null || !used.has(figure.slot)) }
}
