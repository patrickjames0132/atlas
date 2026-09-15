import { conversationHistory, siblingContext } from './history'
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The conversation engine: drives the agent streams and dispatches their
 * events into the store (transcript, highlights, discoveries), while owning
 * the panel-local run state — the active beat/answer, the stream error, the
 * abort controllers (one for the message in flight, one for the classify in
 * front of it), and the backend session id.
 *
 * It used to own a second, parallel engine: a lecture had its own controller,
 * its own store slot, and a show/hide/clear/regenerate lifecycle around it,
 * because a lecture came from a button rather than from a message. Since
 * v7.21.0 every lecture arrives the way every answer does — as a reply to
 * something typed — so there is one stream path, not two.
 *
 * The split of responsibilities is the Phase 6 state directive: everything
 * the canvas or Save needs goes through the store; everything only this
 * panel renders stays right here.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { routeMessage, streamAsk, streamAskSources, streamLecture } from '../api'
import type {
  Beat,
  GraphNode,
  HistoryTurn,
  LectureFraming,
  MentionPaper,
  Provider,
  SearchOptions,
} from '../api'
import { useAppDispatch, useAppSelector, useAppStore } from '../store'
import { highlightSet, selectHighlightSet } from '../store/highlight'
import {
  answerFailed,
  backgroundDiscovery,
  chatBeatAdded,
  chatCleared,
  turnGraphSet,
  citedSet,
  figureAdded,
  graphRefsSet,
  sourceRefsSet,
  provenanceSet,
  paperRefsSet,
  failedTurnDropped,
  selectConversation,
  streamEnded,
  streamStarted,
  tracesSettled,
  tokenAppended,
  traceAdded,
  turnRouted,
  turnStarted,
  turnCompleted,
  turnContextSet,
} from '../store/transcript'
import {
  discoveryMerged,
  loadGraph,
  selectGroundingNodes,
  selectLectureNodes,
  selectSeedNode,
} from '../store/workspace'

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
/**
 * Widen an `@`-mention row into the full `GraphNode` the ask boundary wants.
 *
 * The dropdown's rows are trimmed to what a suggestion shows, and the backend
 * types `nodes` strictly (it rejects partial ones), so the missing fields are
 * filled with the same "not known yet" values a neighbour carries before
 * hydration. `rels: []` is the honest tag: the paper is in the question's
 * scope, not on the graph, so it has no relation to the seed — and nothing
 * paints it, because it is never merged onto the canvas.
 *
 * @param paper The picked mention row.
 * @returns The paper as a graph node.
 */
function mentionNode(paper: MentionPaper): GraphNode {
  return {
    id: paper.id,
    arxiv_id: paper.arxiv_id,
    title: paper.title,
    authors: paper.authors ?? null,
    venue: paper.venue ?? null,
    year: paper.year ?? null,
    citation_count: paper.citation_count ?? null,
    url: paper.url ?? null,
    rels: [],
    is_seed: false,
  }
}

const threadControllers = new Map<string, { current: AbortController | null }>()

