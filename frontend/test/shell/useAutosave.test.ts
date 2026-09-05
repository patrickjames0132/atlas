/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The autosave: one write per settled burst (not one per change), a row
 * created once and then overwritten in place, titling that runs once per
 * exploration, and an immediate flush when the tab goes away.
 *
 * The debounce is the load-bearing part — it is what keeps a streaming answer
 * from writing the whole blob on every chunk — so it is asserted directly with
 * fake timers rather than inferred.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

// @vitest-environment jsdom

import { configureStore } from '@reduxjs/toolkit'
import { act, cleanup, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { Provider } from 'react-redux'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '../../src/api'
import transcript, {
  chatCleared,
  conversationDropped,
  tokenAppended,
  turnStarted,
} from '../../src/store/transcript'
import { workspaceCleared } from '../../src/store/workspace'
import workspace from '../../src/store/workspace'
import { useAutosave } from '../../src/shell/useAutosave'

/** A real store with only the two slices the hook reads. */
function makeStore() {
  return configureStore({ reducer: { workspace, transcript } })
}

/** Render the hook against a live store, wrapped in its Provider. */
function setup(store: ReturnType<typeof makeStore>, onSaved = vi.fn()) {
  // eslint-disable-next-line react/no-children-prop -- createElement's third
  // argument is unavailable here: RTL hands the wrapper a `children` prop.
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(Provider, { store }, children)
  const rendered = renderHook(
    ({ sessionId }: { sessionId: string | null }) => useAutosave({ sessionId, onSaved }),
    { wrapper, initialProps: { sessionId: null as string | null } },
  )
  return { ...rendered, onSaved }
}

let saveSession: ReturnType<typeof vi.spyOn>
let titleFor: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.useFakeTimers()
  saveSession = vi
    .spyOn(api, 'saveSession')
    .mockResolvedValue({ id: 'row-1', name: 'A name' } as never)
  titleFor = vi.spyOn(api, 'titleForConversation').mockResolvedValue('A name')
})

