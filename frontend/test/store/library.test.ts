/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The library slice: one shared copy of the uploaded sources, written by the
 * Sources drawer's reloads and read live by the teacher's source-scope picker
 * — the staleness fix's contract is simply that a fulfilled load lands in the
 * state both surfaces watch.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { Source } from '../../src/api'
import reducer, { loadLibrary } from '../../src/store/library'

const A_SOURCE: Source = {
  id: 'src-1',
  title: 'Deep Learning',
  kind: 'pdf',
  origin: 'deep-learning.pdf',
  pages: 800,
  n_chunks: 1234,
  created_at: '2026-07-17T00:00:00Z',
}

describe('library slice', () => {
  it('starts empty, un-loaded, and assumed-available', () => {
    const state = reducer(undefined, { type: 'noop' })
    expect(state).toEqual({ available: true, sources: [], loaded: false, loading: false })
  })

  it('marks loading while a fetch is in flight', () => {
    const state = reducer(undefined, loadLibrary.pending('req-1', undefined))
    expect(state.loading).toBe(true)
    expect(state.loaded).toBe(false)
  })

  it('lands a fulfilled load for every reader at once', () => {
    const pending = reducer(undefined, loadLibrary.pending('req-1', undefined))
    const state = reducer(
      pending,
      loadLibrary.fulfilled({ available: true, sources: [A_SOURCE] }, 'req-1', undefined),
    )
    expect(state).toEqual({
      available: true,
      sources: [A_SOURCE],
      loaded: true,
      loading: false,
    })
  })

  it('a failed backend degrades to the disabled shape, still marked loaded', () => {
    // listSources never rejects — failures arrive as this payload.
    const state = reducer(
      undefined,
      loadLibrary.fulfilled({ available: false, sources: [] }, 'req-1', undefined),
    )
    expect(state.available).toBe(false)
    expect(state.loaded).toBe(true)
  })
})
