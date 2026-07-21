/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The graph view-model's pure helpers: date formatting, relation priority,
 * radius scaling, node persistence stripping, count rebuilding, and the
 * pasted-arXiv-id fast path.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { GraphNode } from '../../src/api'
import {
  CITE_SLIDER_STEPS,
  ID_RE,
  citationThreshold,
  cleanNode,
  countRels,
  findMatches,
  formatPubDate,
  nodeRadius,
  primaryRel,
} from '../../src/graph/model'
import type { VNode } from '../../src/graph/model'

/** A minimal valid GraphNode; override per test. */
function makeNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 'node01',
    arxiv_id: null,
    title: 'A Paper',
    year: 2017,
    citation_count: 0,
    url: null,
    rels: [],
    is_seed: false,
    ...overrides,
  }
}

describe('findMatches', () => {
  const NODES = [
    makeNode({ id: 'attn', title: 'Attention Is All You Need', authors: 'Vaswani, Shazeer' }),
    makeNode({ id: 'bert', title: 'BERT: Pre-training of Deep Bidirectional Transformers' }),
    makeNode({ id: 'gpt', title: 'Language Models are Few-Shot Learners', authors: 'Brown' }),
  ]

  it('matches case-insensitively on title and author substrings', () => {
    expect(findMatches(NODES, 'attention')).toEqual(new Set(['attn']))
    expect(findMatches(NODES, 'VASWANI')).toEqual(new Set(['attn']))
    expect(findMatches(NODES, 'transformers')).toEqual(new Set(['bert']))
  })

  it('an empty or whitespace query means no find at all (null, not empty)', () => {
    expect(findMatches(NODES, '')).toBeNull()
    expect(findMatches(NODES, '   ')).toBeNull()
  })

  it('a query with no hits returns an EMPTY set — dim everything, honestly', () => {
    expect(findMatches(NODES, 'quantum gravity')).toEqual(new Set())
  })

  it('a node without authors still matches by title', () => {
    expect(findMatches(NODES, 'few-shot')).toEqual(new Set(['gpt']))
  })
})

describe('formatPubDate', () => {
  it('renders a full date, parsed by hand (no timezone off-by-one)', () => {
    expect(formatPubDate('2017-06-12', 2017)).toBe('Jun 12, 2017')
  })

  it('degrades gracefully as data thins out', () => {
    expect(formatPubDate('2017-06', 2017)).toBe('Jun 2017')
    expect(formatPubDate(null, 2017)).toBe('2017')
    expect(formatPubDate(undefined, null)).toBe('—')
  })

  it('falls back to the year on a malformed date string', () => {
    expect(formatPubDate('June 2017', 2017)).toBe('2017')
  })

  it('returns the bare year for an out-of-range month', () => {
    expect(formatPubDate('2017-13-01', null)).toBe('2017')
  })
})

describe('primaryRel', () => {
  it('lets the seed flag win over everything', () => {
    expect(primaryRel(makeNode({ is_seed: true, rels: ['reference'] }))).toBe('seed')
  })

  it('picks the first graph relation in priority order', () => {
    expect(primaryRel(makeNode({ rels: ['similar', 'reference'] }))).toBe('reference')
  })

  it('gives ungrounded topic-search hits their own color', () => {
    expect(primaryRel(makeNode({ rels: ['search'] }))).toBe('search')
  })

  it('falls back to similar when a node has no relation at all', () => {
    expect(primaryRel(makeNode({ rels: [] }))).toBe('similar')
  })
})

describe('nodeRadius', () => {
  it('draws the seed fixed-large regardless of citations', () => {
    expect(nodeRadius(makeNode({ is_seed: true, citation_count: 0 }))).toBe(10)
  })

  it('scales with the square root of citations', () => {
    expect(nodeRadius(makeNode({ citation_count: 0 }))).toBe(3)
    expect(nodeRadius(makeNode({ citation_count: 36 }))).toBe(4)
  })

  it('caps megahit papers so they cannot swallow the canvas', () => {
    expect(nodeRadius(makeNode({ citation_count: 1_000_000 }))).toBe(18)
  })
})

describe('citationThreshold', () => {
  it('anchors position 0 to the graph floor (not a hardcoded 0)', () => {
    expect(citationThreshold(0, 8, 5000)).toBe(8)
  })

  it('reaches exactly the ceiling at the top position', () => {
    expect(citationThreshold(CITE_SLIDER_STEPS, 8, 5000)).toBe(5000)
  })

  it('rises on a log scale — the midpoint sits far below the linear midpoint', () => {
    // expm1(mid of log1p(0)…log1p(5000)) ≈ 70, not 2500: most travel is low.
    expect(citationThreshold(CITE_SLIDER_STEPS / 2, 0, 5000)).toBe(70)
  })

  it('is monotonic across the slider', () => {
    let previous = -1
    for (let position = 0; position <= CITE_SLIDER_STEPS; position += 10) {
      const threshold = citationThreshold(position, 8, 5000)
      expect(threshold).toBeGreaterThanOrEqual(previous)
      previous = threshold
    }
  })

  it('collapses to the ceiling when the range is flat (nothing to filter)', () => {
    expect(citationThreshold(0, 42, 42)).toBe(42)
    expect(citationThreshold(CITE_SLIDER_STEPS, 42, 42)).toBe(42)
  })
})

describe('cleanNode', () => {
  it('strips sim positions and pins, keeping the persistable fields', () => {
    const live: VNode = { ...makeNode(), x: 12, y: 34, fx: 12, fy: 34 }
    const cleaned = cleanNode(live)
    expect(cleaned).not.toHaveProperty('x')
    expect(cleaned).not.toHaveProperty('fx')
    expect(cleaned.id).toBe('node01')
    expect(cleaned.title).toBe('A Paper')
  })
})

describe('countRels', () => {
  it('rebuilds per-relation counts from restored nodes', () => {
    const nodes = [
      makeNode({ rels: ['reference'] }),
      makeNode({ rels: ['citation', 'similar'] }),
      makeNode({ rels: ['latest'] }),
      makeNode({ is_seed: true, rels: [] }),
    ]
    expect(countRels(nodes)).toEqual({
      references: 1,
      citations: 1,
      similar: 1,
      latest: 1,
      nodes: 4,
    })
  })
})

describe('ID_RE — the pasted-id fast path', () => {
  it.each([
    ['1706.03762', '1706.03762'],
    ['1706.03762v5', '1706.03762v5'],
    ['https://arxiv.org/abs/1706.03762', '1706.03762'],
    ['https://arxiv.org/pdf/2304.01234v2', '2304.01234v2'],
    ['hep-th/9901001', 'hep-th/9901001'],
  ])('accepts %s', (input, id) => {
    const match = ID_RE.exec(input)
    expect(match?.[1]).toBe(id)
  })

  it.each(['attention is all you need', '1706', 'https://example.org/abs/1706.03762'])(
    'rejects %s (keyword search takes over)',
    (input) => {
      expect(ID_RE.test(input)).toBe(false)
    },
  )
})
