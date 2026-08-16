/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The workspace slice's node-selection reducers and grounding scope: setting /
 * adding / toggling / clearing the hand-picked selection (with dedupe), and the
 * `selectGroundingNodes` intersection semantics — a non-empty selection narrows
 * grounding to `selected ∩ visible`, while discoveries are always kept.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it, vi } from 'vitest'
import type { GraphNode, GraphResponse } from '../../src/api'
import reducer, {
  loadGraph,
  nodeSelectionAdded,
  nodeSelectionCleared,
  nodeSelectionSet,
  nodeSelectionToggled,
  providerSet,
  selectGroundingNodes,
  selectSatelliteCount,
  restoreSession,
  visibleNodesSet,
  workspaceCleared,
} from '../../src/store/workspace'
import type { WorkspaceState } from '../../src/store/workspace'
import type { TranscriptState } from '../../src/store/transcript'

/** A minimal valid GraphNode; override per test. */
function makeNode(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    arxiv_id: null,
    title: id,
    year: 2020,
    citation_count: 0,
    url: null,
    rels: ['reference'],
    is_seed: false,
    ...overrides,
  }
}

/** A GraphResponse wrapping the given nodes (edges/counts unused by the tests). */
function makeGraph(nodes: GraphNode[]): GraphResponse {
  return {
    seed: { id: nodes[0]?.id ?? 'seed', arxiv_id: null, title: 'seed' },
    nodes,
    edges: [],
    counts: { references: 0, citations: 0, latest: 0, nodes: nodes.length },
  }
}

/** The initial slice state. */
const initial = (): WorkspaceState => reducer(undefined, { type: '@@init' })

describe('node-selection reducers', () => {
  it('sets the selection, deduping the payload', () => {
    const state = reducer(initial(), nodeSelectionSet(['a', 'b', 'a']))
    expect(state.selectedNodeIds).toEqual(['a', 'b'])
  })

  it('adds ids as a union, deduped against the current set', () => {
    let state = reducer(initial(), nodeSelectionSet(['a', 'b']))
    state = reducer(state, nodeSelectionAdded(['b', 'c']))
    expect(state.selectedNodeIds).toEqual(['a', 'b', 'c'])
  })

  it('toggles a single id in and back out', () => {
    let state = reducer(initial(), nodeSelectionSet(['a']))
    state = reducer(state, nodeSelectionToggled('b'))
    expect(state.selectedNodeIds).toEqual(['a', 'b'])
    state = reducer(state, nodeSelectionToggled('a'))
    expect(state.selectedNodeIds).toEqual(['b'])
  })

  it('clears the whole selection', () => {
    let state = reducer(initial(), nodeSelectionSet(['a', 'b']))
    state = reducer(state, nodeSelectionCleared())
    expect(state.selectedNodeIds).toEqual([])
  })
})

describe('selectGroundingNodes', () => {
  const graph = makeGraph([makeNode('a'), makeNode('b'), makeNode('c')])

  /** Build a root state around a workspace patch, from the slice's initial. */
  function stateWith(patch: Partial<WorkspaceState>) {
    return { workspace: { ...initial(), graph, ...patch } }
  }

  it('grounds in the whole visible set when nothing is picked', () => {
    const grounding = selectGroundingNodes(stateWith({ visibleNodeIds: ['a', 'b', 'c'] }))
    expect(grounding.map((node) => node.id)).toEqual(['a', 'b', 'c'])
  })

  it('narrows to selected ∩ visible when a selection exists', () => {
    // 'c' is picked but hidden by the filter, so it drops; 'a' is picked and
    // visible, so it stays; 'b' is visible but not picked, so it drops.
    const grounding = selectGroundingNodes(
      stateWith({ visibleNodeIds: ['a', 'b'], selectedNodeIds: ['a', 'c'] }),
    )
    expect(grounding.map((node) => node.id)).toEqual(['a'])
  })

  it('always keeps discoveries, even outside the selection', () => {
    const discovered = makeNode('d', { discovered: true })
    const grounding = selectGroundingNodes(
      stateWith({
        visibleNodeIds: ['a', 'b'],
        selectedNodeIds: ['a'],
        discoveredNodes: [discovered],
      }),
    )
    // 'a' (selected ∩ visible) plus the discovery, which the selection can't drop.
    expect(grounding.map((node) => node.id)).toEqual(['a', 'd'])
  })

  it('is empty when the selection intersects nothing visible', () => {
    const grounding = selectGroundingNodes(
      stateWith({ visibleNodeIds: ['a', 'b'], selectedNodeIds: ['c'] }),
    )
    expect(grounding).toEqual([])
  })
})

