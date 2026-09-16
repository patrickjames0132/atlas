// @vitest-environment jsdom
import { configureStore } from '@reduxjs/toolkit'
import { act, cleanup, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { Provider } from 'react-redux'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../src/api'
import workspace, {
  loadGraph,
  nodeSelectionSet,
  nodeSelectionToggled,
  visibleNodesSet,
} from '../../src/store/workspace'
import transcript from '../../src/store/transcript'
import explorations from '../../src/store/explorations'
import highlight from '../../src/store/highlight'
import library from '../../src/store/library'
import { useConversation } from '../../src/teacher/useConversation'

const graph = {
  seed: { id: 'seed', title: 'Seed', arxiv_id: null },
  nodes: [
    { id: 'seed', title: 'Seed', is_seed: true, year: 2020, citation_count: 1, url: '', rels: [] },
  ],
  edges: [],
  counts: {},
} as api.GraphResponse
const beat = {
  heading: 'Early methods',
  text: 'They abandoned the earlier approach.',
  node_ids: ['seed'],
} as api.Beat

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('lecture follow-up history', () => {
  it('sends actual completed lecture prose to an ordinary researcher request', async () => {
    vi.spyOn(api, 'fetchGraphStream').mockResolvedValue(graph)
    vi.spyOn(api, 'routeMessage').mockResolvedValue({
      target: 'answer',
      framing: 'summary',
      scope: 'screen',
      year_from: null,
      year_to: null,
    })
    vi.spyOn(api, 'streamLecture').mockImplementation(async (_body, options) => {
      options.onBeat?.(beat)
    })
    const ask = vi.spyOn(api, 'streamAsk').mockImplementation(async (_body, options) => {
      options.onToken?.('Because it was inefficient.')
    })
    const store = configureStore({
      reducer: { workspace, transcript, explorations, highlight, library },
    })
    await store.dispatch(loadGraph({ seed: 'seed' }))
    store.dispatch(visibleNodesSet(['seed']))
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(Provider, { store }, children)
    const { result } = renderHook(() => useConversation(), { wrapper })
    await act(async () => {
      await result.current.lectureInChat('lecture me on these', 'summary', false)
    })
    await act(async () => {
      await result.current.send('Why did they abandon it?', undefined)
    })
    expect(ask.mock.calls[0][0].history).toEqual([
      { role: 'user', content: 'lecture me on these' },
      { role: 'assistant', content: 'Early methods\nThey abandoned the earlier approach.' },
    ])
  })
})

describe('the scope priority list, resolved once per turn', () => {
  // A seed, two of its references (one hidden by the view filter), one citer.
  const node = (id: string, rels: string[], extra: object = {}) => ({
    id,
    title: `Paper ${id}`,
    is_seed: false,
    year: 2015,
    citation_count: 1,
    url: '',
    arxiv_id: null,
    authors: `Author ${id}`,
    rels,
    ...extra,
  })
  const scopedGraph = {
    ...graph,
    nodes: [
      graph.nodes[0],
      node('r1', ['reference']),
      node('r2', ['reference']),
      node('c1', ['citation']),
    ],
  } as api.GraphResponse

  const anyTime = { year_from: null, year_to: null }
  type Route = Omit<api.MessageRoute, 'year_from' | 'year_to'> & Partial<api.MessageRoute>
  const lecture = (scope: api.LectureScope, extra: Partial<api.MessageRoute> = {}): Route => ({
    target: 'lecture',
    framing: 'summary',
    scope,
    ...extra,
  })
  const answer = (scope: api.LectureScope, extra: Partial<api.MessageRoute> = {}): Route => ({
    target: 'answer',
    framing: 'summary',
    scope,
    ...extra,
  })

  const setUp = async (route: Route, resolved: string[] = []) => {
    vi.spyOn(api, 'fetchGraphStream').mockResolvedValue(scopedGraph)
    vi.spyOn(api, 'routeMessage').mockResolvedValue({ ...anyTime, ...route })
    const resolve = vi.spyOn(api, 'resolveRoutedPapers').mockResolvedValue(resolved)
    const streamLecture = vi
      .spyOn(api, 'streamLecture')
      .mockImplementation(async (_body, options) => {
        options.onBeat?.(beat)
      })
    const streamAsk = vi.spyOn(api, 'streamAsk').mockImplementation(async (_body, options) => {
      options.onToken?.('An answer.')
    })
    const store = configureStore({
      reducer: { workspace, transcript, explorations, highlight, library },
    })
    await store.dispatch(loadGraph({ seed: 'seed' }))
    // r2 is filtered out of the view; everything else passes.
    store.dispatch(visibleNodesSet(['seed', 'r1', 'c1']))
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(Provider, { store }, children)
    const { result } = renderHook(() => useConversation(), { wrapper })
    const lastTurn = () => {
      const chat = store.getState().transcript.byKey[store.getState().transcript.activeKey].chat
      return chat[chat.length - 1]
    }
    return { store, result, streamLecture, streamAsk, resolve, lastTurn }
  }

  it('defaults to what passes the filters, and says nothing about it', async () => {
    const { store, result, streamLecture, resolve, lastTurn } = await setUp(lecture('screen'))
    await act(async () => {
      await result.current.send('lecture me on these', undefined)
    })
    expect(streamLecture.mock.calls[0][0].nodes.map((item) => item.id)).toEqual([
      'seed',
      'r1',
      'c1',
    ])
    expect(store.getState().workspace.selectedNodeIds).toEqual([])
    expect(lastTurn().scope).toEqual({ source: 'visible', nodes: 3 })
    // No paper list crossed the wire: the resolver is the named scope's call.
    expect(resolve).not.toHaveBeenCalled()
    // And the whole lecture stays lit once it ends, bubble active.
    expect(store.getState().highlight.ids).toEqual(['seed'])
    expect(result.current.activeChat).toBe(1)
  })

  it('makes a message scope the selection, and it stays after the turn', async () => {
    const { store, result, streamLecture, lastTurn } = await setUp(
      lecture('references', { framing: 'history' }),
    )
    let selectedWhileStreaming: string[] = []
    streamLecture.mockImplementation(async (_body, options) => {
      selectedWhileStreaming = store.getState().workspace.selectedNodeIds
      options.onBeat?.({ ...beat, node_ids: ['r1'] })
      options.onBeat?.({ ...beat, node_ids: ['r2', 'r1'] })
    })
    await act(async () => {
      await result.current.send('lecture me on the references', undefined)
    })
    const body = streamLecture.mock.calls[0][0]
    // r2 is hidden by the filters and in scope anyway: the message outranks them.
    expect(body.nodes.map((item) => item.id)).toEqual(['r1', 'r2'])
    expect(body.framing).toBe('history')
    expect(selectedWhileStreaming).toEqual(['r1', 'r2'])
    // The scope the message chose is the selection now, like one made by
    // hand — it does not revert. And the whole lecture stays lit.
    expect(store.getState().workspace.selectedNodeIds).toEqual(['r1', 'r2'])
    expect(store.getState().highlight.ids).toEqual(['r1', 'r2'])
    expect(lastTurn().scope).toEqual({
      source: 'message',
      nodes: 2,
      kind: 'references',
      years: { from: null, to: null },
      ids: [],
    })
    expect(lastTurn().graph?.nodes).toBe(2)
  })

  it('replaces a prior hand-picked selection with the message scope, keeping mid-turn edits', async () => {
    const { store, result, streamAsk } = await setUp(answer('citations'))
    store.dispatch(nodeSelectionSet(['r1']))
    let selectedWhileStreaming: string[] = []
    streamAsk.mockImplementation(async (_body, options) => {
      selectedWhileStreaming = store.getState().workspace.selectedNodeIds
      // The reader edits the selection while the agent runs.
      store.dispatch(nodeSelectionToggled('r2'))
      options.onToken?.('An answer.')
    })
    await act(async () => {
      await result.current.send('what do the citations say?', undefined)
    })
    // The question grounded in the message's scope, not the old selection.
    expect(streamAsk.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['c1'])
    expect(selectedWhileStreaming).toEqual(['c1'])
    // Nothing reverts at the end: the message's scope plus the reader's edit.
    expect(store.getState().workspace.selectedNodeIds).toEqual(['c1', 'r2'])
  })

  it('grounds a question in the selection even where the filters hide part of it', async () => {
    const { store, result, streamAsk, lastTurn } = await setUp(answer('screen'))
    store.dispatch(nodeSelectionSet(['r1', 'r2']))
    await act(async () => {
      await result.current.send('compare these', undefined)
    })
    expect(streamAsk.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['r1', 'r2'])
    expect(lastTurn().scope).toEqual({ source: 'selection', nodes: 2 })
  })

  it('resolves named papers against a thin list and scopes to the ones it found', async () => {
    const { result, streamLecture, resolve } = await setUp(lecture('named'), ['c1'])
    await act(async () => {
      await result.current.send('lecture me on Paper c1', undefined)
    })
    // The whole graph, titles and authors only — no abstracts, no baggage.
    expect(resolve.mock.calls[0][1]).toEqual([
      { id: 'seed', title: 'Seed', year: 2020, authors: undefined },
      { id: 'r1', title: 'Paper r1', year: 2015, authors: 'Author r1' },
      { id: 'r2', title: 'Paper r2', year: 2015, authors: 'Author r2' },
      { id: 'c1', title: 'Paper c1', year: 2015, authors: 'Author c1' },
    ])
    expect(streamLecture.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['c1'])
  })

  it('narrows a bare period within the current context, and scopes a question by it', async () => {
    const { result, streamAsk, lastTurn } = await setUp(
      answer('screen', { year_from: 2015, year_to: 2015 }),
    )
    await act(async () => {
      await result.current.send('summarize the papers from 2015', undefined)
    })
    // r2 (2015) is hidden by the filters and stays hidden: a bare period
    // narrows what the reader was looking at, it does not reach past it.
    expect(streamAsk.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['r1', 'c1'])
    expect(lastTurn().scope).toMatchObject({ source: 'message', years: { from: 2015, to: 2015 } })
  })

  it('fails the turn in words when an explicit scope matches nothing, for either agent', async () => {
    for (const [route, pattern] of [
      [lecture('named'), /None of the papers you named are on this graph/],
      [answer('references', { year_from: 1990, year_to: 1999 }), /no references from 1990–1999/],
    ] as const) {
      const { store, result, streamLecture, streamAsk, lastTurn } = await setUp(route, [])
      store.dispatch(nodeSelectionSet(['r1']))
      await act(async () => {
        await result.current.send('lecture me on BERT', undefined)
      })
      // Never falls through to the selection or the visible papers.
      expect(streamLecture).not.toHaveBeenCalled()
      expect(streamAsk).not.toHaveBeenCalled()
      expect(lastTurn().failed).toMatch(pattern)
      expect(lastTurn().routedTo).toBe(route.target)
      // The selection is left as it was: a scope that matched nothing
      // replaces nothing.
      expect(store.getState().workspace.selectedNodeIds).toEqual(['r1'])
      expect(result.current.asking).toBe(false)
      cleanup()
      vi.restoreAllMocks()
    }
  })

  it('keeps the message scope as the selection even when the turn fails', async () => {
    const { store, result, streamLecture } = await setUp(lecture('references'))
    streamLecture.mockImplementation(async (_body, options) => {
      options.onError?.('the model fell over')
    })
    await act(async () => {
      await result.current.send('lecture me on the references', undefined)
    })
    // The scope was set before the turn ran; a retry asks over the same set.
    expect(store.getState().workspace.selectedNodeIds).toEqual(['r1', 'r2'])
  })

  it('re-asks a corrected turn for the same papers, against the graph as it stands', async () => {
    const { store, result, streamAsk, lastTurn } = await setUp(lecture('references'))
    await act(async () => {
      await result.current.send('lecture me on the references', undefined)
    })
    await act(async () => {
      result.current.reroute(1)
      await Promise.resolve()
    })
    expect(streamAsk.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['r1', 'r2'])
    expect(lastTurn().scope).toMatchObject({ source: 'message', kind: 'references' })
    expect(store.getState().workspace.selectedNodeIds).toEqual(['r1', 'r2'])
  })
})

it('highlights paper references without fetching, and graph icons open or resume a thread', async () => {
  const build = vi
    .spyOn(api, 'fetchGraphStream')
    .mockImplementation(async (seed) => ({ ...graph, seed: { ...graph.seed, id: seed } }))
  const details = vi.spyOn(api, 'fetchPaperDetail')
  const store = configureStore({
    reducer: { workspace, transcript, explorations, highlight, library },
  })
  await store.dispatch(loadGraph({ seed: 'seed' }))
  const originalThread = store.getState().transcript.activeKey
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(Provider, { store }, children)
  const { result } = renderHook(() => useConversation(), { wrapper })
  build.mockClear()
  act(() => result.current.onRefClick('seed'))
  expect(store.getState().highlight.ids).toEqual(['seed'])
  expect(store.getState().transcript.activeKey).toBe(originalThread)
  act(() => result.current.onRefClick('seed'))
  expect(store.getState().highlight.ids).toEqual([])
  expect(build).not.toHaveBeenCalled()
  await act(async () => {
    result.current.onPaperSeed('another', 's2')
  })
  const nextThread = store.getState().transcript.activeKey
  expect(nextThread).not.toBe(originalThread)
  expect(store.getState().workspace.graph?.seed.id).toBe('another')
  await act(async () => {
    result.current.onPaperSeed('seed', 's2')
  })
  expect(store.getState().transcript.activeKey).toBe(originalThread)
  expect(details).not.toHaveBeenCalled()
})
