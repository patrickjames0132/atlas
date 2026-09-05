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
  buildSaveBody,
  loadGraph,
  saveWorkspace,
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

describe('restoring the three exploration shapes', () => {
  /** The conversation is the durable half — every shape must return it. */
  const CHAT = [{ role: 'user' as const, text: 'What is a diffusion model?' }]

  it('rebuilds the graph from a reference, and merges the stored discoveries', async () => {
    // The agent's finds are stored precisely because no rebuild reproduces
    // them, so they have to survive the rebuild and land on the graph.
    const api = await import('../../src/api')
    const getSession = vi.spyOn(api, 'getSession').mockResolvedValue({
      data: {
        graph_ref: {
          seed: { id: 'seed', arxiv_id: '1706.03762', title: 'Attention' },
          seed_ref: '1706.03762',
          n_nodes: 2,
        },
        provider: 's2',
        discovered_nodes: [makeNode('found-1')],
        discovered_edges: [{ source: 'seed', target: 'found-1', type: 'reference' }],
        chat: CHAT,
      },
    } as never)
    const rebuilt: GraphResponse = {
      seed: { id: 'seed', arxiv_id: '1706.03762', title: 'Attention' },
      nodes: [makeNode('seed'), makeNode('other')],
      edges: [],
      counts: {},
    } as never
    const fetchGraphStream = vi.spyOn(api, 'fetchGraphStream').mockResolvedValue(rebuilt)

    const action = await restoreSession('ref-1')(vi.fn(), vi.fn(), undefined)
    const payload = action.payload as {
      graph: GraphResponse | null
      seedRef: string | null
      discoveredNodes: GraphNode[]
    }

    // Rebuilt under the SAME reference it was saved with, so a later Refresh
    // busts the same cache key.
    expect(fetchGraphStream).toHaveBeenCalledWith('1706.03762', 's2')
    expect(payload.graph).toEqual(rebuilt)
    expect(payload.seedRef).toBe('1706.03762')
    expect(payload.discoveredNodes).toHaveLength(1)

    const state = reducer(undefined, { type: restoreSession.fulfilled.type, payload })
    expect(state.discoveredNodes.map((node) => node.id)).toEqual(['found-1'])

    getSession.mockRestore()
    fetchGraphStream.mockRestore()
  })

  it('keeps the conversation when the rebuild fails', async () => {
    // Losing the whole exploration because the provider is down would be a
    // worse bug than the one the autosave fixed.
    const api = await import('../../src/api')
    const getSession = vi.spyOn(api, 'getSession').mockResolvedValue({
      data: {
        graph_ref: { seed: { id: 'seed', title: 'Attention' }, seed_ref: '1706.03762' },
        discovered_nodes: [makeNode('found-1')],
        chat: CHAT,
      },
    } as never)
    const fetchGraphStream = vi
      .spyOn(api, 'fetchGraphStream')
      .mockRejectedValue(new Error('S2 is down'))

    const action = await restoreSession('ref-2')(vi.fn(), vi.fn(), undefined)
    const payload = action.payload as { graph: GraphResponse | null; transcript: TranscriptState }
    expect(payload.graph).toBeNull()
    expect(payload.transcript.chat).toHaveLength(1)

    // Discoveries hang off a graph that isn't there, so they're dropped.
    const state = reducer(undefined, { type: restoreSession.fulfilled.type, payload })
    expect(state.discoveredNodes).toEqual([])

    getSession.mockRestore()
    fetchGraphStream.mockRestore()
  })

  it('restores a graphless conversation without touching the provider', async () => {
    const api = await import('../../src/api')
    const getSession = vi
      .spyOn(api, 'getSession')
      .mockResolvedValue({ data: { chat: CHAT } } as never)
    const fetchGraphStream = vi.spyOn(api, 'fetchGraphStream')

    const action = await restoreSession('chat-only')(vi.fn(), vi.fn(), undefined)
    const payload = action.payload as {
      graph: GraphResponse | null
      seedRef: string | null
      transcript: TranscriptState
    }

    expect(fetchGraphStream).not.toHaveBeenCalled()
    expect(payload.graph).toBeNull()
    expect(payload.seedRef).toBeNull()
    expect(payload.transcript.chat).toHaveLength(1)

    getSession.mockRestore()
    fetchGraphStream.mockRestore()
  })

  it('uses a legacy inline graph directly, with no rebuild', async () => {
    // An old save keeps the exact papers it was stored with — rebuilding it
    // would silently swap them for whatever the provider says today.
    const api = await import('../../src/api')
    const getSession = vi.spyOn(api, 'getSession').mockResolvedValue({
      data: {
        seed: { id: 'seed', arxiv_id: '1706.03762', title: 'Attention' },
        nodes: [makeNode('seed'), makeNode('legacy-node')],
        edges: [],
        chat: CHAT,
      },
    } as never)
    const fetchGraphStream = vi.spyOn(api, 'fetchGraphStream')

    const action = await restoreSession('legacy')(vi.fn(), vi.fn(), undefined)
    const payload = action.payload as { graph: GraphResponse | null; seedRef: string | null }

    expect(fetchGraphStream).not.toHaveBeenCalled()
    expect(payload.graph?.nodes.map((node) => node.id)).toEqual(['seed', 'legacy-node'])
    expect(payload.seedRef).toBe('1706.03762')

    getSession.mockRestore()
    fetchGraphStream.mockRestore()
  })
})

