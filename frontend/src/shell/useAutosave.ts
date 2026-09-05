/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The autosave: every exploration saves itself, so there is no Save button.
 *
 * Saving used to be a manual act — a ＋ in the rail — and forgetting it lost
 * the sitting on tab close. This watches the workspace and the transcript and
 * writes the same blob the button used to write, without being asked.
 *
 * **It reports nothing to the UI, deliberately** (Patrick, 2026-08-29). The
 * first cut put a "Saving… / Saved" label on the open row to replace the
 * button's lost reassurance; in the app it read as chatter on a rail that is
 * otherwise quiet. The row appearing in the list is the whole signal.
 *
 * **It fires on settled events, not on every change.** A save is a whole-blob
 * POST, so writing on each streamed chunk or each expanded node would be a
 * write per keystroke. A burst of changes instead collapses into one POST via
 * a debounce — which is also, on its own, what keeps mid-stream saves from
 * happening at all (see the commit-points effect). The one thing that cannot
 * wait for a debounce is the tab going away, so `pagehide` and a hidden
 * `visibilitychange` flush immediately, mid-stream or not: a partial answer
 * on disk beats an empty rail row.
 *
 * **What counts as one exploration** is decided by the caller (`Atlas.tsx`),
 * which owns the id: a row begins at ✎ New Exploration or on opening a saved
 * one, and re-seeding inside it continues that same row. This hook only
 * writes whatever id it is handed.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef } from 'react'

import { saveSession, titleForConversation } from '../api'
import type { ChatMsg, SaveSessionBody } from '../api'
import { useAppSelector, useAppStore } from '../store'
import { selectConversation, selectRunningKeys } from '../store/transcript'
import { buildSaveBody, settleInFlight } from '../store/workspace'

/** How long a burst of changes collapses before one POST goes out. */
const DEBOUNCE_MS = 2000

/**
 * How many opening turns the titler reads. A name comes from what the
 * conversation opened with; the server truncates too, this just avoids
 * shipping a long transcript to be thrown away.
 */
const TITLE_TURNS = 4

/** Chat turns needed before an exploration is worth naming and storing. */
const MIN_TURNS_TO_SAVE = 1

/**
 * How much prose a conversation holds — the measure a save must not shrink.
 *
 * Counting characters rather than turns because the loss that matters is an
 * *answer* disappearing: the turn count is identical before and after a
 * completed answer is replaced by an empty one.
 *
 * @param chat The turns to measure.
 * @returns Total characters of message text.
 */
function proseLength(chat: ChatMsg[]): number {
  return chat.reduce((total, turn) => total + (turn.text?.length ?? 0), 0)
}

export interface AutosaveOptions {
  /** The row being written, or null to create one on the next save. */
  sessionId: string | null
  /**
   * Called with the id the server assigned, when a save creates a row.
   *
   * Carries the **conversation key** that row belongs to, because this is the
   * only place that reliably knows both. The shell needs the pairing to say
   * which explorations are still working and to re-show a live one instead of
   * re-reading it from disk — and the row is often created by the save that
   * *leaves* an exploration, at which point the shell has no id to pair up.
   *
   * `background` is true when the row belongs to an exploration the reader is
   * *not* looking at — a conversation that kept streaming after they moved
   * on. The rail still has to list it, but the selection must not jump to it.
   *
   * **Must be referentially stable** (`useCallback`): it feeds the debounced
   * effect's dependency list, so a fresh identity each render restarts the
   * timer each render and nothing is ever saved.
   */
  onSaved: (id: string, name: string, conversationKey: string, background: boolean) => void
}

/**
 * Save the current exploration automatically.
 *
 * @param options Which row to write, and how to report back (see
 *   {@link AutosaveOptions}).
 * @returns A `flush` callback that writes immediately, for callers that need
 *   the row on disk before doing something else (leaving the exploration).
 */
