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
 * reader's cursor: see `highlightedId`.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchMentions } from '../api'
import type { MentionPaper, Provider } from '../api'
import { MENTION_MIN_CHARS, activeMention } from './parse'
import type { ActiveMention } from './parse'

/** How long the reader must pause before a lookup fires. Long enough that
 *  typing a title straight through costs one request; short enough that the
 *  list feels like it is keeping up. */
const DEBOUNCE_MS = 250

/**
 * Drive the mention dropdown for one composer.
 *
 * @param provider The active graph provider, so a picked paper's id is in the
 *                 graph's own id space.
 * @returns The dropdown's state plus the handlers the composer wires up.
 */
export function useMentionSuggestions(provider: Provider) {
  const [active, setActive] = useState<ActiveMention | null>(null)
  const [papers, setPapers] = useState<MentionPaper[]>([])
  const [loading, setLoading] = useState(false)
  // The paper the keyboard is on, tracked by **id rather than index** — the
  // list is re-ranked under it when the full results land, and an index would
  // then point at a different paper than the one the reader was looking at.
  // Enter would take the wrong row, which is the one failure a picker must not
  // have. Null means "the top", so a fresh list starts at row 0.
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const localCtrl = useRef<AbortController | null>(null)
  const fullCtrl = useRef<AbortController | null>(null)
  // The reader pressed Escape on this exact query: stay shut until they type
  // something else, rather than reopening on the next keystroke.
  const dismissed = useRef<string | null>(null)

  /** Re-read the composer and open, update, or close the dropdown. */
  const onInput = useCallback((text: string, caret: number) => {
    const found = activeMention(text, caret)
    if (!found || found.query.length < MENTION_MIN_CHARS) {
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
    setHighlightedId(null)
    settled.current = null
    localCtrl.current?.abort()
    fullCtrl.current?.abort()
    localCtrl.current = null
    fullCtrl.current = null
  }, [])

  const query = active?.query ?? ''

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
    if (!query) return
    localCtrl.current?.abort()
    const ctrl = new AbortController()
    localCtrl.current = ctrl
    void fetchMentions(query, provider, true, ctrl.signal).then((result) => {
      if (ctrl.signal.aborted || settled.current === query) return
      setPapers(result.papers)
    })
  }, [query, provider])

  // The paid pass: only once the reader pauses.
  useEffect(() => {
    if (!query) return
    setLoading(true)
    const timer = setTimeout(() => {
      fullCtrl.current?.abort()
      const ctrl = new AbortController()
      fullCtrl.current = ctrl
      void fetchMentions(query, provider, false, ctrl.signal).then((result) => {
        if (ctrl.signal.aborted) return
        settled.current = query
        setPapers(result.papers)
        setLoading(false)
      })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [query, provider])

  // Where the keyboard selection actually is: the tracked paper's current row,
  // or the top when it isn't in the list any more (a re-rank dropped it, or
  // nothing is tracked yet).
  const highlighted = Math.max(
    0,
    papers.findIndex((paper) => paper.id === highlightedId),
  )

  /** Move the keyboard selection, wrapping at both ends. */
  const move = useCallback(
    (delta: number) => {
      if (papers.length === 0) return
      const next = (highlighted + delta + papers.length) % papers.length
      setHighlightedId(papers[next].id)
    },
    [papers, highlighted],
  )

  /** Put the keyboard selection on a row (the mouse hovering it). */
  const setHighlightedIndex = useCallback(
    (index: number) => {
      const paper = papers[index]
      if (paper) setHighlightedId(paper.id)
    },
    [papers],
  )

  return {
    /** The mention being typed, or null when the dropdown is shut. */
    active,
    /** Whether the dropdown should render: a live mention with something in it. */
    open: active !== null && (papers.length > 0 || loading),
    papers,
    loading,
    highlighted,
    /** The row Enter would accept, or null. */
    choice: papers[highlighted] ?? null,
    onInput,
    move,
    setHighlighted: setHighlightedIndex,
    dismiss,
    reset,
  }
}
