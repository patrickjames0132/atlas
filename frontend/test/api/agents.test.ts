/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * `routeMessage`'s one real contract: it never rejects.
 *
 * This call sits in front of every message the reader sends, so a throw here
 * would break asking questions in order to protect a routing nicety. The
 * backend takes the same position for its own failures; these cover the ones
 * it never gets to see — the request that dies in the browser.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { routeMessage } from '../../src/api'

const ANSWER = { target: 'answer', framing: 'summary' }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('routeMessage', () => {
  it('returns the backend decision', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ target: 'lecture', framing: 'history' }),
      })),
    )
    expect(await routeMessage('lecture me on these')).toEqual({
      target: 'lecture',
      framing: 'history',
    })
  })

  it('sends the message untrimmed', async () => {
    // The backend's fast path anchors on how the message opens, and an `@`
    // mention is the router's to read — so the client must not tidy either
    // away first.
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ANSWER }))
    vi.stubGlobal('fetch', fetchMock)
    await routeMessage('  @DQN what is this?  ')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toEqual({ message: '  @DQN what is this?  ' })
  })

  it('answers when the request fails outright', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline')
      }),
    )
    expect(await routeMessage('what is attention?')).toEqual(ANSWER)
  })

  it('answers on a non-OK response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500 })),
    )
    expect(await routeMessage('what is attention?')).toEqual(ANSWER)
  })

  it('answers when the body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => {
          throw new Error('not json')
        },
      })),
    )
    expect(await routeMessage('what is attention?')).toEqual(ANSWER)
  })
})
