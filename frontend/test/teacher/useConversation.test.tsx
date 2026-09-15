// @vitest-environment jsdom
import { configureStore } from '@reduxjs/toolkit'
import { act, cleanup, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { Provider } from 'react-redux'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../src/api'
import workspace, { loadGraph, visibleNodesSet } from '../../src/store/workspace'
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
    vi.spyOn(api, 'routeMessage').mockResolvedValue({ target: 'answer', framing: 'summary' })
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
      await result.current.lectureInChat('/lecture', 'summary', false)
    })
    await act(async () => {
      await result.current.send('Why did they abandon it?', undefined)
    })
    expect(ask.mock.calls[0][0].history).toEqual([
      { role: 'user', content: '/lecture' },
      { role: 'assistant', content: 'Early methods\nThey abandoned the earlier approach.' },
    ])
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
