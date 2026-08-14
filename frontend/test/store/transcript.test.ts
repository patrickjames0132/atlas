/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The transcript slice's lecture-caching reducers: playing a mode caches its
 * beats (tagged by mode, so parallel background streams fill the right slot),
 * switching modes keeps every cache slot, and show/hide/drop move the visible
 * mode without losing (or, for a drop, deliberately losing) beats. Clearing the
 * chat leaves the lectures alone.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { Beat } from '../../src/api'
import workspaceReducer from '../../src/store/workspace'
import reducer, {
  beatAdded,
  chatCleared,
  lectureDropped,
  lectureHidden,
  lectureShown,
  lectureStarted,
  selectVisibleBeats,
  turnStarted,
} from '../../src/store/transcript'
import type { TranscriptState } from '../../src/store/transcript'

/** A minimal valid lecture beat; override per test. */
function makeBeat(overrides: Partial<Beat> = {}): Beat {
  return { heading: 'Beat', text: 'A beat.', node_ids: [], ...overrides }
}

/** Run a sequence of actions through the reducer from the initial state. */
function play(...actions: Parameters<typeof reducer>[1][]): TranscriptState {
  return actions.reduce(
    (state, action) => reducer(state, action),
    reducer(undefined, { type: '@@init' }),
  )
}

describe('transcript lecture caching', () => {
  it('caches a played lecture under its mode and shows it', () => {
    const beat = makeBeat({ heading: 'One' })
    const state = play(lectureStarted('history'), beatAdded({ mode: 'history', beat }))
    expect(state.activeMode).toBe('history')
    expect(state.lectures.history).toEqual([beat])
    expect(selectVisibleBeats({ transcript: state })).toEqual([beat])
  })

  it('routes a background beat to its own mode, not the shown one', () => {
    // Both lectures are playing; frontier is brought on screen while a history
    // beat arrives in the background — it must land in history's slot, not
    // frontier's.
    const historyBeat = makeBeat({ heading: 'H' })
    const state = play(
      lectureStarted('frontier'),
      lectureStarted('history'),
      lectureShown('frontier'),
      beatAdded({ mode: 'history', beat: historyBeat }),
    )
    expect(state.activeMode).toBe('frontier')
    expect(state.lectures.history).toEqual([historyBeat])
    expect(state.lectures.frontier).toEqual([])
  })

  it('keeps every mode cached when switching between them', () => {
    const historyBeat = makeBeat({ heading: 'H' })
    const frontierBeat = makeBeat({ heading: 'F' })
    const state = play(
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: historyBeat }),
      lectureStarted('frontier'),
      beatAdded({ mode: 'frontier', beat: frontierBeat }),
    )
    // Both lectures are cached; only the last-played is visible.
    expect(state.lectures.history).toEqual([historyBeat])
    expect(state.lectures.frontier).toEqual([frontierBeat])
    expect(state.activeMode).toBe('frontier')
  })

  it('re-shows a cached lecture without re-fetching (no beat replay)', () => {
    const historyBeat = makeBeat({ heading: 'H' })
    const frontierBeat = makeBeat({ heading: 'F' })
    let state = play(
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: historyBeat }),
      lectureStarted('frontier'),
      beatAdded({ mode: 'frontier', beat: frontierBeat }),
    )
    // Re-select history: the cached beats reappear, untouched.
    state = reducer(state, lectureShown('history'))
    expect(state.activeMode).toBe('history')
    expect(selectVisibleBeats({ transcript: state })).toEqual([historyBeat])
    expect(state.lectures.history).toEqual([historyBeat])
  })

  it('hides the visible lecture but keeps its cache', () => {
    const beat = makeBeat()
    let state = play(lectureStarted('history'), beatAdded({ mode: 'history', beat }))
    state = reducer(state, lectureHidden())
    expect(state.activeMode).toBeNull()
    expect(selectVisibleBeats({ transcript: state })).toEqual([])
    // Still cached — a later lectureShown reloads it.
    expect(state.lectures.history).toEqual([beat])
  })

  it('drops a partial lecture and clears it if it was visible', () => {
    const beat = makeBeat()
    let state = play(lectureStarted('history'), beatAdded({ mode: 'history', beat }))
    state = reducer(state, lectureDropped('history'))
    expect(state.activeMode).toBeNull()
    expect(state.lectures.history).toBeUndefined()
  })

  it('a drop leaves a different visible mode untouched', () => {
    const state = play(
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: makeBeat() }),
      lectureStarted('frontier'),
      beatAdded({ mode: 'frontier', beat: makeBeat({ heading: 'F' }) }),
      lectureDropped('history'),
    )
    expect(state.activeMode).toBe('frontier')
    expect(state.lectures.history).toBeUndefined()
    expect(state.lectures.frontier).toHaveLength(1)
  })

  it('clearing the chat leaves cached lectures intact', () => {
    const state = play(
      turnStarted('a question'),
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: makeBeat() }),
      lectureHidden(),
      chatCleared(),
    )
    expect(state.chat).toEqual([])
    expect(state.lectures.history).toHaveLength(1)
    expect(state.activeMode).toBeNull()
  })
})

/** A `loadGraph.fulfilled` action, as the store would dispatch it. */
function graphLoadedAction(fromChat: boolean) {
  return {
    type: 'workspace/loadGraph/fulfilled',
    payload: {
      seed: { id: 'seed', arxiv_id: null, title: 'Seed' },
      nodes: [],
      edges: [],
      counts: {},
    },
    meta: { arg: { seed: 'seed', fromChat }, requestId: 'r', requestStatus: 'fulfilled' },
  } as unknown as Parameters<typeof reducer>[1]
}

describe('transcript survival across a graph load', () => {
  const graphLoaded = graphLoadedAction

  it.each([
    ['seeded from a citation', true],
    ['searched cold from the header', false],
  ])('keeps the conversation when the graph was %s', (_label, fromChat) => {
    // The chat is the user's: they asked those questions, and loading another
    // graph doesn't say they're done with the answers. Clearing it is theirs
    // to do — the Clear button, or Home.
    const state = play(turnStarted('What is new in quantum computing?'), graphLoaded(fromChat))
    // turnStarted seeds the user turn plus the assistant placeholder.
    expect(state.chat).toHaveLength(2)
    expect(state.chat[0].text).toBe('What is new in quantum computing?')
  })

  it('drops the cached lectures, which belong to the graph that is going away', () => {
    // A lecture narrates the neighborhood you built and its beats point at
    // that graph's nodes — carrying one onto a different graph would narrate
    // papers that aren't there.
    const state = play(
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: makeBeat() }),
      turnStarted('And what about DQN?'),
      graphLoaded(false),
    )
    expect(state.lectures).toEqual({})
    expect(state.activeMode).toBeNull()
    expect(state.chat).toHaveLength(2)
  })
})

describe('workspace epoch across a graph load', () => {
  it.each([true, false])('holds the epoch steady on any graph load (fromChat=%s)', (fromChat) => {
    // The shell keys the teacher panel on `epoch`, so a bump remounts it and
    // rebuilds the transcript's scroll container at the top — throwing the
    // reader back to the start of the answer they were reading. Only Home and
    // a session restore remount now.
    const loaded = workspaceReducer(undefined, graphLoadedAction(fromChat))
    expect(loaded.epoch).toBe(0)
  })
})
