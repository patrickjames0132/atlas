/**
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
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { LECTURE_TITLES, streamAsk, streamAskSources, streamLecture } from '../api'
import type { Beat, GraphNode, LectureMode, PlayedLecture } from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { highlightSet, selectHighlightSet } from '../store/highlight'
import {
  beatAdded,
  chatCleared,
  citedSet,
  figureAdded,
  lectureDropped,
  lectureHidden,
  lectureShown,
  lectureStarted,
  refsSet,
  retrieveSet,
  tokenAppended,
  traceAdded,
  turnStarted,
} from '../store/transcript'
import { discoveryMerged, selectGroundingNodes, selectSeedNode } from '../store/workspace'

/**
 * Mint a fresh chat-session id (keys the backend's per-conversation history).
 *
 * @returns A UUID, or a random-digits fallback off-HTTPS.
 */
const newSessionId = () => (crypto.randomUUID?.() as string) || String(Math.random()).slice(2)

/** An inline citation marker in answer prose: a single index (`[7]`) or a
 *  combined list (`[14, 29]`). Group 1 holds the digits and separators; split
 *  on `REF_SEPARATOR` for the individual indices. Kept in step with the same
 *  pattern in `remarkCite` (render) and the backend's `refs_from_text`. */
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
function resolveRefs(text: string, numberedIds: string[]): Record<string, string> {
  const refs: Record<string, string> = {}
  for (const match of text.matchAll(REF_MARKER)) {
    // A combined marker (`[14, 29]`) resolves each of its indices, so every
    // number in it becomes clickable.
    for (const token of match[1].split(REF_SEPARATOR)) {
      const index = Number(token)
      const nodeId = numberedIds[index - 1]
      if (nodeId) refs[token] = nodeId
    }
  }
  return refs
}

/**
 * Own the assistant's stream engine: run the lecture/ask/library streams,
 * dispatch their events into the store, and expose the panel's run state.
 *
 * @returns The run state + the lecture/ask/clear entry points.
 */
