/**
 * The conversation engine: drives the three agent streams and dispatches
 * their events into the store (transcript, highlights, discoveries), while
 * owning the panel-local run state — in-flight flags, the active beat/answer,
 * the stream error, the abort controller, and the backend session id.
 *
 * The split of responsibilities is the Phase 6 state directive: everything
 * the canvas or Save needs goes through the store; everything only this
 * panel renders stays right here.
 */

import { useCallback, useRef, useState } from 'react'
import { streamAsk, streamAskSources, streamLecture } from '../api'
import type { Beat, GraphNode, LectureMode } from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { highlightSet } from '../store/highlight'
import {
  beatAdded,
  citedSet,
  cleared,
  figureAdded,
  histTraceAdded,
  lectureStarted,
  retrieveSet,
  tokenAppended,
  traceAdded,
  turnStarted,
} from '../store/transcript'
import { discoveryMerged, selectGroundingNodes, selectSeedNode } from '../store/workspace'

const newSessionId = () =>
  (crypto.randomUUID?.() as string) || String(Math.random()).slice(2)

export function useConversation() {
  const dispatch = useAppDispatch()
  const seedNode = useAppSelector(selectSeedNode)
  const groundingNodes = useAppSelector(selectGroundingNodes)
  const chatLength = useAppSelector((s) => s.transcript.chat.length)

  const [teaching, setTeaching] = useState(false)
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Which lecture beat / chat answer is "active" (its papers lit on the
  // graph). Panel-local UI state — only the RESULTING highlight ids are
  // global. At most one of the two is non-null.
  const [activeBeat, setActiveBeat] = useState<number | null>(null)
  const [activeChat, setActiveChat] = useState<number | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  // Keys the backend's per-chat history; a Clear mints a new one so the
  // fresh conversation also detaches from server-side context.
  const sessionId = useRef(newSessionId())
  // The chat index the in-flight answer streams into (for onCited's active
  // marking) — chat.length + 1 at turn start (user turn, then assistant).
  const askIdxRef = useRef(0)

  const stopActive = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  const highlight = useCallback(
    (ids: string[]) => dispatch(highlightSet(ids)),
    [dispatch],
  )

  /** Click a beat: light its papers; click the active one again to clear. */
  const onBeatClick = useCallback(
    (index: number, beat: Beat) => {
      const off = activeBeat === index
      setActiveBeat(off ? null : index)
      setActiveChat(null)
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
      highlight(off ? [] : cited)
    },
    [activeChat, highlight],
  )

  /** Wipe the conversation — a fresh start without re-seeding the graph. */
  const clear = useCallback(() => {
    stopActive()
    dispatch(cleared())
    setActiveBeat(null)
    setActiveChat(null)
    setError(null)
    setTeaching(false)
    setAsking(false)
    highlight([])
    sessionId.current = newSessionId()
  }, [stopActive, dispatch, highlight])

  const runLecture = useCallback(
    async (mode: LectureMode) => {
      if (!seedNode) return
      stopActive()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      dispatch(lectureStarted())
      setActiveBeat(null)
      setActiveChat(null)
      setError(null)
      setTeaching(true)
      highlight([])
      let beatCount = 0
      try {
        await streamLecture(
          { seed: seedNode, nodes: groundingNodes, mode },
          {
            signal: ctrl.signal,
            onBeat: (beat) => {
              dispatch(beatAdded(beat))
              // Light up each beat as it arrives.
              setActiveBeat(beatCount)
              highlight(beat.node_ids)
              beatCount += 1
            },
            // History mode first walks back through references to the field's
            // roots: show the hops, and merge the ancestors into the graph.
            onTrace: (t) => dispatch(histTraceAdded(t)),
            onDiscovery: (d) => dispatch(discoveryMerged(d)),
            onError: (m) => setError(m),
          },
        )
      } catch (e) {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null
        setTeaching(false)
      }
    },
    [seedNode, groundingNodes, dispatch, highlight, stopActive],
  )

  const ask = useCallback(
    async (question: string, sourceIds: string[] | undefined) => {
      stopActive()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setError(null)
      setAsking(true)
      highlight([])
      setActiveBeat(null)
      setActiveChat(null)
      askIdxRef.current = chatLength + 1 // the assistant turn we're about to add
      dispatch(turnStarted(question))
      try {
        if (seedNode) {
          // Graph open: the researcher — reads/expands/searches via tool use.
          await streamAsk(
            {
              question,
              session_id: sessionId.current,
              seed: seedNode,
              nodes: groundingNodes,
              source_ids: sourceIds,
            },
            {
              signal: ctrl.signal,
              onToken: (t) => dispatch(tokenAppended(t)),
              onTrace: (t) => dispatch(traceAdded(t)),
              onDiscovery: (d) => dispatch(discoveryMerged(d)),
              onFigure: (f) => dispatch(figureAdded(f)),
              onCited: (ids) => {
                highlight(ids)
                // Mark this answer active, like a beat lights up on arrival.
                setActiveBeat(null)
                setActiveChat(askIdxRef.current)
                dispatch(citedSet(ids))
              },
              onError: (m) => setError(m),
            },
          )
        } else {
          // No graph: the librarian — answer straight from the library.
          await streamAskSources(
            { question, session_id: sessionId.current, source_ids: sourceIds },
            {
              signal: ctrl.signal,
              onRetrieve: (r) => dispatch(retrieveSet(r)),
              onToken: (t) => dispatch(tokenAppended(t)),
              onError: (m) => setError(m),
            },
          )
        }
      } catch (err) {
        if (!ctrl.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null
        setAsking(false)
      }
    },
    [seedNode, groundingNodes, chatLength, dispatch, highlight, stopActive],
  )

  return {
    hasGraph: !!seedNode,
    groundingNodes: groundingNodes as GraphNode[],
    teaching,
    asking,
    error,
    activeBeat,
    activeChat,
    onBeatClick,
    onChatClick,
    runLecture,
    ask,
    clear,
  }
}
