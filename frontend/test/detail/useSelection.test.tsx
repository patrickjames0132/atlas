// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * What a freshly built graph leaves open: nothing. Selection starts (and, on
 * every new graph, returns to) null — v7.9.0's "a graph opens onto the graph,
 * not onto its panels" — so the detail panel only appears once a paper is
 * clicked. The seed is no longer auto-selected; the chat-citation path and the
 * guided tour open it explicitly, from GraphExplorer.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useSelection } from '../../src/detail/useSelection'
import type { GraphResponse } from '../../src/api'
import type { Base, VNode } from '../../src/graph/model'

// The panel's lazy fetches fire the moment something IS selected; none of
// them is under test here, and the suite never touches the network.
vi.mock('../../src/api', () => ({
  fetchPaperDetail: vi.fn(() => Promise.resolve({})),
  fetchFigures: vi.fn(() => Promise.resolve({ available: false, figures: [] })),
  fetchCodeLinks: vi.fn(() => Promise.resolve({ available: false })),
  fetchCategories: vi.fn(() => Promise.resolve({ available: false })),
}))

/** A graph node carrying enough detail that selecting it hydrates nothing. */
function makeNode(id: string, isSeed = false): VNode {
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
    rels: isSeed ? [] : ['citation'],
    is_seed: isSeed,
    abstract: `${id} abstract`,
    tldr: null,
  } as unknown as VNode
}

/** A graph and the matching per-graph dataset, seeded on `seedId`. */
function makeWorld(seedId: string) {
  const seed = makeNode(seedId, true)
  const neighbor = makeNode(`${seedId}-neighbor`)
  const graph: GraphResponse = {
    seed: { id: seedId, arxiv_id: null, title: seedId },
    nodes: [seed, neighbor],
    edges: [],
    counts: { reference: 0, citation: 1, latest: 0 },
  } as unknown as GraphResponse
  const base: Base = {
    nodes: [seed, neighbor],
    links: [],
    minYear: 2019,
    maxYear: 2021,
    counts: { reference: 0, citation: 1, latest: 0 },
    minCitations: 0,
    maxCitations: 10,
  }
  return { graph, base, seed, neighbor }
}

/** Mount the hook over one world, with an inert re-seed callback. */
function mount(world: ReturnType<typeof makeWorld>) {
  return renderHook(
    ({ graph, base }: Pick<ReturnType<typeof makeWorld>, 'graph' | 'base'>) =>
      useSelection({ base, graph, provider: 's2', loadGraph: () => {} }),
    { initialProps: { graph: world.graph, base: world.base } },
  )
}

describe('useSelection on a new graph', () => {
  it('opens nothing — the seed is not auto-selected', () => {
    const world = makeWorld('seed-1')
    const { result } = mount(world)
    expect(result.current.selectedId).toBeNull()
    expect(result.current.selected).toBeNull()
  })

  it('clears an open paper when the next graph lands', () => {
    const world = makeWorld('seed-1')
    const { result, rerender } = mount(world)

    act(() => result.current.onNodeClick(world.neighbor))
    expect(result.current.selectedId).toBe('seed-1-neighbor')

    const next = makeWorld('seed-2')
    rerender({ graph: next.graph, base: next.base })
    expect(result.current.selectedId).toBeNull()
    expect(result.current.selected).toBeNull()
  })

  it('still opens the paper a click asks for', () => {
    const world = makeWorld('seed-1')
    const { result } = mount(world)

    act(() => result.current.onNodeClick(world.seed))
    expect(result.current.selectedId).toBe('seed-1')
    expect(result.current.selected?.title).toBe('seed-1')

    // And the tour / chat-citation path sets it directly, the same way.
    act(() => result.current.setSelectedId(world.neighbor.id))
    expect(result.current.selected?.id).toBe('seed-1-neighbor')
  })
})
