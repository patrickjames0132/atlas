// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The paper scout's turn in the transcript: it is driven through the same
 * reducers a streamed answer is, and — the part that was missing — it is
 * marked complete when it lands, so the search can be talked about
 * afterwards. An unfinished turn never reaches the model as history, and a
 * scout result that stayed unfinished forever made "what other papers
 * appeared in this search?" answer "I have no record of a prior search".
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UnknownAction } from '@reduxjs/toolkit'
import { conversationHistory } from '../../src/teacher/history'
import transcriptReducer from '../../src/store/transcript'
import type { TranscriptState } from '../../src/store/transcript'

/** Every action the hook dispatched, in order. */
const dispatched: UnknownAction[] = []

vi.mock('../../src/store', () => ({
  useAppDispatch: () => (action: UnknownAction) => {
    dispatched.push(action)
  },
}))

/** The scout's answer, scripted. Handlers are fired the way the SSE reader would. */
const searchLive = vi.fn()
vi.mock('../../src/api', () => ({
  searchLive: (...args: unknown[]) => searchLive(...args),
}))

const { useDirectSearch } = await import('../../src/search/useDirectSearch')

afterEach(() => {
  dispatched.length = 0
  searchLive.mockReset()
})

/**
 * Replay the dispatched actions through the real transcript reducer.
 *
 * @returns The transcript a live store would hold.
 */
function replay(): TranscriptState {
  return dispatched.reduce(
    (state, action) => transcriptReducer(state, action),
    transcriptReducer(undefined, { type: '@@test/init' }),
  )
}

describe('useDirectSearch', () => {
  it('marks the scout turn complete, so the search is history the model can see', async () => {
    searchLive.mockResolvedValue({
      papers: [{ id: 'p1', title: 'Playing Atari with Deep RL', year: 2013 }],
      summary: 'Found the DQN paper.',
      queries: ['dqn'],
    })
    const { result } = renderHook(() => useDirectSearch('s2', {}, () => {}))
    await act(async () => {
      await result.current.runSearch('dqn')
    })
    expect(dispatched.map((action) => action.type)).toEqual([
      'transcript/turnStarted',
      'transcript/answerSet',
      'transcript/paperRefsSet',
      'transcript/turnCompleted',
    ])
    const chat = replay().byKey.initial.chat
    expect(chat.at(-1)?.unfinished).toBe(false)
    // The whole point: the exchange is in the history the next question —
    // in this thread, or via `@thread[…]` from another — carries.
    const history = conversationHistory(chat)
    expect(history.map((turn) => turn.role)).toEqual(['user', 'assistant'])
    expect(history[0].content).toBe('dqn')
    expect(history[1].content).toContain('Playing Atari with Deep RL')
  })

  it('leaves a broken run unfinished, like an aborted answer', async () => {
    searchLive.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    const { result } = renderHook(() => useDirectSearch('s2', {}, onError))
    await act(async () => {
      await result.current.runSearch('dqn')
    })
    expect(dispatched.map((action) => action.type)).not.toContain('transcript/turnCompleted')
    expect(onError).toHaveBeenCalledWith('boom')
    expect(conversationHistory(replay().byKey.initial.chat)).toEqual([])
  })
})
