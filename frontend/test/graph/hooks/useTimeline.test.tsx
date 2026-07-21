// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Timeline x-placement: a paper sits at its year plus a month fraction, so it
 * lands *between* the yearly gridlines rather than on them.
 *
 * The undated case is the interesting one. Papers with no year used to be parked
 * on the seed's own exact column, which stacked every one of them on a single x
 * and drew them as a vertical bar skewered through the seed. They're filtered out
 * of the Timeline view now (GraphExplorer's `nodeOk`), so nothing should place
 * them there any more.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useTimeline } from '../../../src/graph/hooks/useTimeline'
import { YEAR_SPACING } from '../../../src/graph/theme'
import type { Base, VNode } from '../../../src/graph/model'

/** A node carrying only what the timeline reads off it. */
function node(id: string, year: number | null, month: number | null, isSeed = false): VNode {
  return {
    id,
    arxiv_id: null,
    title: id,
    year,
    month,
    citation_count: 1,
    url: null,
    rels: [isSeed ? 'seed' : 'citation'],
    is_seed: isSeed,
  } as unknown as VNode
}

/** A Base spanning 2018–2026 with a March-2020 seed. */
function base(nodes: VNode[]): Base {
  return {
    nodes,
    links: [],
    minYear: 2018,
    maxYear: 2026,
    counts: {},
    minCitations: 0,
    maxCitations: 10,
  }
}

function timelineX(nodes: VNode[]) {
  const { result } = renderHook(() =>
    useTimeline({
      base: base(nodes),
      layout: 'timeline',
      fgRef: { current: null },
      size: { w: 800, h: 600 },
      fitDone: { current: false },
      yearLo: 2018,
      yearHi: 2026,
    }),
  )
  return result.current.nodeTimelineX
}

describe('nodeTimelineX', () => {
  it('places a paper at its year offset from the graph’s earliest year', () => {
    const place = timelineX([node('seed', 2020, 3, true)])
    expect(place({ year: 2018, month: 1 })).toBe(0)
    expect(place({ year: 2021, month: 1 })).toBe(3 * YEAR_SPACING)
  })

  it('offsets by month so papers sit between the gridlines', () => {
    const place = timelineX([node('seed', 2020, 3, true)])
    // July is the 7th month → six twelfths into the year.
    expect(place({ year: 2020, month: 7 })).toBeCloseTo((2 + 6 / 12) * YEAR_SPACING)
  })

  it('puts a paper with a year but no month on its year’s gridline', () => {
    const place = timelineX([node('seed', 2020, 3, true)])
    expect(place({ year: 2022, month: null })).toBe(4 * YEAR_SPACING)
  })

  it('does not park an undated paper on the seed’s column', () => {
    // The regression: the seed sits at 2020+2/12, and an undated paper landing
    // there is what drew the vertical bar. Timeline filters undated papers out,
    // so this only guards an undated *seed*, which anchors at the earliest year.
    const place = timelineX([node('seed', 2020, 3, true)])
    const seedX = place({ year: 2020, month: 3 })
    expect(seedX).toBeCloseTo((2 + 2 / 12) * YEAR_SPACING)
    expect(place({ year: null, month: null })).not.toBeCloseTo(seedX)
    expect(place({ year: null, month: null })).toBe(0)
  })
})