/**
 * Wrap one conversation as the whole (keyed) transcript slice.
 *
 * The slice holds several conversations so a stream can keep writing to its
 * own exploration after the reader switches; a save still only ever describes
 * the active one.
 *
 * @param conversation The conversation's fields under test.
 * @returns A transcript slice with it active.
 */
function keyedTranscript(conversation: Record<string, unknown>): TranscriptState {
  return {
    byKey: { only: { lectures: {}, lectureSources: {}, activeMode: null, ...conversation } },
    activeKey: 'only',
  } as unknown as TranscriptState
}

describe('saveWorkspace sends a reference, not a graph', () => {
  /** A store state shaped like a real sitting: a graph plus one agent find. */
  function stateWith(graph: GraphResponse | null, seedRef: string | null) {
    return {
      workspace: {
        graph,
        seedRef,
        discoveredNodes: [makeNode('found-1')],
        discoveredEdges: [{ source: 'seed', target: 'found-1', type: 'reference' }],
        layout: 'timeline' as const,
        provider: 's2' as const,
      } as unknown as WorkspaceState,
      transcript: keyedTranscript({ chat: [{ role: 'user' as const, text: 'hi' }] }),
    }
  }

  const GRAPH = {
    seed: { id: 'seed', arxiv_id: '1706.03762', title: 'Attention' },
    nodes: [makeNode('seed'), makeNode('other')],
    edges: [],
    counts: {},
  } as unknown as GraphResponse

  it('stores the graph reference and the discoveries, but never the graph', async () => {
    const api = await import('../../src/api')
    const saveSession = vi
      .spyOn(api, 'saveSession')
      .mockResolvedValue({ id: 'row-1', name: 'A name' } as never)

    await saveWorkspace({ name: 'A name' })(
      vi.fn(),
      () => stateWith(GRAPH, '1706.03762'),
      undefined,
    )

    const body = saveSession.mock.calls[0][0] as Record<string, unknown>
    expect(body.graph_ref).toEqual({
      seed: GRAPH.seed,
      seed_ref: '1706.03762',
      n_nodes: 2,
    })
    // The whole point: the graph's own nodes/edges do not go on the wire.
    expect(body.nodes).toBeUndefined()
    expect(body.edges).toBeUndefined()
    // The agent's finds do, because no rebuild reproduces them.
    expect(body.discovered_nodes).toHaveLength(1)
    expect(body.discovered_edges).toHaveLength(1)
    saveSession.mockRestore()
  })

  it('saves a graphless conversation instead of throwing', async () => {
    // This used to throw `No graph to save yet.`, which meant a conversation
    // held before any graph existed could not be stored at all.
    const api = await import('../../src/api')
    const saveSession = vi
      .spyOn(api, 'saveSession')
      .mockResolvedValue({ id: 'row-2', name: 'Just a chat' } as never)

    await saveWorkspace({ name: 'Just a chat' })(vi.fn(), () => stateWith(null, null), undefined)

    const body = saveSession.mock.calls[0][0] as Record<string, unknown>
    expect(body.graph_ref).toBeUndefined()
    expect(body.chat).toHaveLength(1)
    saveSession.mockRestore()
  })

  it('omits the reference when a graph has no seedRef to rebuild from', async () => {
    // A graph_ref without a usable reference would be unrebuildable — worse
    // than none, because restore would try and fail rather than degrade.
    const api = await import('../../src/api')
    const saveSession = vi
      .spyOn(api, 'saveSession')
      .mockResolvedValue({ id: 'row-3', name: 'No ref' } as never)

    await saveWorkspace({ name: 'No ref' })(vi.fn(), () => stateWith(GRAPH, null), undefined)

    expect((saveSession.mock.calls[0][0] as Record<string, unknown>).graph_ref).toBeUndefined()
    saveSession.mockRestore()
  })
})

