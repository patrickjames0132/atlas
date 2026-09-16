/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * `resolveScope` — the priority list (message, else selection, else visible)
 * applied to a graph: what "the references", "the seed", named papers and a
 * period mean, that an explicit request matching nothing is the empty-scope
 * signal and never falls through, and that the selection outranks the
 * filters. Plus `routePapers`, the thin list the name resolver is shown, and
 * the transcript's scope phrasing.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { GraphNode, GraphResponse } from '../../src/api'
import {
  ANY_TIME,
  describeScope,
  emptyScopeMessage,
  filtersForTurn,
  resolveScope,
  routePapers,
} from '../../src/scope/resolve'
import type { ScopeRequest } from '../../src/scope/resolve'

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
const ref2 = makeNode('r2', { year: 2016 })
const citer = makeNode('c1', { rels: ['citation'] })
const both = makeNode('b1', { rels: ['reference', 'citation'] })
const undated = makeNode('u1', { year: null })
const graph: GraphResponse = {
  seed: { id: 'seed', arxiv_id: null, title: 'Paper seed' },
  nodes: [seed, ref1, ref2, citer, both, undated],
  edges: [],
  counts: { references: 3, citations: 2, nodes: 6 },
}
const discovered = [makeNode('d1', { rels: ['citation'], year: 2016 })]
// r2, b1 and d1 are filtered out of the view.
const visible = ['seed', 'r1', 'c1', 'u1']

const ask = (kind: ScopeRequest['kind'], ids: string[] = [], years = ANY_TIME): ScopeRequest => ({
  kind,
  ids,
  years,
})
const resolve = (request: ScopeRequest | null, selected: string[] = []) =>
  resolveScope(request, graph, discovered, visible, selected)
const ids = (request: ScopeRequest | null, selected: string[] = []) =>
  resolve(request, selected).nodes.map((node) => node.id)

describe('the default rungs', () => {
  it('is what passes the filters when nothing is picked and the message says nothing', () => {
    for (const request of [null, ask('screen')]) {
      const scope = resolve(request)
      expect(scope.source).toBe('visible')
      expect(scope.nodes.map((node) => node.id)).toEqual(['seed', 'r1', 'c1', 'u1'])
      expect(scope.request).toBeNull()
    }
  })

  it('is the selection when there is one, whatever the filters show', () => {
    const scope = resolve(null, ['r2', 'r1', 'r2', 'gone'])
    expect(scope.source).toBe('selection')
    // r2 is hidden by the filters and stays; an id the graph lacks is dropped.
    expect(scope.nodes.map((node) => node.id)).toEqual(['r2', 'r1'])
  })

  it('has nothing to scope without a graph', () => {
    const scope = resolveScope(ask('references'), null, discovered, visible, [])
    expect(scope.nodes).toEqual([])
  })
})

describe('a message scope', () => {
  it('reads the references off the nodes’ own tags, discoveries included, past the filters', () => {
    const scope = resolve(ask('references'))
    expect(scope.source).toBe('message')
    expect(scope.nodes.map((node) => node.id)).toEqual(['r1', 'r2', 'b1', 'u1'])
    expect(scope.request).toEqual(ask('references'))
  })

  it('reads the citations the same way, never the seed', () => {
    expect(ids(ask('citations'))).toEqual(['c1', 'b1', 'd1'])
  })

  it('makes "the seed" the solo lecture', () => {
    expect(ids(ask('seed'))).toEqual(['seed'])
  })

  it('makes "the whole graph" everything the workspace holds, past every filter', () => {
    // The explicit widening that lets "visible" stay the default: a reader
    // who wants the lot says so rather than clearing every filter.
    expect(ids(ask('graph'), ['r1'])).toEqual(['seed', 'r1', 'r2', 'c1', 'b1', 'u1', 'd1'])
    expect(ids(ask('graph', [], { from: 2016, to: 2016 }))).toEqual(['r2', 'd1'])
  })

  it('keeps named papers in the order they were named, dropping what the graph lacks', () => {
    expect(ids(ask('named', ['d1', 'nope', 'r1', 'd1']))).toEqual(['d1', 'r1'])
  })

  it('outranks a selection', () => {
    expect(ids(ask('citations'), ['r1'])).toEqual(['c1', 'b1', 'd1'])
  })

  it('comes back empty with source "message" when it matches nothing — never falling through', () => {
    // The empty-scope signal: an explicit ask that matches nothing must not
    // quietly become the selection or the visible papers.
    const scope = resolve(ask('named', ['nope']), ['r1'])
    expect(scope.source).toBe('message')
    expect(scope.nodes).toEqual([])
    const bare: GraphResponse = { ...graph, nodes: [seed] }
    expect(resolveScope(ask('citations'), bare, [], visible, []).nodes).toEqual([])
  })
})