export function useConversation() {
  const dispatch = useAppDispatch()
  // Read synchronously when retrying: the history to resend is whatever is
  // on screen at the moment of the click, not at the last render.
  const store = useAppStore()
  const seedNode = useAppSelector(selectSeedNode)
  const groundingNodes = useAppSelector(selectGroundingNodes)
  // Strictly what's on screen — the lecture's promise, and the one place it
  // differs from the researcher's grounding (see `selectLectureNodes`).
  const lectureNodes = useAppSelector(selectLectureNodes)
  // Which cited papers are still reachable — a transcript now outlives the
  // graph it was written against, so `[n]` chips are checked before they
  // render as controls.
  // The selected provider — so the researcher's expand/search/hydrate use the
  // same backend (and id space) as the graph the question is grounded in, and
  // so the graph-free chat searches the backend the dropdown actually names.
  const provider = useAppSelector((state) => state.workspace.provider)
  const chatLength = useAppSelector((state) => selectConversation(state).chat.length)
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

  const [routing, setAsking] = useState(false)
  const running = useAppSelector((state) => state.transcript.byKey[activeKey]?.running.length ?? 0)
  const [error, setError] = useState<string | null>(null)
  // Which chat answer is "active" (its whole grounding set lit on the graph).
  // Panel-local UI state — only the RESULTING highlight ids are global.
  const [activeChat, setActiveChat] = useState<number | null>(null)
  // Which beat of which turn is lit. Addressed by turn as well as index
  // because a conversation can hold several lectures, and an index alone
  // would light a beat of the wrong one. At most one of the three selections
  // here is non-null.
  const [activeChatBeat, setActiveChatBeat] = useState<{ turn: number; beat: number } | null>(null)
  // The node currently spotlit by a clicked inline `[n]` — click the same one
  // again to clear it (like re-clicking an active beat).
  const [activeRef, setActiveRef] = useState<string | null>(null)

  // A per-stream id, so `running` can hold several at once (answers in
  // different explorations) and each removes only its own entry when it
  // finishes.
  const streamCounter = useRef(0)
  const nextStreamId = useCallback(() => {
    streamCounter.current += 1
    return String(streamCounter.current)
  }, [])

  // The message in flight — an answer or a lecture, since both are replies to
  // something typed and only one of them can be the latest.
  if (!threadControllers.has(activeKey)) threadControllers.set(activeKey, { current: null })
  const askCtrl = threadControllers.get(activeKey)!
  // The in-flight message classification (see `send`). Its own controller
  // rather than `askCtrl`'s, because it runs *before* the turn exists: a
  // second message must abort the first's route without also aborting an
  // answer that is legitimately still streaming into the transcript.
  const routeCtrl = useRef<AbortController | null>(null)

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
  }, [seedNode, activeKey, askCtrl])
  // Keys the backend's per-chat history; clearing the chat mints a new one so
  // the fresh conversation also detaches from server-side context.
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
      setActiveChat(null)
      setActiveChatBeat(null)
      setActiveRef(null)
    }
  }, [highlightIds])

  /** Click a beat: light its papers, click again to clear. Addressed by turn
   *  AND beat, since a conversation may hold several lectures and an index
   *  alone would light a beat of the wrong one. */
  const onChatBeatClick = useCallback(
    (turn: number, index: number, beat: Beat) => {
      const off = activeChatBeat?.turn === turn && activeChatBeat.beat === index
      setActiveChatBeat(off ? null : { turn, beat: index })
      setActiveChat(null)
      setActiveRef(null)
      highlight(off ? [] : beat.node_ids)
    },
    [activeChatBeat, highlight],
  )

  /** Click an answer: re-light the papers it was grounded in. */
  const onChatClick = useCallback(
    (index: number, cited: string[]) => {
      const off = activeChat === index
      setActiveChat(off ? null : index)
      setActiveChatBeat(null)
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
      setActiveChat(null)
      setActiveChatBeat(null)
      setActiveRef(off ? null : nodeId)
      highlight(off ? [] : [nodeId])
    },
    [activeRef, highlight],
  )

  /** Open a graph citation directly in its own thread, resuming the existing
   * thread when this provider and seed already belong to the exploration. */
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
    // A message stopped while it is still being *routed* has no turn yet, so
    // there is nothing for `askCtrl` to abort — Stop has to reach the classify
    // too, or the reader's stop is silently ignored and an answer they
    // cancelled starts streaming a moment later.
    routeCtrl.current?.abort()
    routeCtrl.current = null
    setAsking(false)
  }, [askCtrl])

  /** Clear the conversation and detach its server session.
   *
   *  One clear, not the two v7.10.0 needed. A lecture used to live in its own
   *  section beside the chat, so a single button could not say which of the
   *  two it would wipe and each section owned one; with lectures in the
   *  transcript there is one thing to clear. */
  const clearChat = useCallback(() => {
    setError(null)
    askCtrl.current?.abort()
    askCtrl.current = null
    setAsking(false)
    dispatch(chatCleared())
    setActiveChat(null)
    setActiveRef(null)
    highlight([])
  }, [dispatch, highlight, askCtrl])

  const ask = useCallback(
    async (
      question: string,
      sourceIds: string[] | undefined,
      filters?: SearchOptions,
      history?: HistoryTurn[],
      mentioned?: MentionPaper[],
    ) => {
      // Supersede whatever was in flight. One controller covers answers and
      // lectures alike now: both are replies to a typed message, and a new
      // message means the reader has moved on from the last one.
      askCtrl.current?.abort()
      const ctrl = new AbortController()
      askCtrl.current = ctrl
      setError(null)
      setAsking(true)
      highlight([])
      setActiveChat(null)
      setActiveChatBeat(null)
      setActiveRef(null)
      askIdxRef.current = chatLength + 1 // the assistant turn we're about to add
      // The conversation this answer belongs to, fixed for the whole run —
      // every dispatch below is addressed to it, so the reader can move to
      // another exploration mid-answer and this one still lands where it was
      // asked. `isActive()` guards the things that are about the *screen*
      // (errors, highlights, the active-turn mark) rather than the transcript.
      const key = activeKeyRef.current
      const isActive = () => store.getState().transcript.activeKey === key
      const streamId = `ask:${nextStreamId()}`
      dispatch(streamStarted(streamId, key))
      history ??= conversationHistory(store.getState().transcript.byKey[key]?.chat ?? [])
      dispatch(turnStarted(question, key))
      const owner = store.getState().explorations.byId[store.getState().explorations.activeId]
      dispatch(
        turnContextSet(
          owner.threads
            .filter((thread) => thread.id !== key && question.includes(`@thread[${thread.title}]`))
            .map((thread) => ({ id: thread.id, title: thread.title })),
          key,
        ),
      )
      // Stamp the turn with the graph it is about, while that is still what is
      // on screen. Skipped graph-free: there is no graph to name, and an
      // answer over the library alone is not made clearer by saying so.
      if (seedNode) {
        dispatch(
          turnGraphSet(
            {
              seedId: seedNode.id,
              seedTitle: seedNode.title,
              nodes: groundingNodes.length,
              provider,
            },
            key,
          ),
        )
      }
      // Why it ended, if it ended badly. The default covers the commonest
      // case by far — the run was simply abandoned (tab closed, exploration
      // deleted), which raises nothing worth quoting at a reader.
      let failed = false
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
          // Papers the reader `@`-mentioned inside the question join the
          // grounding, ahead of the graph's own nodes so they take the low
          // `[n]` numbers the answer is most likely to cite. They are NOT
          // merged onto the canvas: the reader asked about a paper, which is
          // not the same as asking to explore it, and rearranging their graph
          // as a side effect of a question is exactly the override this app
          // keeps having to remove. A mention already on screen is deduped
          // rather than numbered twice.
          const onScreen = new Set(groundingNodes.map((node) => node.id))
          const attached = (mentioned ?? [])
            .filter((paper) => !onScreen.has(paper.id))
            .map((paper) => mentionNode(paper))
          const askNodes = [...attached, ...groundingNodes]
          const numberedIds = askNodes.map((node) => node.id)
          // No `lectures` argument any more. A played lecture used to be
          // pushed into the prompt here as extra context, gated by the 🎓
          // scope picker, because it lived outside the conversation and the
          // researcher had no other way to see it. A lecture is a turn now, so
          // it reaches the agent as ordinary history like any other turn — and
          // the picker, the wire field and the researcher's `_lectures_context`
          // all went with it in v7.21.0.
          let answerText = ''
          await streamAsk(
            {
              question,
              seed: seedNode,
              nodes: askNodes,
              provider,
              source_ids: sourceIds,
              history,
              thread_context: siblingContext(store.getState(), question),
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
                setActiveChatBeat(null)
                setActiveChat(askIdxRef.current)
              },
              onError: (message) => {
                // Keep the real reason: this is how the *backend's* account of
                // the failure ("Tool 'find_papers' exceeded max retries…")
                // reaches the turn, instead of the generic default.
                failed = true
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
              provider,
              source_ids: sourceIds,
              history,
              thread_context: siblingContext(store.getState(), question),
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
                failed = true
                failure = message
                if (isActive()) setError(message)
              },
            },
          )
        }
        if (!failed && !ctrl.signal.aborted) dispatch(turnCompleted(key))
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
        if (!superseded) dispatch(tracesSettled(key))
        // An answer that produced nothing gets a durable note on its own turn.
        // A *superseded* one is excluded: asking a new question deliberately
        // aborts the last, and that is not a failure to report — the reader
        // replaced that turn on purpose.
        if (!produced && !superseded) dispatch(answerFailed(failure, key))
        if (!superseded) setAsking(false)
      }
    },
    [
      seedNode,
      groundingNodes,
      provider,
      chatLength,
      dispatch,
      highlight,
      nextStreamId,
      store,
      askCtrl,
    ],
  )

  /**
   * Deliver a lecture as the answer to a typed message.
   *
   * Beats go onto the chat turn (`chatBeatAdded`), because a lecture is a
   * *reply*: it belongs in the conversation, where the reader can scroll back
   * to it, ask a follow-up underneath it, and keep the one before it. It runs
   * on the same `askCtrl` as {@link ask} for the same reason — one message is
   * in flight at a time, whichever assistant is answering it.
   *
   * There was a second path until v7.21.0: a `runLecture` writing into the
   * panel's own `lecture` slot on its own controller, so a button lecture and
   * a chat answer streamed in parallel. This is what is left of the two.
   *
   * @param question The message as typed, which becomes the user turn.
   * @param framing  How to tell it — from the `/lecture` command, the router,
   *                 or a correction.
   * @param routed   Whether a model chose this destination. True marks the
   *                 turn so the transcript can offer the researcher instead;
   *                 false is a choice the reader made themselves, which needs
   *                 no second-guessing.
   */
  const lectureInChat = useCallback(
    async (question: string, framing: LectureFraming, routed: boolean) => {
      if (!seedNode) return
      askCtrl.current?.abort()
      const ctrl = new AbortController()
      askCtrl.current = ctrl
      setError(null)
      setAsking(true)
      highlight([])
      setActiveChat(null)
      setActiveChatBeat(null)
      setActiveRef(null)
      const key = activeKeyRef.current
      const isActive = () => store.getState().transcript.activeKey === key
      const turnIdx = chatLength + 1 // the assistant turn about to be added
      const streamId = `ask:${nextStreamId()}`
      dispatch(streamStarted(streamId, key))
      dispatch(turnStarted(question, key))
      // `lectureNodes`, not `groundingNodes` — the count has to be the set
      // actually narrated, which is the stricter of the two (see
      // `selectLectureNodes`). `seedNode` is non-null: the guard above returns.
      dispatch(
        turnGraphSet(
          {
            seedId: seedNode.id,
            seedTitle: seedNode.title,
            nodes: lectureNodes.length,
            provider,
          },
          key,
        ),
      )
      if (routed) dispatch(turnRouted('lecture', key))
      let failed = false
      let failure = 'This lecture stopped before it finished.'
      let beatCount = 0
      try {
        await streamLecture(
          // Same scope as the button's lecture: strictly what the reader can
          // see. The router decided which *agent* answers, not which papers —
          // rescoping a lecture because it was asked for in words would make
          // the same request mean two things.
          { seed: seedNode, nodes: lectureNodes, framing },
          {
            signal: ctrl.signal,
            onSourceRefs: (refs) => dispatch(sourceRefsSet(refs, key)),
            onBeat: (beat) => {
              dispatch(chatBeatAdded(beat, key))
              // Light each beat as it lands, the way the panel's lecture does
              // — but only while this exploration is the one on screen.
              if (isActive()) {
                setActiveChatBeat({ turn: turnIdx, beat: beatCount })
                highlight(beat.node_ids)
              }
              beatCount += 1
            },
            onError: (message) => {
              failed = true
              failure = message
              if (isActive()) setError(message)
            },
          },
        )
        if (!failed && !ctrl.signal.aborted) dispatch(turnCompleted(key))
      } catch (error) {
        if (!ctrl.signal.aborted) {
          failure = error instanceof Error ? error.message : String(error)
          if (isActive()) setError(failure)
        }
      } finally {
        const superseded = askCtrl.current !== ctrl
        if (!superseded) askCtrl.current = null
        dispatch(streamEnded(streamId, key))
        // A lecture that produced no beats has failed as far as the reader is
        // concerned, however it ended — and the turn has to say so itself,
        // because `error` does not survive a reload. A superseded one is
        // excluded: sending another message aborts this on purpose.
        if (beatCount === 0 && !superseded) dispatch(answerFailed(failure, key))
        if (!superseded) setAsking(false)
      }
    },
    [
      seedNode,
      lectureNodes,
      provider,
      chatLength,
      dispatch,
      highlight,
      nextStreamId,
      store,
      askCtrl,
    ],
  )

  /**
   * Send a typed message to whichever assistant it wants.
   *
   * The one branch in the composer's decision tree that cannot be taken on
   * plain facts. Everything above it — a pasted id, a bare `@`-mention, an
   * unresolved `@phrase` — is decided by a regex or by what the reader picked
   * from a dropdown; this one asks a model, because the difference between
   * "teach me these papers" and "which of these used dropout" lives in the
   * words and nowhere else.
   *
   * **The classify is skipped whenever a lecture is impossible**: no graph, or
   * nothing visible to lecture about. That is not an optimization, it is the
   * routing rule — there is no second destination to choose, so paying for a
   * choice would be spending the reader's latency on a foregone conclusion.
   *
   * @param question  The message as typed.
   * @param sourceIds Library scope, passed through to {@link ask}.
   * @param filters   Search filters, passed through to {@link ask}.
   * @param mentioned Papers `@`-mentioned in the message.
   */
  const send = useCallback(
    async (
      question: string,
      sourceIds: string[] | undefined,
      filters?: SearchOptions,
      mentioned?: MentionPaper[],
    ) => {
      const routable = !!seedNode && lectureNodes.length > 0
      if (!routable) {
        void ask(question, sourceIds, filters, undefined, mentioned)
        return
      }
      // The button reacts to the send immediately rather than after the
      // classify: a bar that looks idle for half a second invites a second
      // press, which would abort the first message's own route.
      setAsking(true)
      routeCtrl.current?.abort()
      const ctrl = new AbortController()
      routeCtrl.current = ctrl
      const routingKey = store.getState().transcript.activeKey
      const decision = await routeMessage(question, ctrl.signal)
      if (store.getState().transcript.activeKey !== routingKey) {
        setAsking(false)
        return
      }
      if (ctrl.signal.aborted) return // superseded; the new send owns `asking`
      routeCtrl.current = null
      if (decision.target === 'lecture') {
        void lectureInChat(question, decision.framing, true)
        return
      }
      void ask(question, sourceIds, filters, undefined, mentioned)
    },
    [seedNode, lectureNodes, ask, lectureInChat, store],
  )

  /**
   * Send a turn's question to the *other* assistant — the reader correcting a
   * route.
   *
   * This is what makes model routing affordable. A misroute is not a wrong
   * answer to be spotted and worked around, it is one click: the transcript
   * says which assistant answered and offers the other, and taking the offer
   * re-asks the same question there. The corrected turn is *appended* rather
   * than replacing the original — the reader may well want both, and a
   * transcript that rewrites itself is worse than one that grows.
   *
   * @param index The assistant turn whose route is being corrected.
   */
  const reroute = useCallback(
    (index: number) => {
      const conversation = selectConversation(store.getState())
      const answer = conversation.chat[index]
      const question = conversation.chat[index - 1]
      if (!answer || !question || question.role !== 'user') return
      // The correction is the reader's own decision, so `routed` is false:
      // the new turn carries no offer to route it back again, which would be
      // an invitation to ping-pong between two answers they already have.
      if (answer.routedTo === 'lecture') {
        void ask(question.text, undefined, undefined, undefined, undefined)
      } else {
        void lectureInChat(question.text, 'summary', false)
      }
    },
    [ask, lectureInChat, store],
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
      const history = conversationHistory(conversation.chat.slice(0, index - 1))
      dispatch(failedTurnDropped(index))
      void ask(question.text, undefined, undefined, history)
    },
    [ask, dispatch, store],
  )

  return {
    hasGraph: !!seedNode,
    groundingNodes: groundingNodes as GraphNode[],
    asking: running > 0 || routing,
    error,
    activeChat,
    onChatClick,
    onRefClick,
    onPaperSeed,
    provider,
    ask,
    send,
    reroute,
    lectureInChat,
    activeChatBeat,
    onChatBeatClick,
    retryAnswer,
    stopAsk,
    clearChat,
  }
}
