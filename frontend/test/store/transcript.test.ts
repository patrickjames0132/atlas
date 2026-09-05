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
import workspaceReducer, { workspaceCleared } from '../../src/store/workspace'
import reducer, {
  answerFailed,
  beatAdded,
  chatCleared,
  lectureDropped,
  lectureHidden,
  lectureShown,
  lectureStarted,
  backgroundDiscovery,
  conversationDropped,
  failedTurnDropped,
  pendingDiscoveriesDrained,
  selectConversation,
  selectRunningKeys,
  streamEnded,
  streamStarted,
  traceAdded,
  tracesSettled,
  selectVisibleBeats,
  tokenAppended,
  turnStarted,
} from '../../src/store/transcript'
import type { Conversation, TranscriptState } from '../../src/store/transcript'

/** A minimal valid lecture beat; override per test. */
function makeBeat(overrides: Partial<Beat> = {}): Beat {
  return { heading: 'Beat', text: 'A beat.', node_ids: [], ...overrides }
}

/**
 * The conversation on screen.
 *
 * The slice holds several at once now — that is what lets a stream keep
 * writing to its own exploration after the reader moves on — so these tests,
 * which are about what a single conversation does, read through the active one
 * exactly as the panel's selectors do.
 *
 * @param state The slice state.
 * @returns The active conversation.
 */
function active(state: TranscriptState): Conversation {
  return selectConversation({ transcript: state })
}

/**
 * Run a sequence of actions and return the whole slice, for the tests that are
 * about more than one conversation at a time.
 *
 * @param actions The actions to play, in order.
 * @returns The resulting slice state.
 */
function playAll(...actions: Parameters<typeof reducer>[1][]): TranscriptState {
  return actions.reduce(
    (current, action) => reducer(current, action),
    reducer(undefined, { type: '@@init' }),
  )
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
    expect(active(state).activeMode).toBe('history')
    expect(active(state).lectures.history).toEqual([beat])
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
    expect(active(state).activeMode).toBe('frontier')
    expect(active(state).lectures.history).toEqual([historyBeat])
    expect(active(state).lectures.frontier).toEqual([])
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
    expect(active(state).lectures.history).toEqual([historyBeat])
    expect(active(state).lectures.frontier).toEqual([frontierBeat])
    expect(active(state).activeMode).toBe('frontier')
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
    expect(active(state).activeMode).toBe('history')
    expect(selectVisibleBeats({ transcript: state })).toEqual([historyBeat])
    expect(active(state).lectures.history).toEqual([historyBeat])
  })

  it('hides the visible lecture but keeps its cache', () => {
    const beat = makeBeat()
    let state = play(lectureStarted('history'), beatAdded({ mode: 'history', beat }))
    state = reducer(state, lectureHidden())
    expect(active(state).activeMode).toBeNull()
    expect(selectVisibleBeats({ transcript: state })).toEqual([])
    // Still cached — a later lectureShown reloads it.
    expect(active(state).lectures.history).toEqual([beat])
  })

  it('drops a partial lecture and clears it if it was visible', () => {
    const beat = makeBeat()
    let state = play(lectureStarted('history'), beatAdded({ mode: 'history', beat }))
    state = reducer(state, lectureDropped('history'))
    expect(active(state).activeMode).toBeNull()
    expect(active(state).lectures.history).toBeUndefined()
  })

  it('a drop leaves a different visible mode untouched', () => {
    const state = play(
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: makeBeat() }),
      lectureStarted('frontier'),
      beatAdded({ mode: 'frontier', beat: makeBeat({ heading: 'F' }) }),
      lectureDropped('history'),
    )
    expect(active(state).activeMode).toBe('frontier')
    expect(active(state).lectures.history).toBeUndefined()
    expect(active(state).lectures.frontier).toHaveLength(1)
  })

  it('clearing the chat leaves cached lectures intact', () => {
    const state = play(
      turnStarted('a question'),
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: makeBeat() }),
      lectureHidden(),
      chatCleared(),
    )
    expect(active(state).chat).toEqual([])
    expect(active(state).lectures.history).toHaveLength(1)
    expect(active(state).activeMode).toBeNull()
  })
})

