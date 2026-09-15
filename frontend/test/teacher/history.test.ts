/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Regression tests for thread ownership and completed history.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { describe, expect, it } from 'vitest'
import { conversationHistory, toHistoryTurn } from '../../src/teacher/history'

describe('completed conversational history', () => {
  it('includes lecture prose and removes figure markers', () => {
    expect(
      toHistoryTurn({
        role: 'assistant',
        text: '',
        beats: [{ heading: 'Origins', text: 'Earlier work.\n<<FIG 1>>\nNext idea.', node_ids: [] }],
      }),
    ).toEqual({ role: 'assistant', content: 'Origins\nEarlier work.\nNext idea.' })
  })
  it('omits interrupted exchanges and retains the completed follow-up', () => {
    expect(
      conversationHistory([
        { role: 'user', text: 'abandoned' },
        { role: 'assistant', text: 'partial', unfinished: true },
        { role: 'user', text: 'question' },
        { role: 'assistant', text: 'answer' },
      ]),
    ).toEqual([
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'answer' },
    ])
  })
})