describe('provider selection', () => {
  it('defaults to Semantic Scholar', () => {
    expect(initial().provider).toBe('s2')
  })

  it('providerSet switches the backend', () => {
    const state = reducer(initial(), providerSet('openalex'))
    expect(state.provider).toBe('openalex')
  })

  it('survives Home (an app-wide setting, not per-graph)', () => {
    // Unlike the graph itself, the provider choice persists across a workspace
    // clear — it reads as a global setting, so Home must not reset it.
    let state = reducer(initial(), providerSet('openalex'))
    state = reducer(state, workspaceCleared())
    expect(state.graph).toBeNull() // the graph is cleared…
    expect(state.provider).toBe('openalex') // …but the provider choice stays
  })

  it('follows a graph built under an overriding backend', () => {
    // Only a chat citation overrides: its node id resolves nowhere but the
    // provider that issued it. Once the graph is up under that backend, the
    // dropdown has to agree — otherwise the header names one provider while
    // every expand off the graph runs on another.
    let state = reducer(initial(), providerSet('openalex'))
    state = reducer(state, {
      type: loadGraph.fulfilled.type,
      payload: makeGraph([makeNode('a')]),
      meta: { arg: { seed: 'a', provider: 's2' } },
    })
    expect(state.provider).toBe('s2')
  })

  it('leaves the backend alone on an ordinary load', () => {
    let state = reducer(initial(), providerSet('openalex'))
    state = reducer(state, {
      type: loadGraph.fulfilled.type,
      payload: makeGraph([makeNode('a')]),
      meta: { arg: { seed: 'a' } },
    })
    expect(state.provider).toBe('openalex')
  })
})

describe('selection lifecycle', () => {
  it('a fresh visible-set publish leaves an existing pick in place', () => {
    // Publishing the visible ids (GraphExplorer's per-filter effect) must not
    // disturb the hand-picked selection — they're independent scopes.
    let state = reducer(initial(), nodeSelectionSet(['a']))
    state = reducer(state, visibleNodesSet(['a', 'b', 'c']))
    expect(state.selectedNodeIds).toEqual(['a'])
  })
})

describe('restoring a save from before the graphRefs rename', () => {
  /** A legacy save: `[n]` maps under the old bare `refs` key, on both a chat
   *  turn and a cached lecture beat. */
  const LEGACY_SAVE = {
    data: {
      seed: { id: 'seed', arxiv_id: null, title: 'Seed' },
      nodes: [],
      edges: [],
      chat: [
        { role: 'user', text: 'Why attention?' },
        { role: 'assistant', text: 'Because [1].', refs: { '1': 'node-attention' } },
      ],
      lectures: {
        history: [
          { heading: 'One', text: 'As [2] showed.', node_ids: [], refs: { '2': 'node-rnn' } },
        ],
      },
    },
  }

  it('carries the old `refs` maps onto the current field names', async () => {
    // A dropped map is the worst outcome here: the turn restores looking
    // perfectly fine, with every citation quietly reduced to inert text.
    const api = await import('../../src/api')
    const getSession = vi.spyOn(api, 'getSession').mockResolvedValue(LEGACY_SAVE as never)

    const action = await restoreSession('saved-1')(vi.fn(), vi.fn(), undefined)
    const { transcript } = action.payload as { transcript: TranscriptState }

    expect(transcript.chat[1].graphRefs).toEqual({ '1': 'node-attention' })
    expect(transcript.lectures.history?.[0].graph_refs).toEqual({ '2': 'node-rnn' })
    getSession.mockRestore()
  })

  it('leaves a current save untouched', async () => {
    const api = await import('../../src/api')
    const getSession = vi.spyOn(api, 'getSession').mockResolvedValue({
      data: {
        ...LEGACY_SAVE.data,
        chat: [{ role: 'assistant', text: 'Because [1].', graphRefs: { '1': 'node-new' } }],
        lectures: {},
      },
    } as never)

    const action = await restoreSession('saved-2')(vi.fn(), vi.fn(), undefined)
    const { transcript } = action.payload as { transcript: TranscriptState }

    expect(transcript.chat[0].graphRefs).toEqual({ '1': 'node-new' })
    getSession.mockRestore()
  })
})

describe('selectSatelliteCount', () => {
  const seed = { id: 'seed01', title: 'Seed', is_seed: true }
  const edge = (source: string, target: string) => ({ source, target, type: 'reference' as const })

  /** A workspace state with a graph, its edges, and everything visible. */
  const stateWith = (
    nodes: { id: string; is_seed?: boolean }[],
    edges: ReturnType<typeof edge>[],
  ) =>
    ({
      workspace: {
        ...reducer(undefined, { type: '@@init' }),
        graph: { seed, nodes, edges, counts: {} },
        visibleNodeIds: nodes.map((node) => node.id),
      },
    }) as never

  it('counts papers joined to no edge of the seed — the ones no lecture narrates', () => {
    // ref01 is the seed's reference; ref01-ref hangs off ref01, so it is on the
    // graph but outside the seed's own neighbourhood.
    const state = stateWith(
      [seed, { id: 'ref01' }, { id: 'ref01-ref' }],
      [edge('seed01', 'ref01'), edge('ref01', 'ref01-ref')],
    )
    expect(selectSatelliteCount(state)).toBe(1)
  })

  it('is zero on an unexpanded graph, so the note stays hidden', () => {
    const state = stateWith([seed, { id: 'ref01' }], [edge('seed01', 'ref01')])
    expect(selectSatelliteCount(state)).toBe(0)
  })

  it('checks both endpoints — a citer points AT the seed', () => {
    const state = stateWith([seed, { id: 'cite01' }], [edge('cite01', 'seed01')])
    expect(selectSatelliteCount(state)).toBe(0)
  })

  it('never counts the seed itself', () => {
    expect(selectSatelliteCount(stateWith([seed], []))).toBe(0)
  })
})
