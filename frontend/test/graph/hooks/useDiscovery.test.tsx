// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The discovery merge's origin tracking (the expansion-satellite half of the
 * v5.24.0 layout work): a discovery whose anchor edge lands on a NON-seed
 * node records that node as its `_origin` (the cluster force gathers it
 * there), a seed-anchored or ungrounded discovery records none — and in
 * Timeline, satellites band outward in y past their origin instead of
 * landing inside the settled columns.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useDiscovery } from '../../../src/graph/hooks/useDiscovery'
import type { GraphEdge, GraphNode } from '../../../src/api'
import type { Base, VNode } from '../../../src/graph/model'

function makeNode(id: string, overrides: Partial<VNode> = {}): VNode {
  return {
    id,
    arxiv_id: null,
    title: id,
    year: 2020,
    month: null,
    pub_date: null,
    citation_count: 1,
    authors: null,
    url: null,
    rels: ['citation'],
    is_seed: false,
    abstract: null,
    tldr: null,
    x: 100,
    y: 50,
    ...overrides,
  } as VNode
}

function makeBase(nodes: VNode[]): Base {
  return {
    nodes,
    links: [],
    minYear: 2015,
    maxYear: 2026,
    counts: { reference: 0, citation: 0, latest: 0, similar: 0 },
    minCitations: 0,
    maxCitations: 10,
  }
}

const discovery = (id: string): GraphNode =>
  ({ ...makeNode(id), discovered: true, x: undefined, y: undefined }) as GraphNode

function runDiscover(
  base: Base,
  layout: 'force' | 'timeline',
  nodes: GraphNode[],
  edges: GraphEdge[],
) {
  const { result } = renderHook(() =>
    useDiscovery({
      base,
      layout,
      nodeTimelineX: (node) => (typeof node.year === 'number' ? node.year * 10 : 0),
      fgRef: { current: null },
      onYearLo: () => {},
      onYearHi: () => {},
    }),
  )
  result.current.onDiscover(nodes, edges)
}

describe('useDiscovery origin tracking', () => {
  it('records the anchor as _origin when the anchor edge lands on a non-seed node', () => {
    const base = makeBase([makeNode('seed', { is_seed: true }), makeNode('expanded')])
    runDiscover(
      base,
      'force',
      [discovery('found')],
      [{ source: 'expanded', target: 'found', type: 'reference' } as GraphEdge],
    )
    const merged = base.nodes.find((node) => node.id === 'found')!
    expect(merged._origin).toBe('expanded')
  })

  it('records no origin for seed-anchored or ungrounded discoveries', () => {
    const base = makeBase([makeNode('seed', { is_seed: true }), makeNode('other')])
    runDiscover(
      base,
      'force',
      [discovery('fromSeed'), discovery('searchHit')],
      [{ source: 'seed', target: 'fromSeed', type: 'reference' } as GraphEdge],
    )
    expect(base.nodes.find((node) => node.id === 'fromSeed')!._origin).toBeUndefined()
    expect(base.nodes.find((node) => node.id === 'searchHit')!._origin).toBeUndefined()
  })

  it('bands a Timeline satellite outward in y, past its origin', () => {
    const base = makeBase([
      makeNode('seed', { is_seed: true, y: 0 }),
      makeNode('expanded', { y: 80 }),
    ])
    runDiscover(
      base,
      'timeline',
      [discovery('found')],
      [{ source: 'expanded', target: 'found', type: 'reference' } as GraphEdge],
    )
    const merged = base.nodes.find((node) => node.id === 'found')!
    // Positive-y origin pushes its satellites further positive (outward),
    // and the date column still pins x.
    expect(merged.y!).toBeGreaterThan(80 + 100)
    expect(merged.fx).toBe(2020 * 10)
  })
})
