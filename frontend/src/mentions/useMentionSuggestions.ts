/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention typeahead's engine: watch what is being typed, look up
 * candidates, and hold the keyboard selection.
 *
 * Everything here is about not making the reader wait or pay, and those pull
 * in opposite directions — so the two sources behind a lookup are fired on
 * different clocks.
 *
 * **The free half runs on every keystroke.** A cache-only lookup is a local
 * scan: no provider, no network beyond localhost, milliseconds. Debouncing it
 * would only add latency to something already instant, so suggestions paint
 * while the reader is still typing.
 *
 * **The paid half waits for a pause** (`DEBOUNCE_MS`), fires only past the
 * backend's minimum length, and aborts the request before it — so typing a
 * title straight through costs one provider lookup, not one per character. The
 * backend's day-cache absorbs the repeats.
 *
 * When the full list lands it **replaces** the provisional one, relevance-ranked
 * across both sources. One thing it must not do is move the row under the
 * reader's cursor: see `highlightedKey`.
 *
 * **Sibling threads are rows too**, listed above the papers. They are the
 * other discussions in the current exploration — a local list of a few
 * titles, filtered here with no request at all — so they show from the first
 * character, before the paper lookups are even allowed to fire. Typing `@`
 * alone lists every one of them, which is how a reader finds out that a
 * discussion can be mentioned at all.
 *
 * **Nothing is selected until the reader selects it.** The dropdown used to
 * pre-highlight its top row, so Enter on an untouched list spliced in a paper
 * the reader had only been shown — and Enter again, on the bare mention that
 * left behind, seeded the graph. Now a row is only chosen by arrowing onto it
 * or hovering it; Enter with no row chosen sends the message as typed, and
 * `@words` alone goes to the paper scout the way it did before the dropdown
 * existed.
 *
 * The full pass streams its phases, and `step` holds the latest — the dropdown
 * shows one live line naming what it is waiting on ("Searching Semantic
 * Scholar", "Working out which paper “dqn” is") rather than "Searching…" for
 * all three. Each label supersedes the last: a phase history would be noise
 * for a lookup this short.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCachedMentions, streamMentions } from '../api'
import type { MentionPaper, Provider } from '../api'
import { MENTION_MIN_CHARS, activeMention, threadMatches } from './parse'
import type { ActiveMention, MentionChoice, MentionThread } from './parse'

/** How long the reader must pause before a lookup fires. Long enough that
 *  typing a title straight through costs one request; short enough that the
 *  list feels like it is keeping up. */
const DEBOUNCE_MS = 250

/**
 * The key a row is tracked by across re-ranks: its kind and its id, so a
 * thread and a paper that happen to share an id can never be confused.
 *
 * @param choice The row.
 * @returns Its tracking key.
 */
function rowKey(choice: MentionChoice): string {
  return choice.kind === 'paper' ? `paper:${choice.paper.id}` : `thread:${choice.thread.id}`
}

/**
 * Drive the mention dropdown for one composer.
 *
 * @param provider The active graph provider, so a picked paper's id is in the
 *                 graph's own id space.
 * @param threads  The other threads in the current exploration, offered as
 *                 rows above the papers.
 * @returns The dropdown's state plus the handlers the composer wires up.
 */
