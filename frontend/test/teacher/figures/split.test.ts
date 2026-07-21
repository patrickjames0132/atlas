/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The inline-figure interleaver: `<<FIG n>>` markers pair with attached
 * figures, streaming tails are held back, and invented or missing slots
 * degrade cleanly.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { AnswerFigure } from '../../../src/api'
import { splitAnswer } from '../../../src/teacher/figures/split'

/** A minimal attached figure occupying `slot`. */
function makeFigure(slot: number): AnswerFigure {
  return {
    image: `/api/figure_proxy?src=fig${slot}`,
    caption: `caption ${slot}`,
    title: null,
    slot,
  }
}

describe('splitAnswer', () => {
  it('interleaves a figure exactly where its marker sits', () => {
    const figure = makeFigure(1)
    const { parts, leftover } = splitAnswer('before <<FIG 1>> after', [figure])
    // Only outer NEWLINES are trimmed; spaces stay (harmless in Markdown).
    expect(parts).toEqual(['before ', figure, ' after'])
    expect(leftover).toEqual([])
  })

  it('holds back a partial marker at the end of streaming prose', () => {
    for (const tail of ['<<', '<<F', '<<FI', '<<FIG', '<<FIG ', '<<FIG 1', '<<FIG 1>']) {
      const { parts } = splitAnswer(`text ${tail}`, [])
      expect(parts).toEqual(['text '])
    }
  })

  it("drops an invented slot's marker without gluing its paragraphs", () => {
    const { parts } = splitAnswer('para one\n\n<<FIG 9>>\n\npara two', [])
    expect(parts).toEqual(['para one\n\n\n\npara two'])
  })

  it('renders a figure only once even if its marker repeats', () => {
    const figure = makeFigure(1)
    const { parts } = splitAnswer('a <<FIG 1>> b <<FIG 1>> c', [figure])
    // The second marker vanishes; its surrounding text joins as-is.
    expect(parts).toEqual(['a ', figure, ' b  c'])
  })

  it('returns unreferenced figures as leftovers for the bubble end', () => {
    const inline = makeFigure(1)
    const orphan = makeFigure(2)
    const { parts, leftover } = splitAnswer('only <<FIG 1>> here', [inline, orphan])
    expect(parts).toEqual(['only ', inline, ' here'])
    expect(leftover).toEqual([orphan])
  })

  it('treats slotless figures (old saved sessions) as leftovers', () => {
    const legacy: AnswerFigure = { image: '/api/figure_proxy?src=old', caption: 'old', title: null }
    const { parts, leftover } = splitAnswer('prose without markers', [legacy])
    expect(parts).toEqual(['prose without markers'])
    expect(leftover).toEqual([legacy])
  })

  it('always yields at least one part so the bubble renders', () => {
    expect(splitAnswer('', []).parts).toEqual([''])
  })
})