describe('a saved turn is never mid-stream', () => {
  /** Switching explorations flushes a save and then aborts the stream, so a
   *  turn caught mid-answer must not be persisted as "still working". */
  function stateWithTrace(trace: unknown[]) {
    return {
      workspace: {
        graph: null,
        seedRef: null,
        discoveredNodes: [],
        discoveredEdges: [],
        layout: 'timeline' as const,
        provider: 's2' as const,
      } as unknown as WorkspaceState,
      transcript: keyedTranscript({
        chat: [
          { role: 'user' as const, text: "What's new in quantum computing?" },
          { role: 'assistant' as const, text: 'Partial answer so far', trace },
        ],
      }),
    }
  }

  it('settles a pending trace step, keeping the partial answer', async () => {
    const body = buildSaveBody(
      stateWithTrace([
        { action: 'search_web', ok: true, pending: true, need: 'latest news' },
        { action: 'search_sources', ok: true, found: 2 },
      ]),
      'Quantum computing',
    )
    const [, assistant] = body.chat
    // The spinner is gone — this step never finished and never will.
    expect(assistant.trace?.[0]).toMatchObject({ pending: false, ok: false })
    // A step that genuinely completed is untouched.
    expect(assistant.trace?.[1]).toMatchObject({ ok: true, found: 2 })
    // The partial answer is real work and is kept.
    expect(assistant.text).toBe('Partial answer so far')
  })

  it('leaves a settled conversation alone', async () => {
    const trace = [{ action: 'search_web', ok: true, found: 3 }]
    const body = buildSaveBody(stateWithTrace(trace), 'Quantum computing')
    expect(body.chat[1].trace).toBe(trace)
  })
})

describe('an abandoned answer is marked when it is saved', () => {
  /** The tab-close case: the client never reaches the end of the run, so the
   *  stream cannot mark the turn — the save has to. */
  function chatEndingWith(turns: unknown[]) {
    return {
      workspace: {
        graph: null,
        seedRef: null,
        discoveredNodes: [],
        discoveredEdges: [],
        layout: 'timeline' as const,
        provider: 's2' as const,
      } as unknown as WorkspaceState,
      transcript: keyedTranscript({ chat: turns }),
    }
  }

  it('marks a last turn that has a trace but never produced prose', () => {
    const body = buildSaveBody(
      chatEndingWith([
        { role: 'user', text: 'What is few-shot learning?' },
        { role: 'assistant', text: '', trace: [{ action: 'search', ok: true, pending: true }] },
      ]),
      'Few-shot learning',
    )
    expect(body.chat[1].failed).toBeTruthy()
    // And the spinner is settled in the same pass.
    expect(body.chat[1].trace?.[0]).toMatchObject({ pending: false })
  })

  it('leaves an answer that produced prose alone', () => {
    const body = buildSaveBody(
      chatEndingWith([
        { role: 'user', text: 'q' },
        { role: 'assistant', text: 'A real answer.' },
      ]),
      'Whatever',
    )
    expect(body.chat[1].failed).toBeUndefined()
  })

  it('does not mark a turn that is merely waiting to be asked', () => {
    // A user turn is not a failed answer.
    const body = buildSaveBody(chatEndingWith([{ role: 'user', text: 'q' }]), 'Whatever')
    expect(body.chat[0].failed).toBeUndefined()
  })
})