export function useMentionSuggestions(provider: Provider, threads: MentionThread[] = []) {
  const [active, setActive] = useState<ActiveMention | null>(null)
  const [papers, setPapers] = useState<MentionPaper[]>([])
  const [loading, setLoading] = useState(false)
  // The phase the full pass is in, in the server's own reader-facing words.
  // Null when nothing is running or the result has landed.
  const [step, setStep] = useState<string | null>(null)
  // The row the keyboard is on, tracked by **key rather than index** — the
  // list is re-ranked under it when the full results land, and an index would
  // then point at a different paper than the one the reader was looking at.
  // Enter would take the wrong row, which is the one failure a picker must not
  // have. Null means **no row**: a fresh list has nothing selected, and Enter
  // on it sends the message rather than picking on the reader's behalf.
  const [highlightedKey, setHighlightedKey] = useState<string | null>(null)
  const localCtrl = useRef<AbortController | null>(null)
  const fullCtrl = useRef<AbortController | null>(null)
  // The reader pressed Escape on this exact query: stay shut until they type
  // something else, rather than reopening on the next keystroke.
  const dismissed = useRef<string | null>(null)

  /** Re-read the composer and open, update, or close the dropdown.
   *  `completed` is the draft's already-picked mention texts, which end a
   *  mention rather than extending it (see `activeMention`). */
  const onInput = useCallback((text: string, caret: number, completed?: Iterable<string>) => {
    const found = activeMention(text, caret, completed)
    if (!found) {
      setActive(null)
      setPapers([])
      return
    }
    if (dismissed.current === found.query) return
    dismissed.current = null
    setActive(found)
  }, [])

  /** Close the dropdown and remember not to reopen on this query. */
  const dismiss = useCallback(() => {
    dismissed.current = active?.query ?? null
    setActive(null)
    setPapers([])
  }, [active])

  /** Close it outright — after a pick, or a send. */
  const reset = useCallback(() => {
    dismissed.current = null
    setActive(null)
    setPapers([])
    setLoading(false)
    setStep(null)
    setHighlightedKey(null)
    settled.current = null
    localCtrl.current?.abort()
    fullCtrl.current?.abort()
    localCtrl.current = null
    fullCtrl.current = null
  }, [])

  const query = active?.query ?? ''
  // The threads show for any live mention; the paper lookups below wait for
  // the backend's minimum length, and a shorter query holds no papers at all.
  const matchedThreads = active ? threadMatches(threads, query) : []
  const lookup = query.length >= MENTION_MIN_CHARS ? query : ''

  // The query whose FULL results we already hold. Each new query aborts both
  // requests before it, so a stale response can't arrive — but within one
  // query the two can finish out of order (a slow cache scan against a
  // day-cached provider hit), and the provisional list must never overwrite
  // the ranked one. This is that fact, stated rather than inferred from
  // whether a spinner is up.
  const settled = useRef<string | null>(null)

  // The free pass: no debounce, because a cache scan is already instant and
  // delaying it would only make the dropdown feel slower than it is.
  useEffect(() => {
    if (!lookup) {
      // Too short to look up: whatever papers a longer query left behind are
      // stale, and the phase label with them — and a lookup still in flight
      // for that longer query must not land on this one.
      localCtrl.current?.abort()
      fullCtrl.current?.abort()
      setPapers((previous) => (previous.length ? [] : previous))
      setStep(null)
      return
    }
    // A new query: the previous one's phase label must not sit over it. Done
    // here rather than in `onInput`, which is a stable callback and would
    // read a stale `active` to compare against.
    setStep(null)
    localCtrl.current?.abort()
    const ctrl = new AbortController()
    localCtrl.current = ctrl
    void fetchCachedMentions(lookup, provider, ctrl.signal).then((result) => {
      if (ctrl.signal.aborted || settled.current === lookup) return
      setPapers(result.papers)
    })
  }, [lookup, provider])

  // The paid pass: only once the reader pauses.
  useEffect(() => {
    if (!lookup) {
      setLoading(false)
      return
    }
    setLoading(true)
    const timer = setTimeout(() => {
      fullCtrl.current?.abort()
      const ctrl = new AbortController()
      fullCtrl.current = ctrl
      void streamMentions(lookup, provider, {
        signal: ctrl.signal,
        onStep: (label) => {
          if (!ctrl.signal.aborted) setStep(label)
        },
        onResult: (found) => {
          if (ctrl.signal.aborted) return
          settled.current = lookup
          setPapers(found)
          setStep(null)
          setLoading(false)
        },
      })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [lookup, provider])

  // Every row the keyboard can reach, threads first: they are the reader's
  // own, few, and already on screen in the rail, so they belong above a list
  // of strangers' papers that is still being fetched.
  const rows: MentionChoice[] = [
    ...matchedThreads.map((thread): MentionChoice => ({ kind: 'thread', thread })),
    ...papers.map((paper): MentionChoice => ({ kind: 'paper', paper })),
  ]

  // Where the keyboard selection actually is: the tracked row's current
  // index, or -1 — nothing selected — when it isn't in the list any more (a
  // re-rank dropped it, or nothing was ever chosen). -1 rather than the top,
  // because a selection the reader didn't make is exactly what Enter must
  // not act on.
  const highlighted = rows.findIndex((row) => rowKey(row) === highlightedKey)

  /** Move the keyboard selection, wrapping at both ends. From nothing
   *  selected, down goes to the first row and up to the last. */
  const move = useCallback(
    (delta: number) => {
      if (rows.length === 0) return
      const next =
        highlighted === -1
          ? delta > 0
            ? 0
            : rows.length - 1
          : (highlighted + delta + rows.length) % rows.length
      setHighlightedKey(rowKey(rows[next]))
    },
    [rows, highlighted],
  )

  /** Put the keyboard selection on a row (the mouse hovering it). */
  const setHighlightedIndex = useCallback(
    (index: number) => {
      const row = rows[index]
      if (row) setHighlightedKey(rowKey(row))
    },
    [rows],
  )

  return {
    /** The mention being typed, or null when the dropdown is shut. */
    active,
    /** Whether the dropdown should render: a live mention with something in it. */
    open: active !== null && (rows.length > 0 || loading),
    /** The sibling threads matching the query, shown above the papers. */
    threads: matchedThreads,
    papers,
    loading,
    /** What the full pass is doing right now, or null. */
    step,
    /** The index of the selected row across threads then papers, or -1. */
    highlighted,
    /** The row Enter would accept, or null when the reader hasn't chosen one. */
    choice: rows[highlighted] ?? null,
    onInput,
    move,
    setHighlighted: setHighlightedIndex,
    dismiss,
    reset,
  }
}
