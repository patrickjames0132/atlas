/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The conversation engine: drives the three agent streams and dispatches
 * their events into the store (transcript, highlights, discoveries), while
 * owning the panel-local run state — which lecture modes are loading, the
 * active beat/answer, the stream error, the per-stream abort controllers (one
 * per in-flight lecture plus one for the chat, so they cancel independently
 * and run in parallel), and the backend session id.
 *
 * The split of responsibilities is the Phase 6 state directive: everything
 * the canvas or Save needs goes through the store; everything only this
 * panel renders stays right here.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { LECTURE_TITLES, streamAsk, streamAskSources, streamLecture } from '../api'
import type {
  Beat,
  GraphNode,
  HistoryTurn,
  LectureMode,
  PlayedLecture,
  Provider,
  SearchOptions,
} from '../api'
import { useAppDispatch, useAppSelector, useAppStore } from '../store'
import { highlightSet, selectHighlightSet } from '../store/highlight'
import {
  answerFailed,
  backgroundDiscovery,
  beatAdded,
  chatCleared,
  citedSet,
  figureAdded,
  lectureDropped,
  lectureHidden,
  lectureShown,
  lectureStarted,
  graphRefsSet,
  sourceRefsSet,
  provenanceSet,
  paperRefsSet,
  failedTurnDropped,
  lectureSourcesSet,
  selectConversation,
  streamEnded,
  streamStarted,
  tracesSettled,
  tokenAppended,
  traceAdded,
  turnStarted,
} from '../store/transcript'
import {
  discoveryMerged,
  loadGraph,
  selectGraphEdges,
  selectGroundingNodes,
  selectSeedNode,
  selectWorkspaceNodeIds,
} from '../store/workspace'

/**
 * Mint a fresh chat-session id (keys the backend's per-conversation history).
 *
 * @returns A UUID, or a random-digits fallback off-HTTPS.
 */
const newSessionId = () => (crypto.randomUUID?.() as string) || String(Math.random()).slice(2)

/** An inline citation marker in answer prose: a single index (`[7]`) or a
 *  combined list (`[14, 29]`). Group 1 holds the digits and separators; split
 *  on `REF_SEPARATOR` for the individual indices. Kept in step with the same
 *  pattern in `remarkCite` (render) and the backend's `graph_refs_from_text`. */
const REF_MARKER = /\[(\d+(?:[\s,]+\d+)*)\]/g
/** The separator between indices inside a combined marker (comma and/or space). */
const REF_SEPARATOR = /[\s,]+/

/**
 * Resolve the `[n]` markers an answer actually used into a compact
 * `index → node-id` map, given the numbered grounding list `[n]` indexes into
 * (1-based, matching the backend's `node_lines`). Only referenced indices that
 * land on a real node are kept, so the map stays small and reload-safe.
 *
 * @param text        The finished answer prose.
 * @param numberedIds The grounding list's node ids, in numbered order.
 * @returns The marker → node-id map for the turn's clickable chips.
 */
function resolveGraphRefs(text: string, numberedIds: string[]): Record<string, string> {
  const graphRefs: Record<string, string> = {}
  for (const match of text.matchAll(REF_MARKER)) {
    // A combined marker (`[14, 29]`) resolves each of its indices, so every
    // number in it becomes clickable.
    for (const token of match[1].split(REF_SEPARATOR)) {
      const index = Number(token)
      const nodeId = numberedIds[index - 1]
      if (nodeId) graphRefs[token] = nodeId
    }
  }
  return graphRefs
}

/**
 * Turn the chat bar's filters into the wire fields the ask routes take.
 *
 * Omitted entirely when nothing is filtered, so an unfiltered question sends
 * exactly the body it always did — the backend's own default is "no filter",
 * and spelling that out as explicit nulls would only be noise.
 *
 * @param filters The bar's active filters, or undefined when it has none.
 * @returns The `year_from` / `year_to` / `fields` fields to spread into the
 *          request body (an empty object when nothing is set).
 */
