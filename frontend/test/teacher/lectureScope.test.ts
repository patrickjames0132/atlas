/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * `scopeLecture` — what "the references", "the seed" and a list of named
 * papers mean on a given graph, and which of them the view currently hides —
 * plus `routePapers`, the thin list the name resolver is shown.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { GraphNode, GraphResponse } from '../../src/api'
import { routePapers, scopeLecture } from '../../src/teacher/lectureScope'

function makeNode(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    arxiv_id: null,
    title: `Paper ${id}`,
    abstract: 'a long abstract that must never reach the resolver',
    year: 2020,
    citation_count: 0,
    url: null,
    authors: `A. ${id}, B. ${id}`,
    rels: ['reference'],
    is_seed: false,
    ...overrides,
  }
}

const seed = makeNode('seed', { is_seed: true, rels: [], authors: null })
const ref1 = makeNode('r1')
const ref2 = makeNode('r2')
const citer = makeNode('c1', { rels: ['citation'] })
const both = makeNode('b1', { rels: ['reference', 'citation'] })
const graph: GraphResponse = {
  seed: { id: 'seed', arxiv_id: null, title: 'Paper seed' },
  nodes: [seed, ref1, ref2, citer, both],
  edges: [],
  counts: { references: 3, citations: 2, nodes: 5 },
}
const discovered = [makeNode('d1', { rels: ['citation'], year: 2016 })]
const visible = ['seed', 'r1', 'c1']
const anyTime = { from: null, to: null }
/** No hand-picked selection, the usual case. */
const scoped = (
  scope: Parameters<typeof scopeLecture>[0],
  ids: string[] = [],
  years = anyTime,
  selected: string[] = [],
) => scopeLecture(scope, ids, years, graph, discovered, visible, selected)

describe('scopeLecture', () => {
  it('leaves a message that did not say alone', () => {
    expect(scoped('screen')).toBeNull()
  })

  it('has nothing to scope without a graph', () => {
    expect(scopeLecture('references', [], anyTime, null, discovered, visible, [])).toBeNull()
  })

  it('reads the references off the nodes’ own tags, discoveries included', () => {
    const result = scoped('references')
    expect(result?.nodes.map((node) => node.id)).toEqual(['r1', 'r2', 'b1'])
    // r2 and b1 are filtered out of the view: those are what the message
    // has to force back on screen.
    expect(result?.hidden).toEqual(['r2', 'b1'])
  })

  it('reads the citations the same way, never the seed', () => {
    const result = scoped('citations')
    expect(result?.nodes.map((node) => node.id)).toEqual(['c1', 'b1', 'd1'])
    expect(result?.hidden).toEqual(['b1', 'd1'])
  })

  it('makes "the seed" the solo lecture', () => {
    const result = scoped('seed')
    expect(result?.nodes.map((node) => node.id)).toEqual(['seed'])
    expect(result?.hidden).toEqual([])
  })

  it('keeps named papers in the order they were named, dropping what the graph lacks', () => {
    const result = scoped('named', ['d1', 'nope', 'r1', 'd1'])
    expect(result?.nodes.map((node) => node.id)).toEqual(['d1', 'r1'])
    expect(result?.hidden).toEqual(['d1'])
  })

  it('comes back empty, not null, when the scope matches nothing', () => {
    // Empty is a failed request the caller reports; null would read as
    // "narrate the screen instead", which is the silent fallback it must not be.
    expect(scoped('named', ['nope'])).toEqual({ nodes: [], hidden: [] })
    const bare: GraphResponse = { ...graph, nodes: [seed] }
    expect(scopeLecture('citations', [], anyTime, bare, [], visible, [])?.nodes).toEqual([])
  })

  describe('a year window', () => {
    // seed/r1/r2/c1/b1 are 2020; d1 is 2016; u1 is undated.
    const undated = makeNode('u1', { year: null })
    const dated: GraphResponse = { ...graph, nodes: [...graph.nodes, undated] }
    const between = (from: number | null, to: number | null, selected: string[] = []) =>
      scopeLecture('screen', [], { from, to }, dated, discovered, visible, selected)

    it('makes "the papers between…" a scope of its own, off the whole graph', () => {
      // Not the visible part: a year the sliders exclude is exactly what the
      // message should reach past, like a hidden relation.
      expect(between(2016, 2017)?.nodes.map((node) => node.id)).toEqual(['d1'])
      expect(between(2016, 2017)?.hidden).toEqual(['d1'])
    })

    it('narrows within a hand-picked selection when there is one', () => {
      expect(between(2000, 2030, ['r1', 'd1'])?.nodes.map((node) => node.id)).toEqual(['r1', 'd1'])
      expect(between(2020, 2020, ['r1', 'd1'])?.nodes.map((node) => node.id)).toEqual(['r1'])
    })

    it('is open-ended on either side, and never admits an undated paper', () => {
      expect(between(2017, null)?.nodes.map((node) => node.id)).toEqual([
        'seed',
        'r1',
        'r2',
        'c1',
        'b1',
      ])
      expect(between(null, 2019)?.nodes.map((node) => node.id)).toEqual(['d1'])
    })

    it('combines with a relation', () => {
      const result = scopeLecture(
        'citations',
        [],
        { from: 2016, to: 2016 },
        graph,
        discovered,
        visible,
        [],
      )
      expect(result?.nodes.map((node) => node.id)).toEqual(['d1'])
    })
  })
})

describe('routePapers', () => {
  it('lists every paper once, by what a reader names it by, and nothing more', () => {
    const papers = routePapers(graph, [...discovered, ref1])
    expect(papers).toEqual([
      { id: 'seed', title: 'Paper seed', year: 2020, authors: null },
      { id: 'r1', title: 'Paper r1', year: 2020, authors: 'A. r1, B. r1' },
      { id: 'r2', title: 'Paper r2', year: 2020, authors: 'A. r2, B. r2' },
      { id: 'c1', title: 'Paper c1', year: 2020, authors: 'A. c1, B. c1' },
      { id: 'b1', title: 'Paper b1', year: 2020, authors: 'A. b1, B. b1' },
      { id: 'd1', title: 'Paper d1', year: 2016, authors: 'A. d1, B. d1' },
    ])
  })

  it('is empty without a graph', () => {
    expect(routePapers(null, [])).toEqual([])
  })
})
