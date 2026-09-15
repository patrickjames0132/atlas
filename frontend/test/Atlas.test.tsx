// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Shell reconciliation across repeated graph and General thread navigation.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { act, cleanup, render, screen } from '@testing-library/react'
import { configureStore } from '@reduxjs/toolkit'
import { Provider } from 'react-redux'
import { afterEach, expect, it, vi } from 'vitest'
import Atlas from '../src/Atlas'
import workspace, { activateThread, loadGraph } from '../src/store/workspace'
import transcript from '../src/store/transcript'
import explorations from '../src/store/explorations'

vi.mock('../src/graph/GraphExplorer', () => ({
  default: () => <main data-testid="explorer">Graph</main>,
}))
vi.mock('../src/teacher/Teacher', () => ({
  default: () => <aside data-testid="teacher">Chat</aside>,
}))
vi.mock('../src/shell/SideBar', () => ({ default: () => null }))
vi.mock('../src/library/Sources', () => ({ default: () => null }))
vi.mock('../src/settings/SettingsModal', () => ({ default: () => null }))
vi.mock('../src/tour/Tour', () => ({ default: () => null }))
vi.mock('../src/shell/useExplorations', () => ({
  useExplorations: () => ({ sessions: [], working: [] }),
}))
vi.mock('../src/api', async (original) => ({
  ...(await original<typeof import('../src/api')>()),
  getSettings: vi.fn().mockRejectedValue(new Error('Offline test')),
  fetchGraphStream: vi.fn(async (seed: string) => ({
    seed: { id: seed, title: seed },
    nodes: [{ id: seed, rels: [], is_seed: true }],
    edges: [],
    counts: {},
  })),
}))
afterEach(() => cleanup())
it('replaces the explorer rather than accumulating sibling panels when threads change', async () => {
  const store = configureStore({ reducer: { workspace, transcript, explorations } })
  render(
    <Provider store={store}>
      <Atlas />
    </Provider>,
  )
  const general = store.getState().transcript.activeKey
  await act(async () => {
    await store.dispatch(loadGraph({ seed: 'first' }))
  })
  const first = store.getState().transcript.activeKey
  await act(async () => {
    await store.dispatch(loadGraph({ seed: 'second' }))
  })
  const second = store.getState().transcript.activeKey
  for (const key of [general, first, general, second, first, second, general, first]) {
    await act(async () => {
      await store.dispatch(activateThread(key))
    })
    expect(screen.queryAllByTestId('explorer')).toHaveLength(key === general ? 0 : 1)
    expect(screen.getAllByTestId('teacher')).toHaveLength(1)
  }
})