describe('a year window', () => {
  it('filters whichever set the message named', () => {
    expect(ids(ask('references', [], { from: 2016, to: 2016 }))).toEqual(['r2'])
    expect(ids(ask('citations', [], { from: 2016, to: 2016 }))).toEqual(['d1'])
  })

  it('alone, narrows the existing context rather than reaching past the filters', () => {
    // "the papers between 2016 and 2017" says nothing about WHICH set, so an
    // ambiguous ask preserves the context the reader established: the
    // selection if there is one, else what passes the filters.
    const window = { from: 2016, to: 2017 }
    expect(ids(ask('screen', [], window))).toEqual([])
    expect(ids(ask('screen', [], window), ['r2', 'r1'])).toEqual(['r2'])
    expect(ids(ask('screen', [], { from: 2020, to: 2020 }))).toEqual(['seed', 'r1', 'c1'])
    expect(resolve(ask('screen', [], window)).source).toBe('message')
  })

  it('is open-ended on either side, and never admits an undated paper', () => {
    expect(ids(ask('references', [], { from: 2017, to: null }))).toEqual(['r1', 'b1'])
    expect(ids(ask('references', [], { from: null, to: 2019 }))).toEqual(['r2'])
  })
})

describe('emptyScopeMessage', () => {
  it('names what was asked for', () => {
    expect(emptyScopeMessage(ask('references'))).toMatch(/no references/)
    expect(emptyScopeMessage(ask('named', ['x']))).toMatch(/None of the papers you named/)
    expect(emptyScopeMessage(ask('references', [], { from: 1990, to: 1999 }))).toBe(
      'This graph has no references from 1990–1999.',
    )
    expect(emptyScopeMessage(ask('screen', [], { from: 2005, to: 2005 }))).toBe(
      'This graph has no papers in your current scope from 2005 — widen the year filter, or say which papers.',
    )
  })
})

describe('filtersForTurn', () => {
  const bar = { yearFrom: 2010, yearTo: 2025, fields: ['cs'] }

  it('leaves the bar\u2019s filters alone when the turn has no period', () => {
    expect(filtersForTurn(bar, ANY_TIME)).toBe(bar)
    expect(filtersForTurn(undefined, ANY_TIME)).toBeUndefined()
  })

  it('tightens each side to the stricter of the bar and the period', () => {
    expect(filtersForTurn(bar, { from: 2016, to: 2030 })).toEqual({
      yearFrom: 2016,
      yearTo: 2025,
      fields: ['cs'],
    })
    expect(filtersForTurn(bar, { from: 2000, to: 2017 })).toEqual({
      yearFrom: 2010,
      yearTo: 2017,
      fields: ['cs'],
    })
  })

  it('stands in for absent bar filters', () => {
    expect(filtersForTurn(undefined, { from: 2016, to: null })).toEqual({
      yearFrom: 2016,
      yearTo: null,
      fields: [],
    })
  })
})

describe('describeScope', () => {
  it('says nothing for the visible default, and what was chosen otherwise', () => {
    expect(describeScope({ source: 'visible', nodes: 12 })).toBeNull()
    expect(describeScope({ source: 'selection', nodes: 1 })).toBe('your 1 selected paper')
    expect(describeScope({ source: 'selection', nodes: 5 })).toBe('your 5 selected papers')
    expect(
      describeScope({
        source: 'message',
        kind: 'references',
        years: { from: 2010, to: 2019 },
        nodes: 12,
      }),
    ).toBe('the references, 2010–2019 · 12 papers')
    expect(describeScope({ source: 'message', kind: 'named', years: ANY_TIME, nodes: 1 })).toBe(
      'the paper you named · 1 paper',
    )
    expect(
      describeScope({
        source: 'message',
        kind: 'screen',
        years: { from: 2020, to: null },
        nodes: 3,
      }),
    ).toBe('2020 on · 3 papers')
    expect(describeScope({ source: 'message', kind: 'graph', years: ANY_TIME, nodes: 40 })).toBe(
      'the whole graph · 40 papers',
    )
  })
})

describe('routePapers', () => {
  it('lists every paper once, by what a reader names it by, and nothing more', () => {
    const papers = routePapers(graph, [...discovered, ref1])
    expect(papers.map((paper) => paper.id)).toEqual(['seed', 'r1', 'r2', 'c1', 'b1', 'u1', 'd1'])
    expect(papers[1]).toEqual({ id: 'r1', title: 'Paper r1', year: 2020, authors: 'A. r1, B. r1' })
    expect(Object.keys(papers[0])).toEqual(['id', 'title', 'year', 'authors'])
  })

  it('is empty without a graph', () => {
    expect(routePapers(null, [])).toEqual([])
  })
})