export function useAutosave({ sessionId, onSaved }: AutosaveOptions): {
  flush: () => void
  adopt: (conversationKey: string, rowId: string, name: string) => void
} {
  const store = useAppStore()
  const graph = useAppSelector((state) => state.workspace.graph)
  const seedRef = useAppSelector((state) => state.workspace.seedRef)
  const discoveredNodes = useAppSelector((state) => state.workspace.discoveredNodes)
  const layout = useAppSelector((state) => state.workspace.layout)
  const activeKey = useAppSelector((state) => state.transcript.activeKey)
  const conversation = useAppSelector(selectConversation)
  const chat = conversation.chat
  const lectures = conversation.lectures
  // Which conversations still have a stream running. A background one that
  // has just gone quiet has finished an answer nobody is looking at, and that
  // answer has to reach disk — see the settle effect below.
  const runningKeys = useAppSelector(selectRunningKeys)

  /**
   * Per-conversation bookkeeping: the row each one writes to, the name it was
   * given, and the last body written for it.
   *
   * Keyed rather than single-valued because several explorations are live at
   * once now. The stored **body** is what lets a background conversation be
   * saved at all: `buildSaveBody` reads the workspace, and the workspace only
   * holds the *active* exploration's graph — so a background save reuses the
   * graph reference from that conversation's last write and swaps in its new
   * chat, rather than inventing one or (worse) borrowing the graph on screen.
   */
  const booksRef = useRef(
    new Map<string, { rowId: string | null; name: string | null; body: SaveSessionBody | null }>(),
  )
  /** The bookkeeping entry for a conversation, created on first use. */
  const bookFor = useCallback((key: string) => {
    let book = booksRef.current.get(key)
    if (!book) {
      book = { rowId: null, name: null, body: null }
      booksRef.current.set(key, book)
    }
    return book
  }, [])

  const timerRef = useRef<number | null>(null)
  const inFlightRef = useRef(false)
  // Set when a save is asked for while one is already in flight, so the last
  // state always reaches disk instead of being dropped by the overlap guard.
  const dirtyRef = useRef(false)
  const activeKeyRef = useRef(activeKey)

  // The caller owns the row id for the exploration on screen (it is what the
  // rail marks), so adopt it into that conversation's book.
  useEffect(() => {
    activeKeyRef.current = activeKey
    if (sessionId) bookFor(activeKey).rowId = sessionId
  }, [activeKey, sessionId, bookFor])

  /** The name to save under, generating one the first time it's needed. */
  const resolveName = useCallback(
    async (key: string, turns: ChatMsg[], local = false): Promise<string> => {
      const book = bookFor(key)
      if (book.name) return book.name
      // The reader's own words: always available, costs nothing, and the
      // fallback if the titler can't be reached.
      const firstAsk = turns.find((turn) => turn.role === 'user')?.text?.trim() ?? ''
      const fallback = firstAsk.length > 60 ? `${firstAsk.slice(0, 57)}…` : firstAsk
      // On the unload path there is no time for a round-trip — the page is
      // being torn down, and awaiting one is how the last save came to be
      // cancelled and lost. The reader's own words are always available, and
      // the name can be improved (or edited) next time.
      if (local) return (book.name = fallback || 'Untitled exploration')
      const generated = await titleForConversation(
        turns
          .slice(0, TITLE_TURNS)
          .map((turn) => turn.text ?? '')
          .filter(Boolean),
      )
      book.name = generated || fallback || 'Untitled exploration'
      return book.name
    },
    [bookFor],
  )

  /**
   * Write one conversation.
   *
   * @param key The conversation to save. When it is not the active one the
   *   body comes from its last write (the workspace holds someone else's
   *   graph), so a background answer is stored against its own exploration.
   */
  const saveConversation = useCallback(
    async (key: string, unloading = false) => {
      const state = store.getState()
      const target = state.transcript.byKey[key]
      if (!target) return
      const book = bookFor(key)
      const isActive = state.transcript.activeKey === key
      // **Captured before the first await**, all of it: leaving an exploration
      // clears the workspace and drops the id on the very next statement, so
      // anything read afterwards would describe the exploration arrived at.
      const targetId = book.rowId
      const turns = target.chat
      if (turns.length < MIN_TURNS_TO_SAVE && !(isActive && state.workspace.graph)) return
      // **Never write less than was written before.** A save is a whole-blob
      // overwrite, so a conversation whose in-memory copy is thinner than the
      // one already on disk would destroy the difference — and that is not
      // hypothetical: an exploration merely *reopened* holds whatever the
      // restore put there, which a later blanket flush would then write back
      // over a completed answer. Prose is the thing worth protecting, so the
      // comparison is on how much of it there is.
      if (book.body && proseLength(turns) < proseLength(book.body.chat)) return
      const name = await resolveName(key, turns, unloading)
      const body: SaveSessionBody = isActive
        ? buildSaveBody(state, name, targetId ?? undefined)
        : {
            // A background conversation keeps the graph reference it was last
            // saved with; only what the stream produced is new.
            ...(book.body ?? { layout: 'timeline' as const, chat: [] }),
            name,
            id: targetId ?? undefined,
            chat: settleInFlight(turns),
            lectures: target.lectures,
            lectureSources: target.lectureSources,
            activeMode: target.activeMode,
          }
      // Deleting an exploration removes its conversation; a save queued
      // before that must not go out, or the upsert would **recreate the row
      // the reader just deleted** — with whatever the stream wrote next.
      if (!store.getState().transcript.byKey[key]) return
      const saved = await saveSession(body, { keepalive: unloading })
      book.body = body
      if (!targetId) {
        book.rowId = saved.id
        // `background` decides only whether the reader's selection moves; the
        // pairing is reported either way, because the shell needs it for every
        // exploration, not just the visible one.
        onSaved(saved.id, saved.name, key, store.getState().transcript.activeKey !== key)
      }
    },
    [bookFor, onSaved, resolveName, store],
  )

  const save = useCallback(async () => {
    if (inFlightRef.current) {
      dirtyRef.current = true
      return
    }
    inFlightRef.current = true
    try {
      await saveConversation(activeKeyRef.current)
    } catch {
      // An autosave that shouts on failure would be worse than one that
      // retries quietly: the next settled event writes the same state again.
    } finally {
      inFlightRef.current = false
      if (dirtyRef.current) {
        dirtyRef.current = false
        void save()
      }
    }
  }, [saveConversation])

  /**
   * Take on an exploration that already exists on disk.
   *
   * Reopening one mints a fresh conversation key, and a fresh key means a
   * fresh book — with no row and no name. Left alone, its first save would
   * create a *second* row and re-run the titler, quietly renaming an
   * exploration the reader may have named themselves. Seeding the book with
   * what is already stored is what makes a reopened exploration continue
   * rather than fork.
   *
   * @param conversationKey The key the restore minted.
   * @param rowId           The exploration's existing row.
   * @param name            The name it is already stored under.
   */
  const adopt = useCallback(
    (conversationKey: string, rowId: string, name: string) => {
      const book = bookFor(conversationKey)
      book.rowId = rowId
      book.name = name
    },
    [bookFor],
  )

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    void save()
  }, [save])

  // The commit points.
  //
  // **The debounce is what skips mid-stream saves**, and it does it without
  // needing to know a stream is running — which matters, because that flag is
  // component-local to `useConversation` and never reaches the store. A
  // streaming answer rewrites the last chat turn on every chunk, so each chunk
  // pushes the timer out again; the 2s of quiet only ever arrives once the
  // stream has settled. One write per turn, not one per token, for free.
  useEffect(() => {
    if (chat.length < MIN_TURNS_TO_SAVE && !graph) return
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      void save()
    }, DEBOUNCE_MS)
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    }
    // `save` IS a dependency, and must be: it closes over the chat it will
    // write, so an effect holding an older `save` would persist stale state.
    // The cost is that `onSaved` has to be stable — an unmemoized callback
    // changes `save`'s identity every render, which restarts the timer every
    // render and means the debounce never fires at all. The caller memoizes
    // it; see the interface docs.
  }, [chat, graph, seedRef, discoveredNodes, layout, lectures, save])

  // A deleted exploration must be forgotten here too. The book holds its row
  // id, and a save that still had one would re-POST it — and `save_session`
  // upserts, so the row would come back from the dead.
  const liveKeys = useAppSelector((state) => state.transcript.byKey)
  useEffect(() => {
    for (const key of booksRef.current.keys()) {
      if (!liveKeys[key]) booksRef.current.delete(key)
    }
  }, [liveKeys])

  // A background conversation that has just gone quiet finished an answer
  // nobody was watching. Nothing else will write it — the debounce only ever
  // saves what is on screen — so it is saved here, once, as it settles.
  const previouslyRunning = useRef<string[]>([])
  useEffect(() => {
    const settled = previouslyRunning.current.filter(
      (key) => !runningKeys.includes(key) && key !== activeKeyRef.current,
    )
    previouslyRunning.current = runningKeys
    for (const key of settled) void saveConversation(key).catch(() => {})
  }, [runningKeys, saveConversation])

  // The tab going away is the one event that cannot wait for a debounce, and
  // it has to take every live conversation, not just the visible one.
  useEffect(() => {
    const flushAll = () => {
      // Every live conversation, on the unload path — no titler round-trip and
      // a keepalive request, so the last save actually lands.
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
      // Only conversations this tab has actually written. One merely opened
      // for reading has a book with no body, and flushing it would push this
      // tab's copy over whatever has happened to that exploration since.
      for (const key of Object.keys(store.getState().transcript.byKey)) {
        if (key === activeKeyRef.current || booksRef.current.get(key)?.body) {
          void saveConversation(key, true).catch(() => {})
        }
      }
    }
    const onHide = () => {
      if (document.visibilityState === 'hidden') flushAll()
    }
    window.addEventListener('pagehide', flushAll)
    document.addEventListener('visibilitychange', onHide)
    return () => {
      window.removeEventListener('pagehide', flushAll)
      document.removeEventListener('visibilitychange', onHide)
    }
  }, [saveConversation, store])

  return { flush, adopt }
}