export function useConversation() {
  const dispatch = useAppDispatch()
  const seedNode = useAppSelector(selectSeedNode)
  const groundingNodes = useAppSelector(selectGroundingNodes)
  // The graph's provider — so the researcher's expand/search/hydrate use the
  // same backend (and id space) as the graph the question is grounded in.
  const provider = useAppSelector((state) => state.workspace.provider)
  const chatLength = useAppSelector((state) => state.transcript.chat.length)
  const lectures = useAppSelector((state) => state.transcript.lectures)
  const activeMode = useAppSelector((state) => state.transcript.activeMode)

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

  // Abort every in-flight stream when the panel unmounts. It remounts on each
  // graph change (the shell keys it on the workspace epoch), so a provider
  // switch / re-seed / Home / restore stops a running Q&A or lecture instead of
  // letting it keep streaming discoveries into the NEW graph. (Capturing the ref
  // objects — stable — so the cleanup reads their live `.current` at unmount.)
  useEffect(() => {
    const asks = askCtrl
    const lectures = lectureCtrls
    return () => {
      asks.current?.abort()
      lectures.current.forEach((ctrl) => ctrl.abort())
    }
  }, [])
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

  /** The Clear button, contextual on what's selected:
   *    • a lecture is shown → clear just that lecture (stop it if it's still
   *      loading, drop its cache, and unlight the graph), leaving the chat and
   *      the other lectures intact;
   *    • no lecture shown → clear the Q&A chat (and detach its server session),
   *      leaving every cached lecture. */
  const clear = useCallback(() => {
    setError(null)
    if (activeMode) {
      const ctrl = lectureCtrls.current.get(activeMode)
      // A loading lecture's abort runs runLecture's finally, which drops the
      // partial and clears activeMode; a finished one is dropped here directly.
      if (ctrl) ctrl.abort()
      else dispatch(lectureDropped(activeMode))
      setActiveBeat(null)
      setActiveRef(null)
      highlight([])
    } else {
      askCtrl.current?.abort()
      askCtrl.current = null
      setAsking(false)
      dispatch(chatCleared())
      setActiveChat(null)
      setActiveRef(null)
      highlight([])
      sessionId.current = newSessionId()
    }
  }, [activeMode, dispatch, highlight])

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
      setLoadingModes((prev) => (prev.includes(mode) ? prev : [...prev, mode]))
      dispatch(lectureStarted(mode)) // empties the slot and shows this mode
      setActiveBeat(null)
      setActiveChat(null)
      setActiveRef(null)
      setError(null)
      highlight([])
      let beatCount = 0
      let completed = false
      try {
        await streamLecture(
          { seed: seedNode, nodes: groundingNodes, mode },
          {
            signal: ctrl.signal,
            onBeat: (beat) => {
              // `beat.refs` (the [n] → node-id map) is resolved server-side —
              // a lecture numbers the mode-filtered story nodes, which the
              // frontend never sees, so it can't resolve them itself.
              dispatch(beatAdded({ mode, beat }))
              // Light up each beat as it arrives — but only while this lecture
              // is the one on screen (a background one stays quiet).
              if (shownModeRef.current === mode) {
                setActiveBeat(beatCount)
                highlight(beat.node_ids)
              }
              beatCount += 1
            },
            onError: (message) => setError(message),
          },
        )
        completed = true
      } catch (error) {
        if (!ctrl.signal.aborted) setError(error instanceof Error ? error.message : String(error))
      } finally {
        lectureCtrls.current.delete(mode)
        setLoadingModes((prev) => prev.filter((loading) => loading !== mode))
        // Don't cache a half-streamed lecture — drop it so a re-click regenerates.
        if (!completed) dispatch(lectureDropped(mode))
      }
    },
    [seedNode, groundingNodes, dispatch, highlight],
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
      // Asking drops into the Q&A view: hide any shown lecture (its cache and
      // any in-flight stream survive — re-select its button to return to it).
      if (activeMode) dispatch(lectureHidden())
      askIdxRef.current = chatLength + 1 // the assistant turn we're about to add
      dispatch(turnStarted(question))
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
            },
            {
              signal: ctrl.signal,
              onToken: (token) => {
                answerText += token
                dispatch(tokenAppended(token))
              },
              onTrace: (trace) => dispatch(traceAdded(trace)),
              onDiscovery: (discovery) => {
                dispatch(discoveryMerged(discovery))
                for (const node of discovery.nodes) {
                  if (typeof node.idx === 'number' && node.idx >= 1) {
                    numberedIds[node.idx - 1] = node.id
                  }
                }
              },
              onFigure: (figure) => dispatch(figureAdded(figure)),
              onCited: (ids) => {
                highlight(ids)
                // Mark this answer active, like a beat lights up on arrival.
                setActiveBeat(null)
                setActiveChat(askIdxRef.current)
                dispatch(citedSet(ids))
              },
              onError: (message) => setError(message),
            },
          )
          // Answer complete: freeze the `[n]` → node-id map onto the turn.
          dispatch(refsSet(resolveRefs(answerText, numberedIds)))
        } else {
          // No graph: the librarian — answer straight from the library.
          await streamAskSources(
            { question, session_id: sessionId.current, source_ids: sourceIds },
            {
              signal: ctrl.signal,
              onRetrieve: (retrieval) => dispatch(retrieveSet(retrieval)),
              onTrace: (trace) => dispatch(traceAdded(trace)),
              onFigure: (figure) => dispatch(figureAdded(figure)),
              onToken: (token) => dispatch(tokenAppended(token)),
              onError: (message) => setError(message),
            },
          )
        }
      } catch (err) {
        if (!ctrl.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (askCtrl.current === ctrl) askCtrl.current = null
        setAsking(false)
      }
    },
    [seedNode, groundingNodes, provider, chatLength, activeMode, lectures, dispatch, highlight],
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
    toggleLecture,
    ask,
    clear,
  }
}
