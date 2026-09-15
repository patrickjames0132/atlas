// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Navigation and persistence contracts formerly tested against useAutosave.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { configureStore } from '@reduxjs/toolkit'
import { act, cleanup, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { Provider } from 'react-redux'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../src/api'
import workspace, { viewFiltersSet, loadGraph, deleteThread } from '../../src/store/workspace'
import explorations, { threadEdited } from '../../src/store/explorations'
import transcript, {
  backgroundDiscovery,
  tokenAppended,
  turnStarted,
  turnCompleted,
  streamStarted,
  streamEnded,
} from '../../src/store/transcript'
import { useExplorations } from '../../src/shell/useExplorations'
import type { SaveSessionBody, SavedSession } from '../../src/api'

function makeStore() {
  return configureStore({ reducer: { workspace, transcript, explorations } })
}
function setup(store = makeStore()) {
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(Provider, { store }, children)
  return { ...renderHook(() => useExplorations(), { wrapper }), store }
}
async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1800)
  })
}
let saved: SaveSessionBody[]
beforeEach(() => {
  vi.useFakeTimers()
  localStorage.clear()
  saved = []
  vi.spyOn(api, 'listSessions').mockResolvedValue([])
  vi.spyOn(api, 'saveSession').mockImplementation(async (body) => {
    saved.push(body)
    return { id: body.id, name: body.name } as never
  })
  vi.spyOn(api, 'titleForConversation').mockResolvedValue(null)
  vi.spyOn(api, 'deleteSession').mockResolvedValue(true)
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => ({ summary: null }) })),
  )
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('exploration persistence', () => {
  it('does not save an untouched landing page', async () => {
    setup()
    await tick()
    expect(saved).toEqual([])
  })
  it('debounces tokens, saves completed prose, and keeps one row id', async () => {
    const { store } = setup()
    act(() => {
      store.dispatch(streamStarted('run'))
      store.dispatch(turnStarted('Why attention?'))
    })
    for (const text of ['Because ', 'it ', 'scales.']) {
      act(() => {
        store.dispatch(tokenAppended(text))
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200)
      })
    }
    expect(saved).toHaveLength(0)
    act(() => {
      store.dispatch(turnCompleted())
      store.dispatch(streamEnded('run'))
    })
    await tick()
    await tick()
    expect(saved.at(-1)?.exploration?.threads[0].data.chat[1].text).toBe('Because it scales.')
    const id = saved[0].id
    act(() => {
      store.dispatch(turnStarted('Follow up'))
      store.dispatch(tokenAppended('Answer'))
      store.dispatch(turnCompleted())
    })
    await tick()
    expect(saved.every((body) => body.id === id)).toBe(true)
    expect(api.titleForConversation).toHaveBeenCalledTimes(1)
  })
  it('saves without awaiting a stalled titler, including at pagehide', async () => {
    vi.mocked(api.titleForConversation).mockImplementation(() => new Promise(() => {}))
    const { store } = setup()
    act(() => {
      store.dispatch(turnStarted('Keep these words'))
    })
    await tick()
    expect(saved[0].name).toBe('Keep these words')
    act(() => {
      store.dispatch(tokenAppended('Partial answer'))
    })
    await act(async () => {
      window.dispatchEvent(new Event('pagehide'))
    })
    expect(saved.at(-1)?.exploration?.threads[0].data.chat[1].text).toBe('Partial answer')
  })
  it('writes the exploration being left, gives the next one its own id, and retains background updates', async () => {
    const { result, store } = setup()
    const first = store.getState().transcript.activeKey
    act(() => {
      store.dispatch(streamStarted('run'))
      store.dispatch(turnStarted('First'))
      result.current.create()
    })
    act(() => {
      store.dispatch(turnStarted('Second'))
      store.dispatch(tokenAppended('Late first answer', first))
      store.dispatch(streamEnded('run', first))
    })
    await tick()
    await tick()
    const firstSaved = saved.findLast(
      (body) => body.exploration?.threads[0].data.chat[0]?.text === 'First',
    )!
    const secondSaved = saved.findLast(
      (body) => body.exploration?.threads[0].data.chat[0]?.text === 'Second',
    )!
    expect(firstSaved.id).not.toBe(secondSaved.id)
    expect(firstSaved.exploration?.threads[0].data.chat[1].text).toBe('Late first answer')
  })
  it('does not rewrite a legacy save merely by opening it, but saves a subsequent reply in place', async () => {
    vi.spyOn(api, 'getSession').mockResolvedValue({
      id: 'old',
      name: 'My name',
      data: {
        layout: 'timeline',
        chat: [
          { role: 'user', text: 'Old question' },
          { role: 'assistant', text: 'Old answer' },
        ],
      },
    } as SavedSession)
    const { result, store } = setup()
    await act(async () => {
      await result.current.open('old')
    })
    await tick()
    expect(saved).toEqual([])
    act(() => {
      store.dispatch(turnStarted('New question'))
    })
    await tick()
    expect(saved.at(-1)?.id).toBe('old')
    expect(saved.at(-1)?.name).toBe('My name')
    expect(api.titleForConversation).not.toHaveBeenCalled()
  })
  it('saves an explicit filter edit without requiring another message', async () => {
    const { store } = setup()
    act(() => {
      store.dispatch(turnStarted('A question'))
    })
    await tick()
    const count = saved.length
    act(() => {
      store.dispatch(threadEdited())
      store.dispatch(
        viewFiltersSet({
          enabled: ['seed'],
          yearLo: 2000,
          yearHi: 2026,
          citeLo: 0,
          citeHi: 100,
          relCaps: {},
        }),
      )
    })
    await tick()
    expect(saved.length).toBeGreaterThan(count)
    expect(saved.at(-1)?.exploration?.threads[0].data.viewFilters?.yearLo).toBe(2000)
  })
  it('restores discoveries received while another exploration is active', async () => {
    vi.spyOn(api, 'fetchGraphStream').mockResolvedValue({
      seed: { id: 'seed', title: 'Seed' },
      nodes: [],
      edges: [],
    } as never)
    const { store, result } = setup()
    await act(async () => {
      await store.dispatch(loadGraph({ seed: 'seed' }))
    })
    const id = store.getState().explorations.activeId
    const key = store.getState().transcript.activeKey
    act(() => {
      result.current.create()
      store.dispatch(
        backgroundDiscovery(
          { nodes: [{ id: 'new-paper', title: 'New paper' } as never], edges: [] },
          key,
        ),
      )
    })
    await act(async () => {
      await result.current.open(id)
    })
    expect(store.getState().workspace.discoveredNodes.map((node) => node.id)).toContain('new-paper')
    expect(store.getState().transcript.byKey[key].pendingDiscoveries.nodes).toEqual([])
  })
  it('persists deletion of the last graph even when General is empty', async () => {
    vi.spyOn(api, 'fetchGraphStream').mockResolvedValue({
      seed: { id: 'only', title: 'Only graph' },
      nodes: [],
      edges: [],
    } as never)
    const { store } = setup()
    await act(async () => {
      await store.dispatch(loadGraph({ seed: 'only' }))
    })
    await tick()
    const key = store.getState().transcript.activeKey
    await act(async () => {
      await store.dispatch(deleteThread(key))
    })
    await tick()
    expect(saved.at(-1)?.exploration?.threads).toHaveLength(1)
    expect(saved.at(-1)?.exploration?.threads[0].title).toBe('General')
  })
  it('drops all owned conversations on deletion so late tokens cannot resurrect them', async () => {
    const { result, store } = setup()
    const id = store.getState().explorations.activeId
    const key = store.getState().transcript.activeKey
    act(() => {
      store.dispatch(turnStarted('Delete me'))
    })
    await tick()
    await act(async () => {
      await result.current.remove(id)
    })
    const count = saved.length
    act(() => {
      store.dispatch(tokenAppended('Late', key))
    })
    await tick()
    expect(saved).toHaveLength(count)
    expect(store.getState().transcript.byKey[key]).toBeUndefined()
  })
})