/** A `loadGraph.fulfilled` action, as the store would dispatch it. */
function graphLoadedAction() {
  return {
    type: 'workspace/loadGraph/fulfilled',
    payload: {
      seed: { id: 'seed', arxiv_id: null, title: 'Seed' },
      nodes: [],
      edges: [],
      counts: {},
    },
    meta: { arg: { seed: 'seed' }, requestId: 'r', requestStatus: 'fulfilled' },
  } as unknown as Parameters<typeof reducer>[1]
}

describe('transcript survival across a graph load', () => {
  const graphLoaded = graphLoadedAction

  it('keeps the conversation, however the new graph was reached', () => {
    // The chat is the user's: they asked those questions, and loading another
    // graph doesn't say they're done with the answers. Clearing it is theirs
    // to do — the Clear button, or Home. A citation-seeded load and a cold
    // search are the same action here: the `fromChat` flag that once told them
    // apart is gone (v7.11.0), along with the detail panel it opened.
    const state = play(turnStarted('What is new in quantum computing?'), graphLoaded())
    // turnStarted seeds the user turn plus the assistant placeholder.
    expect(active(state).chat).toHaveLength(2)
    expect(active(state).chat[0].text).toBe('What is new in quantum computing?')
  })

  it('drops the cached lectures, which belong to the graph that is going away', () => {
    // A lecture narrates the neighborhood you built and its beats point at
    // that graph's nodes — carrying one onto a different graph would narrate
    // papers that aren't there.
    const state = play(
      lectureStarted('history'),
      beatAdded({ mode: 'history', beat: makeBeat() }),
      turnStarted('And what about DQN?'),
      graphLoaded(),
    )
    expect(active(state).lectures).toEqual({})
    expect(active(state).activeMode).toBeNull()
    expect(active(state).chat).toHaveLength(2)
  })
})

describe('workspace epoch across a graph load', () => {
  it('holds the epoch steady on a graph load', () => {
    // The shell keys the teacher panel on `epoch`, so a bump remounts it and
    // rebuilds the transcript's scroll container at the top — throwing the
    // reader back to the start of the answer they were reading. Only Home and
    // a session restore remount now.
    const loaded = workspaceReducer(undefined, graphLoadedAction())
    expect(loaded.epoch).toBe(0)
  })
})

