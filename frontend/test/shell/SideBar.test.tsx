// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Shared row controls and exploration-owned collapsible thread navigation.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { configureStore } from '@reduxjs/toolkit'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Provider, useSelector } from 'react-redux'
import { afterEach, expect, it, vi } from 'vitest'
import SideBar from '../../src/shell/SideBar'
import workspace, { loadGraph } from '../../src/store/workspace'
import transcript from '../../src/store/transcript'
import explorations, { explorationOpened, newExploration } from '../../src/store/explorations'
import * as api from '../../src/api'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

/** Mount the actual sidebar with an exploration containing one graph.
 * @returns Store and parent record for navigation assertions.
 */
async function setup() {
  vi.spyOn(api, 'fetchGraphStream').mockResolvedValue({
    seed: { id: 'paper', title: 'Graph paper' },
    nodes: [],
    edges: [],
    counts: {},
  } as never)
  const store = configureStore({ reducer: { workspace, transcript, explorations } })
  const record = newExploration('saved')
  record.title = 'Saved exploration'
  store.dispatch(explorationOpened(record))
  await store.dispatch(loadGraph({ seed: 'paper' }))
  function Harness() {
    const activeId = useSelector(
      (state: ReturnType<typeof store.getState>) => state.explorations.activeId,
    )
    return (
      <SideBar
        open
        onToggle={() => {}}
        view="workspace"
        onView={() => {}}
        onNewGraph={() => store.dispatch(explorationOpened(newExploration()))}
        sessions={[{ id: record.id, name: record.title } as api.SavedSessionMeta]}
        openSessionId={activeId}
        onOpenSession={() => {}}
        onRenameSession={() => {}}
        onDeleteSession={() => {}}
        onOpenSettings={() => {}}
        onStartTour={() => {}}
        theme="dark"
        onToggleTheme={() => {}}
        provider="s2"
        onProviderChange={() => {}}
        loadingGraph={false}
        seedTitle={null}
      />
    )
  }
  render(
    <Provider store={store}>
      <Harness />
    </Provider>,
  )
  return { store, record }
}

it('collapses children under their own parent and hides them when starting a new exploration', async () => {
  await setup()
  expect(screen.getByText('General')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Saved exploration' }))
  expect(screen.queryByText('General')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Expand Saved exploration' }))
  expect(screen.getByText('General')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'New Exploration' }))
  expect(screen.queryByText('General')).toBeNull()
  expect(screen.queryByText('Graph paper')).toBeNull()
  expect(
    screen.getByRole('button', { name: 'Expand Saved exploration' }).getAttribute('aria-expanded'),
  ).toBe('false')
})

it('uses the existing menu and inline rename, then deletes a graph thread into General', async () => {
  const { store, record } = await setup()
  const graphId = store.getState().transcript.activeKey
  fireEvent.click(screen.getByRole('button', { name: 'Options for Graph paper' }))
  expect(screen.getByRole('menuitem', { name: /Delete/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('menuitem', { name: /Rename/ }))
  const input = screen.getByRole('textbox', { name: 'Rename Graph paper' })
  expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  fireEvent.change(input, { target: { value: 'Renamed graph' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(screen.getByText('Renamed graph')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Options for Renamed graph' }))
  await act(async () => fireEvent.click(screen.getByRole('menuitem', { name: /Delete/ })))
  await waitFor(() => expect(screen.queryByText('Renamed graph')).toBeNull())
  expect(store.getState().transcript.activeKey).toBe(record.activeThreadId)
  expect(store.getState().workspace.graph).toBeNull()
  expect(store.getState().transcript.byKey[graphId]).toBeUndefined()
})
