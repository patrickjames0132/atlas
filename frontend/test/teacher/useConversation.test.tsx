// @vitest-environment jsdom
import { configureStore } from '@reduxjs/toolkit'
import { act, cleanup, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { Provider } from 'react-redux'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../src/api'
import workspace, { loadGraph, nodeSelectionSet, visibleNodesSet } from '../../src/store/workspace'
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

describe('a lecture request that says which papers', () => {
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

  const setUp = async (
    route: Omit<api.MessageRoute, 'year_from' | 'year_to'> & Partial<api.MessageRoute>,
    resolved: string[] = [],
  ) => {
    vi.spyOn(api, 'fetchGraphStream').mockResolvedValue(scopedGraph)
    vi.spyOn(api, 'routeMessage').mockResolvedValue({ ...anyTime, ...route })
    const resolve = vi.spyOn(api, 'resolveRoutedPapers').mockResolvedValue(resolved)
    const lecture = vi.spyOn(api, 'streamLecture').mockImplementation(async (_body, options) => {
      options.onBeat?.(beat)
    })
    const store = configureStore({
      reducer: { workspace, transcript, explorations, highlight, library },
    })
    await store.dispatch(loadGraph({ seed: 'seed' }))
    // r2 is filtered out of the view; everything else is on screen.
    store.dispatch(visibleNodesSet(['seed', 'r1', 'c1']))
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(Provider, { store }, children)
    const { result } = renderHook(() => useConversation(), { wrapper })
    return { store, result, lecture, resolve }
  }

  it('narrates what is on screen, untouched, when the message does not say', async () => {
    const { store, result, lecture, resolve } = await setUp({
      target: 'lecture',
      framing: 'summary',
      scope: 'screen',
    })
    await act(async () => {
      await result.current.send('lecture me on these', undefined)
    })
    expect(lecture.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['seed', 'r1', 'c1'])
    expect(store.getState().workspace.selectedNodeIds).toEqual([])
    expect(store.getState().workspace.revealedNodeIds).toEqual([])
    // No paper list crossed the wire: the resolver is the named scope's call.
    expect(resolve).not.toHaveBeenCalled()
    // And the whole lecture stays lit once it ends, bubble active.
    expect(store.getState().highlight.ids).toEqual(['seed'])
    expect(result.current.activeChat).toBe(1)
    expect(result.current.activeChatBeat).toBeNull()
  })

  it('scopes the canvas to the references while it streams, then lets the scope go', async () => {
    const { store, result, lecture } = await setUp({
      target: 'lecture',
      framing: 'history',
      scope: 'references',
    })
    // What the canvas looked like mid-lecture: the scope selected.
    let selectedWhileStreaming: string[] = []
    lecture.mockImplementation(async (_body, options) => {
      selectedWhileStreaming = store.getState().workspace.selectedNodeIds
      options.onBeat?.({ ...beat, node_ids: ['r1'] })
      options.onBeat?.({ ...beat, node_ids: ['r2', 'r1'] })
    })
    await act(async () => {
      await result.current.send('lecture me on the references', undefined)
    })
    const body = lecture.mock.calls[0][0]
    expect(body.nodes.map((item) => item.id)).toEqual(['r1', 'r2'])
    expect(body.framing).toBe('history')
    expect(selectedWhileStreaming).toEqual(['r1', 'r2'])
    // One-shot: the selection is released once the lecture ends, leaving the
    // whole lecture lit rather than a scope the reader has to clear.
    expect(store.getState().workspace.selectedNodeIds).toEqual([])
    expect(store.getState().highlight.ids).toEqual(['r1', 'r2'])
    // r2 was filtered out; the message brought it back rather than narrating
    // something invisible — and it stays back, or the highlight would be
    // lighting nothing.
    expect(store.getState().workspace.revealedNodeIds).toEqual(['r2'])
    // And the turn counts the scope it narrated, not the screen's.
    const chat = store.getState().transcript.byKey[store.getState().transcript.activeKey].chat
    expect(chat[1].graph?.nodes).toBe(2)
    expect(chat[1].routedTo).toBe('lecture')
  })

  it('resolves named papers against a thin list and narrates the ones it found', async () => {
    const { store, result, lecture, resolve } = await setUp(
      { target: 'lecture', framing: 'summary', scope: 'named' },
      ['c1'],
    )
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
    expect(lecture.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['c1'])
    expect(store.getState().highlight.ids).toEqual(['seed'])
  })

  it('keeps a selection the reader re-picked mid-lecture', async () => {
    const { store, result, lecture } = await setUp({
      target: 'lecture',
      framing: 'summary',
      scope: 'references',
    })
    lecture.mockImplementation(async (_body, options) => {
      store.dispatch(nodeSelectionSet(['c1']))
      options.onBeat?.(beat)
    })
    await act(async () => {
      await result.current.send('lecture me on the references', undefined)
    })
    expect(store.getState().workspace.selectedNodeIds).toEqual(['c1'])
  })

  it('reads a period off the message and scopes to it, revealing hidden years', async () => {
    const { store, result, lecture } = await setUp({
      target: 'lecture',
      framing: 'summary',
      scope: 'screen',
      year_from: 2015,
      year_to: 2015,
    })
    await act(async () => {
      await result.current.send('summarize the papers from 2015', undefined)
    })
    expect(lecture.mock.calls[0][0].nodes.map((item) => item.id)).toEqual(['r1', 'r2', 'c1'])
    expect(store.getState().workspace.revealedNodeIds).toEqual(['r2'])
  })

  it('fails the turn in words when nothing falls in the period', async () => {
    const { store, result, lecture } = await setUp({
      target: 'lecture',
      framing: 'summary',
      scope: 'references',
      year_from: 1990,
      year_to: 1999,
    })
    await act(async () => {
      await result.current.send('lecture me on the references from the 90s', undefined)
    })
    expect(lecture).not.toHaveBeenCalled()
    const chat = store.getState().transcript.byKey[store.getState().transcript.activeKey].chat
    expect(chat[1].failed).toBe('This graph has no references from 1990–1999 to lecture on.')
  })

  it('fails the turn in words when the named papers are not on the graph', async () => {
    const { store, result, lecture } = await setUp(
      { target: 'lecture', framing: 'summary', scope: 'named' },
      [],
    )
    await act(async () => {
      await result.current.send('lecture me on BERT', undefined)
    })
    expect(lecture).not.toHaveBeenCalled()
    const chat = store.getState().transcript.byKey[store.getState().transcript.activeKey].chat
    expect(chat[0]).toMatchObject({ role: 'user', text: 'lecture me on BERT' })
    expect(chat[1].failed).toMatch(/None of the papers you named are on this graph/)
    expect(chat[1].routedTo).toBe('lecture')
    // The canvas is left alone: there was nothing to scope it to.
    expect(store.getState().workspace.selectedNodeIds).toEqual([])
    expect(result.current.asking).toBe(false)
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