describe('conversations run in parallel', () => {
  // The point of keying the slice: a stream started in one exploration keeps
  // writing there after the reader moves to another. Before this, the single
  // conversation meant a running answer had nowhere to write but whatever was
  // now on screen — which is why switching used to abort it outright.
  it('keeps a background answer in its own conversation', () => {
    let state = playAll(turnStarted('Why attention?'))
    const first = state.activeKey

    // The reader starts a new exploration while that answer is still coming.
    state = reducer(state, workspaceCleared({ conversationKey: 'second' }))
    expect(state.activeKey).toBe('second')

    // Tokens from the first exploration's stream, addressed to its own key.
    state = reducer(state, tokenAppended('Because it ', first))
    state = reducer(state, tokenAppended('scales.', first))

    // They landed there, and nothing reached the conversation on screen.
    expect(state.byKey[first].chat[1].text).toBe('Because it scales.')
    expect(active(state).chat).toEqual([])
  })

  it('marks a conversation as running until its last stream ends', () => {
    // The rail reads this to show which explorations are still working, and
    // the autosave reads it to know a background answer has settled.
    let state = playAll(streamStarted('ask:1'), streamStarted('lecture:history:2'))
    const key = state.activeKey
    expect(selectRunningKeys({ transcript: state })).toEqual([key])

    state = reducer(state, streamEnded('ask:1', key))
    expect(selectRunningKeys({ transcript: state })).toEqual([key])

    state = reducer(state, streamEnded('lecture:history:2', key))
    expect(selectRunningKeys({ transcript: state })).toEqual([])
  })

  it('holds a background discovery instead of dropping it on the visible graph', () => {
    // A paper found by one exploration's agent belongs to that exploration's
    // graph. The workspace only holds the active one, so an off-screen find
    // waits here rather than landing on a map it has nothing to do with.
    let state = playAll(turnStarted('Why attention?'))
    const first = state.activeKey
    state = reducer(state, workspaceCleared({ conversationKey: 'second' }))
    state = reducer(
      state,
      backgroundDiscovery({ nodes: [{ id: 'found-1' }], edges: [] } as never, first),
    )

    expect(state.byKey[first].pendingDiscoveries.nodes).toHaveLength(1)
    expect(active(state).pendingDiscoveries.nodes).toEqual([])

    // Opening that exploration takes them.
    state = reducer(state, pendingDiscoveriesDrained(first))
    expect(state.byKey[first].pendingDiscoveries.nodes).toEqual([])
  })

  it('a late write to a deleted conversation lands nowhere', () => {
    // A stream can outlive the exploration the reader deleted; it must not
    // resurrect it as a phantom row.
    let state = playAll(turnStarted('one'))
    const key = state.activeKey
    state = reducer(state, workspaceCleared({ conversationKey: 'second' }))
    state = reducer(state, conversationDropped(key))
    state = reducer(state, tokenAppended('late token', key))

    expect(state.byKey[key]).toBeUndefined()
    expect(active(state).chat).toEqual([])
  })
})

describe('an answer that never arrived', () => {
  it('records the failure on the turn, so it survives a reload', () => {
    // The panel's own error state does not outlive a reload, and a reload is
    // exactly when this is most often seen — the reader comes back to a turn
    // that shows a trace and then simply stops.
    const state = play(turnStarted('Why attention?'), answerFailed('It stopped.'))
    expect(active(state).chat[1].failed).toBe('It stopped.')
  })

  it('leaves a partial answer alone', () => {
    // Prose that did arrive is real work and reads as an answer, not a failure.
    const state = play(
      turnStarted('Why attention?'),
      tokenAppended('Because it scales'),
      answerFailed('It stopped.'),
    )
    expect(active(state).chat[1].failed).toBeUndefined()
    expect(active(state).chat[1].text).toBe('Because it scales')
  })

  it('drops the whole failed exchange when it is retried', () => {
    // Both halves go, so the retry re-runs through the ordinary path and the
    // transcript ends with one exchange rather than a graveyard of attempts.
    const state = play(
      turnStarted('first'),
      tokenAppended('an answer'),
      turnStarted('second'),
      answerFailed('It stopped.'),
      failedTurnDropped(3),
    )
    expect(active(state).chat.map((turn) => turn.text)).toEqual(['first', 'an answer'])
  })

  it('ignores a drop aimed at a turn that did answer', () => {
    const state = play(
      turnStarted('first'),
      tokenAppended('an answer'),
      failedTurnDropped(0), // a user turn, not a failed answer
    )
    expect(active(state).chat).toHaveLength(2)
  })
})

describe('a run that dies mid-step', () => {
  it('stops every chip claiming to be in progress', () => {
    // `pending` drives the spinner and only the *finished* trace clears it, so
    // a run that dies mid-step left chips spinning for a request that no
    // longer exists — under a header already back to saying "2 steps".
    const state = play(
      turnStarted('Explain diffusion models in one paragraph.'),
      traceAdded({ action: 'search', ok: true, pending: true, query: 'diffusion' }),
      traceAdded({ action: 'read', ok: true, title: 'A paper' }),
      tracesSettled(),
    )
    const trace = active(state).chat[1].trace ?? []
    expect(trace[0]).toMatchObject({ pending: false, ok: false })
    // A step that genuinely finished is untouched.
    expect(trace[1]).toMatchObject({ ok: true })
  })
})
