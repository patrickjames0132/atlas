/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Regression tests for thread ownership and completed history.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { configureStore } from '@reduxjs/toolkit'
import { describe, expect, it, vi } from 'vitest'
import workspace, { activateThread, loadGraph, nodeSelectionSet } from '../../src/store/workspace'
import transcript, { tokenAppended, turnStarted } from '../../src/store/transcript'
import explorations, { explorationOpened, newExploration } from '../../src/store/explorations'
import { migrateExploration, explorationBody } from '../../src/store/threadPersistence'
import type { GraphResponse, SavedSession } from '../../src/api'

vi.mock('../../src/api', async (original) => ({
  ...(await original<typeof import('../../src/api')>()),
  fetchGraphStream: vi.fn(async (seed: string) => graph(seed)),
}))

function graph(id: string): GraphResponse {
  return {
    seed: { id, title: id, arxiv_id: null },
    nodes: [{ id, title: id, url: '', is_seed: true, rels: [], citation_count: 1, year: 2020 }],
    edges: [],
    counts: {},
  } as GraphResponse
}
function makeStore() {
  return configureStore({ reducer: { workspace, transcript, explorations } })
}

describe('thread ownership', () => {
  it('keeps General graphless, restores graph selections, and routes background tokens to their owner', async () => {
    const store = makeStore()
    const record = newExploration('explore')
    store.dispatch(explorationOpened(record))
    const general = record.activeThreadId
    store.dispatch(turnStarted('general question'))
    await store.dispatch(loadGraph({ seed: 'DQN' }))
    const dqn = store.getState().transcript.activeKey
    expect(dqn).not.toBe(general)
    store.dispatch(nodeSelectionSet(['DQN']))
    store.dispatch(turnStarted('DQN question'))
    await store.dispatch(loadGraph({ seed: 'PPO' }))
    store.dispatch(tokenAppended('DQN background answer', dqn))
    expect(store.getState().transcript.byKey[dqn].chat.at(-1)?.text).toBe('DQN background answer')
    expect(store.getState().transcript.byKey[store.getState().transcript.activeKey].chat).toEqual(
      [],
    )
    await store.dispatch(activateThread(dqn))
    expect(store.getState().workspace.graph?.seed.id).toBe('DQN')
    expect(store.getState().workspace.selectedNodeIds).toEqual(['DQN'])
    await store.dispatch(activateThread(general))
    expect(store.getState().workspace.graph).toBeNull()
    expect(store.getState().transcript.byKey[general].chat[0].text).toBe('general question')
  })
  it('reuses graph threads by resolved seed and provider', async () => {
    const store = makeStore()
    await store.dispatch(loadGraph({ seed: 'same', provider: 's2' }))
    const first = store.getState().transcript.activeKey
    await store.dispatch(loadGraph({ seed: 'same', provider: 'openalex' }))
    expect(store.getState().transcript.activeKey).not.toBe(first)
    await store.dispatch(loadGraph({ seed: 'same', provider: 's2' }))
    expect(store.getState().transcript.activeKey).toBe(first)
    const record = store.getState().explorations.byId[store.getState().explorations.activeId]
    expect(record.threads).toHaveLength(3)
  })
})

describe('legacy migration', () => {
  it('splits stamped pairs by provider and preserves every unstamped turn without mutating the saved blob', () => {
    const saved = {
      id: 'old',
      name: 'Learning',
      data: {
        layout: 'timeline',
        provider: 's2',
        graph_ref: { seed: { id: 'DQN', title: 'DQN' }, seed_ref: 'DQN' },
        chat: [
          { role: 'user', text: 'old unstamped' },
          { role: 'assistant', text: 'old answer' },
          { role: 'user', text: 'new question' },
          {
            role: 'assistant',
            text: 'new answer',
            graph: { seedId: 'DQN', seedTitle: 'Other provider', nodes: 1, provider: 'openalex' },
          },
          { role: 'user', text: 'unanswered' },
        ],
      },
    } as SavedSession
    const original = JSON.stringify(saved)
    const migrated = migrateExploration(saved)
    expect(
      migrated.threads
        .find((thread) => thread.identity === 's2:DQN')
        ?.data.chat.map((turn) => turn.text),
    ).toEqual(['old unstamped', 'old answer', 'unanswered'])
    expect(
      migrated.threads
        .find((thread) => thread.identity === 'openalex:DQN')
        ?.data.chat.map((turn) => turn.text),
    ).toEqual(['new question', 'new answer'])
    expect(JSON.stringify(saved)).toBe(original)
  })
  it('round-trips all threads and does not erase a failed graph rebuild reference', async () => {
    const store = makeStore()
    await store.dispatch(loadGraph({ seed: 'DQN' }))
    store.dispatch(turnStarted('question'))
    await store.dispatch(loadGraph({ seed: 'PPO' }))
    const state = store.getState()
    const record = state.explorations.byId[state.explorations.activeId]
    const body = explorationBody(state, record)
    const restored = migrateExploration({
      id: body.id,
      name: body.name,
      data: body,
    } as SavedSession)
    expect(restored.threads).toHaveLength(3)
    expect(restored.threads.find((thread) => thread.identity === 's2:DQN')?.data.chat[0].text).toBe(
      'question',
    )
    expect(restored.threads.every((thread) => !thread.workspace)).toBe(true)
  })
})