afterEach(() => {
  // Unmount explicitly: the suite runs without test globals, so RTL's
  // auto-cleanup is never registered. A hook left mounted keeps its
  // `pagehide` listener on `window`, and the next test's event then fires
  // every previous test's autosave too — which is exactly how this file
  // first reported five writes for one flush.
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useAutosave', () => {
  it('does not save an untouched landing page', async () => {
    // An empty chat with no graph is not an exploration, and a rail full of
    // blank rows would be its own bug.
    const store = makeStore()
    setup(store)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(saveSession).not.toHaveBeenCalled()
  })

  it('writes once for a streamed answer, not once per token', async () => {
    // This is the whole reason mid-stream saves never happen, and it is worth
    // asserting against a real token stream rather than a stand-in: each
    // chunk rewrites the last turn, which pushes the timer out again, so the
    // 2s of quiet only ever arrives once the stream has settled.
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('Why attention?'))
      for (const token of ['Because ', 'it ', 'scales ', 'better.']) {
        store.dispatch(tokenAppended(token))
        await vi.advanceTimersByTimeAsync(300)
      }
    })
    expect(saveSession).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(1)
    // And what landed is the finished answer, not a half-written one.
    const body = saveSession.mock.calls[0][0] as { chat: { text: string }[] }
    expect(body.chat[1].text).toBe('Because it scales better.')
  })

  it('creates a row once, then overwrites it in place', async () => {
    // The autosave re-POSTs constantly; forking a row per write would fill
    // the rail with duplicates of one sitting.
    const store = makeStore()
    const { onSaved } = setup(store)

    await act(async () => {
      store.dispatch(turnStarted('one'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(onSaved).toHaveBeenCalledWith('row-1', 'A name', expect.any(String), false)
    expect((saveSession.mock.calls[0][0] as { id?: string }).id).toBeUndefined()

    await act(async () => {
      store.dispatch(turnStarted('two'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect((saveSession.mock.calls[1][0] as { id?: string }).id).toBe('row-1')
    // The row was adopted on the first save, so it is not announced again.
    expect(onSaved).toHaveBeenCalledTimes(1)
  })

  it('titles an exploration once, not on every save', async () => {
    // Titling costs a model call, and a name the reader may have edited must
    // not be overwritten by the next autosave two seconds later.
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('one'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    await act(async () => {
      store.dispatch(turnStarted('two'))
      await vi.advanceTimersByTimeAsync(2100)
    })

    expect(saveSession).toHaveBeenCalledTimes(2)
    expect(titleFor).toHaveBeenCalledTimes(1)
  })

  it('falls back to the reader’s own words when the titler cannot be reached', async () => {
    // A null title is a normal answer — an exploration must never fail to
    // save because a nicety was unavailable.
    titleFor.mockResolvedValue(null as never)
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('What is a diffusion model?'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect((saveSession.mock.calls[0][0] as { name: string }).name).toBe(
      'What is a diffusion model?',
    )
  })

  it('writes immediately when the tab goes away', async () => {
    // The one event that cannot wait for the debounce.
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('one'))
      await vi.advanceTimersByTimeAsync(200)
    })
    expect(saveSession).not.toHaveBeenCalled()

    await act(async () => {
      window.dispatchEvent(new Event('pagehide'))
    })
    expect(saveSession).toHaveBeenCalledTimes(1)
  })

  it('keeps working after a failed write', async () => {
    // An autosave that gave up on one bad response would silently stop
    // saving for the rest of the sitting.
    saveSession.mockRejectedValueOnce(new Error('offline'))
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('one'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    await act(async () => {
      store.dispatch(turnStarted('two'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(2)
  })
})

describe('leaving an exploration mid-save', () => {
  it('writes the exploration being LEFT, not the empty one arrived at', async () => {
    // The reported bug, in its two halves. `flush()` cannot finish
    // synchronously — it has to await a name — so `goHome`'s very next
    // statements (clear the workspace, drop the id) used to land first. The
    // request then read the *cleared* store and carried no id: a duplicate
    // empty row, and the real conversation overwritten with nothing.
    const store = makeStore()
    const { result, rerender } = setup(store)

    await act(async () => {
      store.dispatch(turnStarted('Why attention?'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(1)
    const rowId = 'row-1'

    // Now leave, exactly as `goHome` does it: flush, then immediately start a
    // new conversation and drop the id, without awaiting the flush.
    await act(async () => {
      result.current.flush()
      store.dispatch(workspaceCleared({ conversationKey: 'second' }))
      rerender({ sessionId: null })
      await vi.advanceTimersByTimeAsync(100)
    })

    const leaving = saveSession.mock.calls[1][0] as { id?: string; chat: unknown[] }
    // Overwrites the row it belongs to...
    expect(leaving.id).toBe(rowId)
    // ...with the conversation as it stood, not the cleared store.
    expect(leaving.chat).toHaveLength(2)
  })

  it('gives the next exploration its own row, not the one just left', async () => {
    // A first save creates a row. The exploration started afterwards must not
    // inherit that id, or its first save would overwrite the conversation the
    // reader just walked away from.
    const store = makeStore()
    const { result, rerender } = setup(store)

    await act(async () => {
      store.dispatch(turnStarted('one'))
      result.current.flush()
      // Leave before the POST resolves.
      store.dispatch(workspaceCleared({ conversationKey: 'second' }))
      rerender({ sessionId: null })
      await vi.advanceTimersByTimeAsync(100)
    })

    // The new exploration says something of its own and saves.
    saveSession.mockResolvedValue({ id: 'row-2', name: 'Second' } as never)
    await act(async () => {
      store.dispatch(turnStarted('a different question'))
      await vi.advanceTimersByTimeAsync(2100)
    })

    const second = saveSession.mock.calls[saveSession.mock.calls.length - 1][0] as {
      id?: string
      chat: { text: string }[]
    }
    expect(second.id).toBeUndefined()
    // And it carries its own conversation, not the previous one's.
    expect(second.chat[0].text).toBe('a different question')
  })
})

describe('reporting which conversation a row belongs to', () => {
  it('reports the pairing even when the row is created by the leaving save', async () => {
    // The row is often created by the flush that LEAVES an exploration, at
    // which point the shell has no id to pair up itself. Without the pairing
    // reported here, that exploration could not be shown as still working,
    // and reopening it would re-read from disk — discarding whatever its
    // stream wrote after the reader walked away.
    const store = makeStore()
    const { result, rerender, onSaved } = setup(store)
    const firstKey = store.getState().transcript.activeKey

    await act(async () => {
      store.dispatch(turnStarted('one'))
      result.current.flush()
      store.dispatch(workspaceCleared({ conversationKey: 'second' }))
      rerender({ sessionId: null })
      await vi.advanceTimersByTimeAsync(100)
    })

    expect(onSaved).toHaveBeenCalledWith('row-1', 'A name', firstKey, true)
  })
})

describe('deleting an exploration', () => {
  it('never lets a queued save resurrect the deleted row', async () => {
    // `save_session` upserts, so a save still holding the deleted row's id
    // would bring it straight back — reliably, for a conversation that is
    // still streaming and therefore still saving.
    const store = makeStore()
    const { result, rerender } = setup(store)
    const key = store.getState().transcript.activeKey

    await act(async () => {
      store.dispatch(turnStarted('one'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(1)

    // The reader deletes it; the conversation goes with the row.
    await act(async () => {
      store.dispatch(conversationDropped(key))
      rerender({ sessionId: null })
    })

    // Whatever its stream writes next must reach no one.
    await act(async () => {
      store.dispatch(tokenAppended('a late chunk', key))
      result.current.flush()
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(1)
  })
})

describe('reopening an existing exploration', () => {
  it('continues it instead of forking, and keeps its name', async () => {
    // Reopening mints a fresh conversation key, and a fresh key means a fresh
    // book. Without adopting what is already stored, the first save would
    // create a SECOND row and re-run the titler — renaming an exploration the
    // reader may have named by hand.
    const store = makeStore()
    const { result } = setup(store)
    const key = store.getState().transcript.activeKey

    act(() => {
      result.current.adopt(key, 'row-existing', 'A name I chose myself')
    })

    await act(async () => {
      store.dispatch(turnStarted('another question'))
      await vi.advanceTimersByTimeAsync(2100)
    })

    const body = saveSession.mock.calls[0][0] as { id?: string; name: string }
    expect(body.id).toBe('row-existing')
    expect(body.name).toBe('A name I chose myself')
    // The titler is never consulted for an exploration that already has a name.
    expect(titleFor).not.toHaveBeenCalled()
  })
})

describe('the tab going away', () => {
  it('saves without waiting on the titler, and asks to outlive the page', async () => {
    // The unload save is the one that matters most and the one most easily
    // lost: a normal fetch is cancelled with the document, and awaiting a
    // title round-trip first makes that near-certain. So the name comes from
    // the reader's own words and the request is sent `keepalive`.
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('Explain contrastive learning objectives.'))
      await vi.advanceTimersByTimeAsync(200)
    })
    expect(saveSession).not.toHaveBeenCalled()

    await act(async () => {
      window.dispatchEvent(new Event('pagehide'))
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(titleFor).not.toHaveBeenCalled()
    const [body, options] = saveSession.mock.calls[0] as [{ name: string }, { keepalive?: boolean }]
    expect(body.name).toBe('Explain contrastive learning objectives.')
    expect(options?.keepalive).toBe(true)
  })
})

describe('a save must never lose an answer', () => {
  it('refuses to write a conversation thinner than the one already stored', async () => {
    // A save is a whole-blob overwrite. An exploration merely *reopened* holds
    // whatever the restore put there, and a later blanket flush would write
    // that back over a completed answer — which is exactly how a finished
    // 3,000-character answer came back as an empty failed turn in testing.
    const store = makeStore()
    const { result } = setup(store)

    await act(async () => {
      store.dispatch(turnStarted('Why attention?'))
      store.dispatch(tokenAppended('A long, complete answer.'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(1)

    // The conversation is replaced by a thinner copy of itself.
    await act(async () => {
      store.dispatch(chatCleared())
      store.dispatch(turnStarted('Why attention?'))
      result.current.flush()
      await vi.advanceTimersByTimeAsync(2100)
    })

    // No second write: the answer on disk stands.
    expect(saveSession).toHaveBeenCalledTimes(1)
  })

  it('still writes a conversation that has grown', async () => {
    const store = makeStore()
    setup(store)

    await act(async () => {
      store.dispatch(turnStarted('one'))
      store.dispatch(tokenAppended('first answer'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    await act(async () => {
      store.dispatch(turnStarted('two'))
      store.dispatch(tokenAppended('second answer'))
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(saveSession).toHaveBeenCalledTimes(2)
  })
})
