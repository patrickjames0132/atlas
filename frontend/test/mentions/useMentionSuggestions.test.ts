// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention typeahead's cost guarantees. Two clocks, and the split is
 * the point: the **cache-only** lookup is free and offline, so it runs on
 * every keystroke; the **provider** lookup waits for a pause, refuses queries
 * under the minimum length, and supersedes the request before it.
 *
 * This is the half of the feature that could quietly become expensive — it
 * runs while someone types — so what costs money is counted here rather than
 * trusted.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMentionSuggestions } from '../../src/mentions/useMentionSuggestions'

/** Calls the fake `fetch` received, in order. */
let calls: string[] = []

/** Only the lookups that reach a provider — what actually costs anything. */
const paidCalls = () => calls.filter((url) => !url.includes('source=local'))

/** Only the free, cache-only lookups. */
const freeCalls = () => calls.filter((url) => url.includes('source=local'))

/**
 * A fake `Response` carrying an SSE body, for the streamed full pass.
 *
 * @param frames The `[event, data]` pairs to emit, in order.
 * @returns Something `readSSE` can consume.
 */
function sseResponse(frames: [string, unknown][]): unknown {
  const body = frames
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('')
  const bytes = new TextEncoder().encode(body)
  let sent = false
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: () =>
          sent
            ? Promise.resolve({ value: undefined, done: true })
            : ((sent = true), Promise.resolve({ value: bytes, done: false })),
      }),
    },
  }
}

/**
 * Let the fetch promise chain settle. `fetchMentions` awaits the response and
 * then its `.json()`, so one microtask tick is not enough.
 *
 * @returns A promise resolving once the chain has run.
 */