function askFilters(filters?: SearchOptions) {
  if (!filters) return {}
  const { yearFrom, yearTo, fields } = filters
  return {
    ...(yearFrom != null ? { year_from: yearFrom } : {}),
    ...(yearTo != null ? { year_to: yearTo } : {}),
    ...(fields.length ? { fields } : {}),
  }
}

/**
 * Own the assistant's stream engine: run the lecture/ask/library streams,
 * dispatch their events into the store, and expose the panel's run state.
 *
 * @returns The run state + the lecture/ask/clear entry points.
 */
export function useConversation() {
  const dispatch = useAppDispatch()
  // Read synchronously when retrying: the history to resend is whatever is
  // on screen at the moment of the click, not at the last render.
  const store = useAppStore()
  const seedNode = useAppSelector(selectSeedNode)
  const groundingNodes = useAppSelector(selectGroundingNodes)
  const lectureEdges = useAppSelector(selectGraphEdges)
  // Which cited papers are still reachable — a transcript now outlives the
  // graph it was written against, so `[n]` chips are checked before they
  // render as controls.
  const onGraphIds = useAppSelector(selectWorkspaceNodeIds)
  // The selected provider — so the researcher's expand/search/hydrate use the
  // same backend (and id space) as the graph the question is grounded in, and
  // so the graph-free chat searches the backend the dropdown actually names.
  const provider = useAppSelector((state) => state.workspace.provider)
  const chatLength = useAppSelector((state) => selectConversation(state).chat.length)
  const lectures = useAppSelector((state) => selectConversation(state).lectures)
  const activeMode = useAppSelector((state) => selectConversation(state).activeMode)
  // The conversation a stream belongs to, captured when the stream STARTS and
  // passed to every dispatch it makes. This is what lets an answer keep
  // running after the reader moves to another exploration: its writes are
  // addressed to the conversation that asked the question, not to whichever
  // one happens to be on screen when a chunk lands. Read from a ref, never
  // from the render closure, so a stream started before a switch still sees
  // its own key afterwards.
  const activeKey = useAppSelector((state) => state.transcript.activeKey)
  const activeKeyRef = useRef(activeKey)
  useEffect(() => {
    activeKeyRef.current = activeKey
  }, [activeKey])

  // Which lecture modes are streaming right now. Lectures load independently
  // and in parallel — a lecture can keep generating in the background while
  // you deselect it, ask a question, or start another one — so this is a set,
  // not one "teaching" flag. Drives each button's hopping-dots indicator.
  const [loadingModes, setLoadingModes] = useState<LectureMode[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Which lecture beat / chat answer is "active" (its papers lit on the
  // graph). Panel-local UI state — only the RESULTING highlight ids are
  // global. At most one of the two is non-null.
  const [activeBeat, setActiveBeat] = useState<number | null>(null)
  const [activeChat, setActiveChat] = useState<number | null>(null)
  // The node currently spotlit by a clicked inline `[n]` — click the same one
  // again to clear it (like re-clicking an active beat).
  const [activeRef, setActiveRef] = useState<string | null>(null)

  // A per-stream id, so `running` can hold several at once (an answer and two
  // lectures) and each removes only its own entry when it finishes.
  const streamCounter = useRef(0)
  const nextStreamId = useCallback(() => {
    streamCounter.current += 1
    return String(streamCounter.current)
  }, [])

  // One AbortController per in-flight lecture (keyed by mode) plus one for the
  // Q&A/library stream — each cancels independently, so stopping or clearing
  // one never disturbs the others running in parallel.
  const lectureCtrls = useRef(new Map<LectureMode, AbortController>())
  const askCtrl = useRef<AbortController | null>(null)
  // The mode currently on screen, mirrored into a ref so a streaming lecture's
  // onBeat can tell whether it should drive the live highlight (only the shown
  // lecture lights the graph as its beats arrive; background ones stay quiet).
  const shownModeRef = useRef<LectureMode | null>(activeMode)
  useEffect(() => {
    shownModeRef.current = activeMode
  }, [activeMode])

  // **Nothing is aborted when the reader switches exploration.** This used to
  // abort every in-flight stream on unmount — the panel remounts on the
  // workspace epoch — because a single-conversation store gave a running
  // answer nowhere to write but whatever was now on screen. Conversations are
  // keyed now and every stream addresses its own, so leaving one running is
  // safe and is the point: you can ask something slow, go read another
  // exploration, and come back to a finished answer.
  //
  // The controllers still exist for the things that *should* stop a stream —
  // Stop, Clear, and asking a new question, which supersedes the last.
  //
  // The one case that still has to abort is a **re-seed inside the same
  // conversation**: the graph under the answer is being replaced, so its
  // discoveries would land on a neighbourhood the question was never about.
  // Keying can't help there — it really is the same conversation — so the
  // guard is kept, narrowed to that case. A seed change that comes *with* a
  // conversation change is just a switch, and must not abort.
  const seedAtMount = useRef(seedNode?.id ?? null)
  const keyAtMount = useRef(activeKey)
  useEffect(() => {
    const seedId = seedNode?.id ?? null
    // Read both previous values BEFORE writing either, or the comparison is
    // always against what was just stored and the guard never fires.
    const previousSeed = seedAtMount.current
    const sameConversation = keyAtMount.current === activeKey
    seedAtMount.current = seedId
    keyAtMount.current = activeKey
    if (!sameConversation || seedId === previousSeed) return
    askCtrl.current?.abort()
    lectureCtrls.current.forEach((ctrl) => ctrl.abort())
    lectureCtrls.current.clear()
  }, [seedNode, activeKey])
  // Keys the backend's per-chat history; clearing the chat mints a new one so
  // the fresh conversation also detaches from server-side context.
  const sessionId = useRef(newSessionId())
  // The chat index the in-flight answer streams into (for onCited's active
  // marking) — chat.length + 1 at turn start (user turn, then assistant).
  const askIdxRef = useRef(0)

  const highlight = useCallback((ids: string[]) => dispatch(highlightSet(ids)), [dispatch])

  // The active beat/answer/ref marks are UI echoes of the GLOBAL highlight —
  // so when that highlight empties from anywhere else (the graph's Esc /
  // clear-all, a graph reload, a session restore), un-mark here too. Without
  // this, the glow died but the panel kept a beat looking lit.
  const highlightIds = useAppSelector(selectHighlightSet)
  useEffect(() => {
    if (highlightIds.size === 0) {
      setActiveBeat(null)
      setActiveChat(null)
      setActiveRef(null)
    }
  }, [highlightIds])

  /** Click a beat: light its papers; click the active one again to clear. */
  const onBeatClick = useCallback(
    (index: number, beat: Beat) => {
      const off = activeBeat === index
      setActiveBeat(off ? null : index)
      setActiveChat(null)
      setActiveRef(null)
      highlight(off ? [] : beat.node_ids)
    },
    [activeBeat, highlight],
  )

  /** Click an answer: re-light the papers it was grounded in. */
  const onChatClick = useCallback(
    (index: number, cited: string[]) => {
      const off = activeChat === index
      setActiveChat(off ? null : index)
      setActiveBeat(null)
      setActiveRef(null)
      highlight(off ? [] : cited)
    },
    [activeChat, highlight],
  )

  /** Click an inline `[n]` reference: spotlight just that one paper on the
   * graph (a targeted glow, distinct from the whole-answer re-light). Click the
   * same marker again to clear the highlight and restore the plain graph. */
  const onRefClick = useCallback(
    (nodeId: string) => {
      const off = activeRef === nodeId
      setActiveBeat(null)
      setActiveChat(null)
      setActiveRef(off ? null : nodeId)
      highlight(off ? [] : [nodeId])
    },
    [activeRef, highlight],
  )

  /** Click a cited paper in a graph-free answer: build that paper's graph.
   * The conversation survives the jump on its own (every graph load keeps it
   * now — see `store/transcript`), and the graph arrives with nothing selected,
   * like any other build: the click asked for the map around that paper, and
   * the detail panel it used to open landed on top of it. `refProvider` is the
   * backend that minted the id (absent on pre-v6.14.0 saves, where the selected
   * one is the best guess available); building under anything else looks the id
   * up in a namespace it was never in, and the build simply fails. */
  const onPaperSeed = useCallback(
    (nodeId: string, refProvider?: Provider) => {
      dispatch(loadGraph({ seed: nodeId, provider: refProvider }))
    },
    [dispatch],
  )

  /** Stop the in-flight question, keeping whatever it has already streamed —
   * the partial answer is real work the reader may still want. The abort path
   * is already quiet by design (`ask` skips `setError` when its own signal
   * aborted, and clears `asking` in `finally`), so this only has to fire it. */
  const stopAsk = useCallback(() => {
    askCtrl.current?.abort()
  }, [])

  /** Clear the shown lecture: stop it if it's still loading, drop its cache,
   *  and unlight the graph — leaving the chat and the other lectures intact.
   *  A no-op with no lecture on screen.
   *
   *  Two clears, not one contextual one (v7.10.0): the panel now shows the
   *  lecture and the chat as separate sections at the same time, so a single
   *  button could no longer say which of the two it would wipe. Each section
   *  owns its own. */
  const clearLecture = useCallback(() => {
    if (!activeMode) return
    setError(null)
    const ctrl = lectureCtrls.current.get(activeMode)
    // A loading lecture's abort runs runLecture's finally, which drops the
    // partial and clears activeMode; a finished one is dropped here directly.
    if (ctrl) ctrl.abort()
    else dispatch(lectureDropped(activeMode))
    setActiveBeat(null)
    setActiveRef(null)
    highlight([])
  }, [activeMode, dispatch, highlight])

  /** Clear the Q&A chat and detach its server session, leaving every cached
   *  lecture where it is. */
  const clearChat = useCallback(() => {
    setError(null)
    askCtrl.current?.abort()
    askCtrl.current = null
    setAsking(false)
    dispatch(chatCleared())
    setActiveChat(null)
    setActiveRef(null)
    highlight([])
    sessionId.current = newSessionId()
  }, [dispatch, highlight])

  /** Generate a lecture for `mode` from scratch: stream its beats into the
   *  mode's cache slot and show them live. Runs on its own controller, so it
   *  streams in parallel with the chat and any other lecture. A run aborted
   *  (stopped, or cleared) before finishing drops its partial cache, so the
   *  next click regenerates rather than reloading half a lecture. */
  const runLecture = useCallback(
    async (mode: LectureMode) => {
      if (!seedNode || lectureCtrls.current.has(mode)) return // already loading
      const ctrl = new AbortController()
      lectureCtrls.current.set(mode, ctrl)
      // The conversation this lecture belongs to, fixed for the whole run. The
      // reader may move to another exploration halfway through; every dispatch
      // below is addressed here so the beats keep landing in the lecture that
      // asked for them.
      const key = activeKeyRef.current
      const streamId = `lecture:${mode}:${nextStreamId()}`
      dispatch(streamStarted(streamId, key))
      setLoadingModes((prev) => (prev.includes(mode) ? prev : [...prev, mode]))
      dispatch(lectureStarted(mode, key)) // empties the slot and shows this mode
      setActiveBeat(null)
      setActiveChat(null)
      setActiveRef(null)
      setError(null)
      highlight([])
      let beatCount = 0
      let completed = false
      try {
        await streamLecture(
          // `edges` is what lets the backend scope a lecture to the seed's
          // OWN neighbours; without it a graph the reader has expanded gets
          // its satellites narrated as if the seed had cited them.
          { seed: seedNode, nodes: groundingNodes, edges: lectureEdges, mode },
          {
            signal: ctrl.signal,
            // Arrives before the first beat, so a beat's [Sn, p.N] library
            // citations render as real titles from the moment they appear.
            onSourceRefs: (refs) => dispatch(lectureSourcesSet({ mode, refs }, key)),
            onBeat: (beat) => {
              // `beat.graph_refs` (the [n] → node-id map) is resolved server-side —
              // a lecture numbers the mode-filtered story nodes, which the
              // frontend never sees, so it can't resolve them itself.
              dispatch(beatAdded({ mode, beat }, key))
              // Light up each beat as it arrives — but only while this lecture
              // is the one on screen (a background one stays quiet). A lecture
              // whose whole exploration is in the background is quiet too.
              if (shownModeRef.current === mode && activeKeyRef.current === key) {
                setActiveBeat(beatCount)
                highlight(beat.node_ids)
              }
              beatCount += 1
            },
            // An error belongs to the exploration that ran the lecture; only
            // surface it if that one is still what the reader is looking at.
            onError: (message) => {
              if (activeKeyRef.current === key) setError(message)
            },
          },
        )
        completed = true
      } catch (error) {
        if (!ctrl.signal.aborted && activeKeyRef.current === key) {
          setError(error instanceof Error ? error.message : String(error))
        }
      } finally {
        lectureCtrls.current.delete(mode)
        setLoadingModes((prev) => prev.filter((loading) => loading !== mode))
        dispatch(streamEnded(streamId, key))
        // Don't cache a half-streamed lecture — drop it so a re-click regenerates.
        if (!completed) dispatch(lectureDropped(mode, key))
      }
    },
    [seedNode, groundingNodes, lectureEdges, dispatch, highlight, nextStreamId],
  )

  /** The lecture-button toggle. One button per mode, acting as a show/hide
   *  switch over that mode's lecture:
   *    • the shown mode → hide it. A lecture still loading keeps generating in
   *      the background (its button keeps its dots); nothing is aborted, so
   *      re-selecting it picks the stream back up. A finished one just hides,
   *      its cache kept.
   *    • a hidden mode that's loading or cached → reveal it with no re-fetch
   *      (live if it's still streaming, instant if it's done);
   *    • an un-played mode → generate it (see {@link runLecture}), in parallel
   *      with whatever else is running. */
  const toggleLecture = useCallback(
    (mode: LectureMode) => {
      if (!seedNode) return
      if (activeMode === mode) {
        dispatch(lectureHidden())
        setActiveBeat(null)
        setActiveChat(null)
        setActiveRef(null)
        highlight([])
        return
      }
      const loading = lectureCtrls.current.has(mode)
      const cached = (lectures[mode]?.length ?? 0) > 0
      if (loading || cached) {
        dispatch(lectureShown(mode))
        setActiveBeat(null)
        setActiveChat(null)
        setActiveRef(null)
        highlight([])
        return
      }
      runLecture(mode)
    },
    [seedNode, activeMode, lectures, dispatch, highlight, runLecture],
  )

  const ask = useCallback(
    async (
      question: string,
      sourceIds: string[] | undefined,
      lectureModes: LectureMode[] | undefined,
      filters?: SearchOptions,
      history?: HistoryTurn[],
    ) => {
      // Only supersede a previous question — lectures stream on their own
      // controllers, so asking never interrupts one that's loading.
      askCtrl.current?.abort()
      const ctrl = new AbortController()
      askCtrl.current = ctrl
      setError(null)
      setAsking(true)
      highlight([])
      setActiveBeat(null)
      setActiveChat(null)
      setActiveRef(null)
      // A shown lecture STAYS shown. It used to be hidden here, because the
      // lecture and the chat shared one scroll and would otherwise stack on
      // top of each other; since v7.10.0 they are separate sections of the
      // panel, so asking a question no longer costs the reader the beats they
      // were reading.
      askIdxRef.current = chatLength + 1 // the assistant turn we're about to add
      // The conversation this answer belongs to, fixed for the whole run —
      // every dispatch below is addressed to it, so the reader can move to
      // another exploration mid-answer and this one still lands where it was
      // asked. `isActive()` guards the things that are about the *screen*
      // (errors, highlights, the active-turn mark) rather than the transcript.
      const key = activeKeyRef.current
      const isActive = () => activeKeyRef.current === key
      const streamId = `ask:${nextStreamId()}`
      dispatch(streamStarted(streamId, key))
      dispatch(turnStarted(question, key))
      // Why it ended, if it ended badly. The default covers the commonest
      // case by far — the run was simply abandoned (tab closed, exploration
      // deleted), which raises nothing worth quoting at a reader.
      let failure = 'This answer stopped before it finished.'
      // Whether any prose reached the turn. An answer that produces none has
      // failed as far as the reader is concerned, however it ended — and the
      // turn has to say so itself, because the panel's `error` state does not
      // survive a reload, which is exactly when this is most often seen.
      let produced = false
      try {
        if (seedNode) {
          // Graph open: the researcher — reads/expands/searches via tool use.
          // The numbered list `[n]` markers index into (1-based), matching the
          // backend's node_lines ordering; discovered papers slot in at their
          // server-assigned idx as they stream. Plus the raw answer text, so we
          // can resolve which `[n]`s were actually used once it's done.
          const numberedIds = groundingNodes.map((node) => node.id)
          // Lectures already played this session (trimmed to title + beat
          // heading/text) become extra context, so the answer can build on
          // them instead of re-deriving a story the student already heard.
          // `lectureModes` is the user's scope pick (undefined = all played);
          // a mode not in it is left out of context.
          const allowedModes = lectureModes ? new Set(lectureModes) : null
          const playedLectures: PlayedLecture[] = (
            Object.entries(lectures) as [LectureMode, Beat[]][]
          )
            .filter(
              ([mode, beats]) => beats.length > 0 && (!allowedModes || allowedModes.has(mode)),
            )
            .map(([mode, beats]) => ({
              title: LECTURE_TITLES[mode],
              beats: beats.map((beat) => ({ heading: beat.heading, text: beat.text })),
            }))
          let answerText = ''
          await streamAsk(
            {
              question,
              session_id: sessionId.current,
              seed: seedNode,
              nodes: groundingNodes,
              provider,
              source_ids: sourceIds,
              lectures: playedLectures.length > 0 ? playedLectures : undefined,
              history,
              ...askFilters(filters),
            },
            {
              signal: ctrl.signal,
              onToken: (token) => {
                answerText += token
                produced = true
                dispatch(tokenAppended(token, key))
              },
              onTrace: (trace) => dispatch(traceAdded(trace, key)),
              onDiscovery: (discovery) => {
                // A discovery belongs to the graph of the exploration that
                // found it. The workspace only holds the ACTIVE exploration's
                // graph, so merging a background find straight in would drop
                // this conversation's papers onto a map the reader is reading
                // for something else — the very cross-contamination the old
                // abort-on-switch existed to prevent. Off-screen finds wait in
                // their own conversation and are applied when it is opened.
                if (isActive()) dispatch(discoveryMerged(discovery))
                else dispatch(backgroundDiscovery(discovery, key))
                for (const node of discovery.nodes) {
                  if (typeof node.idx === 'number' && node.idx >= 1) {
                    numberedIds[node.idx - 1] = node.id
                  }
                }
              },
              onFigure: (figure) => dispatch(figureAdded(figure, key)),
              onSourceRefs: (refs) => dispatch(sourceRefsSet(refs, key)),
              onProvenance: (provenance) => dispatch(provenanceSet(provenance, key)),
              onPaperRefs: (refs) => dispatch(paperRefsSet(refs, key)),
              onCited: (ids) => {
                dispatch(citedSet(ids, key))
                // The highlight and the active-turn mark are about the screen,
                // so a background answer must not move either.
                if (!isActive()) return
                highlight(ids)
                // Mark this answer active, like a beat lights up on arrival.
                setActiveBeat(null)
                setActiveChat(askIdxRef.current)
              },
              onError: (message) => {
                // Keep the real reason: this is how the *backend's* account of
                // the failure ("Tool 'find_papers' exceeded max retries…")
                // reaches the turn, instead of the generic default.
                failure = message
                if (isActive()) setError(message)
              },
            },
          )
          // Answer complete: freeze the `[n]` → node-id map onto the turn.
          dispatch(graphRefsSet(resolveGraphRefs(answerText, numberedIds), key))
        } else {
          // No graph: the same researcher, seedless — it reaches for the
          // library (and the provider) through its tools instead of a numbered
          // graph. `provider` matters as much here as with a graph even though
          // there's no graph to match: it decides which backend the paper
          // search hits, and therefore whose ids come back on the citations.
          await streamAskSources(
            {
              question,
              session_id: sessionId.current,
              provider,
              source_ids: sourceIds,
              history,
              ...askFilters(filters),
            },
            {
              signal: ctrl.signal,
              onSourceRefs: (refs) => dispatch(sourceRefsSet(refs, key)),
              onProvenance: (provenance) => dispatch(provenanceSet(provenance, key)),
              onPaperRefs: (refs) => dispatch(paperRefsSet(refs, key)),
              onTrace: (trace) => dispatch(traceAdded(trace, key)),
              onFigure: (figure) => dispatch(figureAdded(figure, key)),
              onToken: (token) => {
                produced = true
                dispatch(tokenAppended(token, key))
              },
              onError: (message) => {
                failure = message
                if (isActive()) setError(message)
              },
            },
          )
        }
      } catch (err) {
        // An abort is not worth quoting ("AbortError: signal is aborted…");
        // the default already says the useful part.
        if (!ctrl.signal.aborted) failure = err instanceof Error ? err.message : String(err)
        if (!ctrl.signal.aborted && isActive()) setError(failure)
      } finally {
        // Read BEFORE releasing the slot, or the comparison is against the
        // null we just wrote and every answer looks superseded.
        const superseded = askCtrl.current !== ctrl
        if (!superseded) askCtrl.current = null
        dispatch(streamEnded(streamId, key))
        // Nothing is in progress any more, whatever the outcome — so no chip
        // may still say it is.
        dispatch(tracesSettled(key))
        // An answer that produced nothing gets a durable note on its own turn.
        // A *superseded* one is excluded: asking a new question deliberately
        // aborts the last, and that is not a failure to report — the reader
        // replaced that turn on purpose.
        if (!produced && !superseded) dispatch(answerFailed(failure, key))
        setAsking(false)
      }
    },
    [seedNode, groundingNodes, provider, chatLength, lectures, dispatch, highlight, nextStreamId],
  )

  /**
   * Ask a failed question again, picking up where it left off.
   *
   * The exchange that failed is removed first, so the transcript ends with one
   * exchange rather than a graveyard of attempts — and the question is re-run
   * through the ordinary path, so it behaves exactly like asking it now.
   *
   * **The history goes with it.** The server's own copy is in memory, keyed by
   * an id a page reload discards, so after one it has none — which is the very
   * situation a retry is usually in. The turns still on screen are sent along
   * and used only if the server has nothing of its own. A failed turn was
   * never written to history (it is recorded on success only), so what is sent
   * is exactly the conversation up to the question being retried.
   *
   * @param index The failed assistant turn's position in the chat.
   */
  const retryAnswer = useCallback(
    (index: number) => {
      const conversation = selectConversation(store.getState())
      const question = conversation.chat[index - 1]
      if (!question || question.role !== 'user') return
      const history: HistoryTurn[] = conversation.chat
        .slice(0, index - 1)
        .filter((turn) => turn.text.trim())
        .map((turn) => ({ role: turn.role, content: turn.text }))
      dispatch(failedTurnDropped(index))
      void ask(question.text, undefined, undefined, undefined, history)
    },
    [ask, dispatch, store],
  )

  return {
    hasGraph: !!seedNode,
    groundingNodes: groundingNodes as GraphNode[],
    loadingModes,
    asking,
    error,
    activeBeat,
    activeChat,
    onBeatClick,
    onChatClick,
    onRefClick,
    onGraphIds,
    onPaperSeed,
    provider,
    toggleLecture,
    ask,
    retryAnswer,
    stopAsk,
    clearLecture,
    clearChat,
  }
}