async function flush(): Promise<void> {
  await act(async () => {
    for (let tick = 0; tick < 5; tick += 1) await Promise.resolve()
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      calls.push(url)
      const found = [{ id: 'p1', arxiv_id: null, title: 'Found' }]
      return url.includes('source=local')
        ? Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ papers: found, partial: true }),
          })
        : Promise.resolve(sseResponse([['result', { papers: found }]]))
    }),
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useMentionSuggestions', () => {
  it('does not look up a query below the minimum length, either way', () => {
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dq', 3))
    act(() => void vi.advanceTimersByTime(1000))
    expect(calls).toEqual([])
  })

  it('coalesces a burst of typing into ONE provider lookup', async () => {
    // The cost guarantee, and it is about the PAID call only. A reader typing
    // a title straight through must not spend one provider lookup per
    // character — but the cache-only pass is free and offline, so it fires on
    // every keystroke on purpose, which is what paints suggestions while they
    // are still typing.
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    for (const [text, caret] of [
      ['@atte', 5],
      ['@atten', 6],
      ['@attent', 7],
      ['@attenti', 8],
    ] as const) {
      act(() => result.current.onInput(text, caret))
      act(() => void vi.advanceTimersByTime(50)) // faster than the debounce
    }
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(paidCalls()).toHaveLength(1)
    expect(paidCalls()[0]).toContain('q=attenti') // the last thing typed, not the first
    // One free lookup per keystroke, and none of them waited for the pause.
    expect(freeCalls()).toHaveLength(4)
  })

  it('asks the cache with no debounce at all', () => {
    // Delaying a local scan would only add latency to something already
    // instant. The free pass must be in flight before any timer runs.
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dqn', 4))
    expect(freeCalls()).toHaveLength(1)
    expect(paidCalls()).toHaveLength(0)
  })

  it('sends the provider so a picked paper is in the graph’s id space', async () => {
    const { result } = renderHook(() => useMentionSuggestions('openalex'))
    act(() => result.current.onInput('@dqn', 4))
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(freeCalls()[0]).toContain('provider=openalex')
    expect(paidCalls()[0]).toContain('provider=openalex')
  })

  it('closes and stays closed after Escape, until the query changes', async () => {
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dqn', 4))
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current.open).toBe(true)
    act(() => result.current.dismiss())
    expect(result.current.open).toBe(false)
    // The same query must not reopen it — a caret move or a re-render would
    // otherwise undo the dismissal the reader just asked for.
    act(() => result.current.onInput('@dqn', 4))
    expect(result.current.open).toBe(false)
    // Typing more does.
    act(() => result.current.onInput('@dqns', 5))
    expect(result.current.active?.query).toBe('dqns')
  })

  it('wraps the keyboard selection at both ends', async () => {
    const two = [
      { id: 'a', arxiv_id: null, title: 'A' },
      { id: 'b', arxiv_id: null, title: 'B' },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('source=local')
          ? Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ papers: two, partial: true }),
            })
          : Promise.resolve(sseResponse([['result', { papers: two }]])),
      ),
    )
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dqn', 4))
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current.choice?.title).toBe('A')
    act(() => result.current.move(-1)) // up from the top wraps to the bottom
    expect(result.current.choice?.title).toBe('B')
    act(() => result.current.move(1))
    expect(result.current.choice?.title).toBe('A')
  })

  it('keeps the keyboard on the SAME PAPER when the full list re-ranks', async () => {
    // The one failure a picker must not have. The provisional list is
    // re-ranked when the ranked one lands, so a selection tracked by index
    // would end up pointing at a different paper than the reader was looking
    // at — and Enter would take the wrong one.
    let callCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        callCount += 1
        // Cache pass (plain JSON): A then B. Full pass (streamed): flipped.
        if (url.includes('source=local')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                papers: [
                  { id: 'a', arxiv_id: null, title: 'A' },
                  { id: 'b', arxiv_id: null, title: 'B' },
                ],
                partial: true,
              }),
          })
        }
        return Promise.resolve(
          sseResponse([
            ['step', { label: 'Searching Semantic Scholar' }],
            [
              'result',
              {
                papers: [
                  { id: 'b', arxiv_id: null, title: 'B' },
                  { id: 'a', arxiv_id: null, title: 'A' },
                ],
              },
            ],
          ]),
        )
      }),
    )
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@abc', 4))
    // Let the free pass land, then move the reader onto the second row.
    await flush()
    act(() => result.current.move(1))
    expect(result.current.choice?.title).toBe('B')
    // The ranked list arrives and puts B first.
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current.papers.map((paper) => paper.title)).toEqual(['B', 'A'])
    // Still on B — the row moved, the selection followed it.
    expect(result.current.choice?.title).toBe('B')
    expect(result.current.highlighted).toBe(0)
    expect(callCount).toBe(2)
  })

  it('falls back to the top row when a re-rank drops the tracked paper', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('source=local')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                papers: [{ id: 'gone', arxiv_id: null, title: 'Cached only' }],
                partial: true,
              }),
          })
        }
        return Promise.resolve(
          sseResponse([['result', { papers: [{ id: 'kept', arxiv_id: null, title: 'Ranked' }] }]]),
        )
      }),
    )
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@abc', 4))
    await flush()
    expect(result.current.choice?.title).toBe('Cached only')
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    // The tracked paper is not in the new list; Enter must still be safe.
    expect(result.current.highlighted).toBe(0)
    expect(result.current.choice?.title).toBe('Ranked')
  })

  it('surfaces each phase the server names, latest only', async () => {
    // One live line, not a phase history: a lookup that finishes in a second
    // or two turns an accumulating list of steps into noise.
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('source=local')
          ? Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ papers: [], partial: true }),
            })
          : Promise.resolve(
              sseResponse([
                ['step', { label: 'Looking in your library' }],
                ['step', { label: 'Searching Semantic Scholar' }],
                ['step', { label: 'Working out which paper “dqn” is' }],
                ['result', { papers: [{ id: 'p1', arxiv_id: null, title: 'Playing Atari' }] }],
              ]),
            ),
      ),
    )
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dqn', 4))
    await act(async () => {
      vi.advanceTimersByTime(300)
      for (let tick = 0; tick < 5; tick += 1) await Promise.resolve()
    })
    // The result landed, so the line clears — it reports work in progress,
    // and there is none left.
    expect(result.current.step).toBeNull()
    expect(result.current.papers.map((paper) => paper.title)).toEqual(['Playing Atari'])
  })

  it('clears the phase line when the query changes', async () => {
    // The previous query's label must never sit over a new query's lookup.
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('source=local')
          ? Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ papers: [], partial: true }),
            })
          : Promise.resolve(sseResponse([['step', { label: 'Searching Semantic Scholar' }]])),
      ),
    )
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dqn', 4))
    await act(async () => {
      vi.advanceTimersByTime(300)
      for (let tick = 0; tick < 5; tick += 1) await Promise.resolve()
    })
    expect(result.current.step).toBe('Searching Semantic Scholar')
    act(() => result.current.onInput('@resnet', 7))
    expect(result.current.step).toBeNull()
  })

  it('clears the phase line on reset', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('source=local')
          ? Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ papers: [], partial: true }),
            })
          : Promise.resolve(sseResponse([['step', { label: 'Searching Semantic Scholar' }]])),
      ),
    )
    const { result } = renderHook(() => useMentionSuggestions('s2'))
    act(() => result.current.onInput('@dqn', 4))
    await act(async () => {
      vi.advanceTimersByTime(300)
      for (let tick = 0; tick < 5; tick += 1) await Promise.resolve()
    })
    act(() => result.current.reset())
    expect(result.current.step).toBeNull()
  })
})
