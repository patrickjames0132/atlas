/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The transcript slice: the reader's conversations — chat turns and lecture
 * beats — **several at once**, keyed by exploration.
 *
 * This slice is why the old `onStateChange`/`teacherStateRef` plumbing died:
 * the transcript used to live in Teacher.tsx with a live duplicate hoisted
 * into Atlas purely so Save could read it. Now there is exactly one copy,
 * owned by neither component.
 *
 * **Why it holds more than one conversation.** Until v7.16.0 it held exactly
 * one, and switching exploration therefore had to *abort* whatever was
 * streaming — otherwise the running answer would have carried on writing into
 * the conversation you had just moved to. That made switching mid-answer
 * destroy the answer. Conversations are now keyed, so a stream writes into the
 * exploration that started it whether or not that one is on screen, and you
 * can leave an answer running and come back to it.
 *
 * **How a stream addresses its own conversation.** Every action takes an
 * optional key as its *second* argument, carried in `meta.key`; omitted, it
 * targets whichever conversation is active. That default is deliberate — the
 * many dispatches that are plainly about what the reader is looking at
 * (clicking a lecture mode, clearing the chat) stay unchanged and unkeyed,
 * while the streaming paths capture their key once at stream start and pass it
 * every time. Only code that can outlive the switch has to think about it.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { createSlice, nanoid } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import type {
  AnswerFigure,
  Beat,
  ChatMsg,
  GraphEdge,
  GraphNode,
  LectureMode,
  PaperRef,
  ProvenanceEvent,
  RetrieveEvent,
  SourceRef,
  TraceEvent,
} from '../api'
import { loadGraph, restoreSession, workspaceCleared } from './workspace'

/** One exploration's conversation. */
export interface Conversation {
  chat: ChatMsg[]
  /**
   * Per-mode lecture cache: a mode maps to its generated beats once it has
   * been played. Re-selecting a cached mode reloads its beats without a
   * re-fetch; the four modes are independent, so switching between them is
   * instant after the first play.
   */
  lectures: Partial<Record<LectureMode, Beat[]>>
  /**
   * Per-mode library index for the `[Sn]` markers a lecture's beats cite —
   * one map per lecture, not per beat, because every beat of a lecture cites
   * the same retrieved sources. Only intuition-mode lectures retrieve, so the
   * other modes never get an entry.
   */
  lectureSources: Partial<Record<LectureMode, Record<string, SourceRef>>>
  /** Which cached lecture is currently shown on screen (null = none visible —
   *  every mode button is deselected). */
  activeMode: LectureMode | null
  /**
   * Ids of the streams still running in this conversation.
   *
   * A list rather than a flag because a conversation can have an answer and
   * several lectures in flight at once. It is what lets the rail show which
   * explorations are still working while you read a different one, and what
   * tells the autosave that a background conversation has settled and is worth
   * writing.
   */
  running: string[]
  /**
   * Papers this conversation's agent found while it was **not** on screen.
   *
   * A discovery belongs to the graph of the exploration that found it, and the
   * workspace only ever holds the active exploration's graph — so merging a
   * background find straight in would drop other people's papers onto the map
   * you are reading. They wait here and are applied when the exploration is
   * next opened. (A find made while the conversation *is* active goes straight
   * to the workspace, as it always did.)
   */
  pendingDiscoveries: { nodes: GraphNode[]; edges: GraphEdge[] }
}

export interface TranscriptState {
  byKey: Record<string, Conversation>
  /** Which conversation the teacher panel is showing. */
  activeKey: string
}

/**
 * A fresh, empty conversation.
 *
 * @returns A conversation with no chat, no lectures and nothing running.
 */
export function emptyConversation(): Conversation {
  return {
    chat: [],
    lectures: {},
    lectureSources: {},
    activeMode: null,
    running: [],
    pendingDiscoveries: { nodes: [], edges: [] },
  }
}

/**
 * Mint a key for a new exploration's conversation.
 *
 * @returns A fresh, unique conversation key.
 */
export const newConversationKey = (): string => nanoid()

const FIRST_KEY = 'initial'

const initialState: TranscriptState = {
  byKey: { [FIRST_KEY]: emptyConversation() },
  activeKey: FIRST_KEY,
}

/** A stable empty source map, so `selectVisibleSourceRefs` never returns a
 *  fresh object (which would churn selector-driven re-renders). */
const NO_SOURCE_REFS: Record<string, SourceRef> = {}

/** A stable empty-beats reference, so `selectVisibleBeats` never returns a
 *  fresh array (which would churn selector-driven re-renders). */
const NO_BEATS: Beat[] = []

/** A stable empty conversation, for selectors reading a key that has gone. */
const NO_CONVERSATION: Conversation = emptyConversation()

/**
 * The conversation an action is addressed to.
 *
 * @param state The slice state.
 * @param key   The explicit key from `meta`, or undefined for "the active one".
 * @returns The conversation, or undefined when the key names one that has been
 *   dropped — a late event from a stream whose exploration the reader deleted,
 *   which must land nowhere rather than resurrect it.
 */
function target(state: TranscriptState, key: string | undefined): Conversation | undefined {
  return state.byKey[key ?? state.activeKey]
}

/** Actions carry an optional target key in `meta`. */
type Keyed = { key?: string }

/**
 * Build the `prepare` half of a keyed action: payload first, key second.
 *
 * @returns A prepare callback stamping the payload and `meta.key`.
 */
function keyed<Payload>() {
  return (payload: Payload, key?: string) => ({ payload, meta: { key } })
}

/**
 * The in-flight assistant message — streams always write to the last turn.
 *
 * @param conversation The conversation being written to.
 * @returns The last chat turn, or undefined on an empty chat.
 */
const lastMsg = (conversation: Conversation) => conversation.chat[conversation.chat.length - 1]

const transcriptSlice = createSlice({
  name: 'transcript',
  initialState,
  reducers: {
    /**
     * Begin a new exploration's conversation and show it.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the new conversation's key.
     */
    conversationStarted(state, action: PayloadAction<string>) {
      state.byKey[action.payload] = emptyConversation()
      state.activeKey = action.payload
    },
    /**
     * Show a conversation this sitting already holds, without touching it.
     *
     * This is what makes returning to a background exploration instant *and*
     * correct: its chat is whatever its stream has written since you left, not
     * the older copy on disk, so a re-read from the server would go backwards.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the key to show.
     */
    conversationActivated(state, action: PayloadAction<string>) {
      if (state.byKey[action.payload]) state.activeKey = action.payload
    },
    /**
     * Forget a conversation entirely (its exploration was deleted).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the key to drop.
     */
    conversationDropped(state, action: PayloadAction<string>) {
      delete state.byKey[action.payload]
    },
    /**
     * Take the pending discoveries a background stream accumulated, now that
     * its exploration is being opened.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the key whose buffer is being drained.
     */
    pendingDiscoveriesDrained(state, action: PayloadAction<string>) {
      const conversation = state.byKey[action.payload]
      if (conversation) conversation.pendingDiscoveries = { nodes: [], edges: [] }
    },
    /**
     * A stream starts in a conversation — the rail's "still working" mark, and
     * the autosave's signal that this conversation has not settled.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the stream id, and the conversation in `meta`.
     */
    streamStarted: {
      reducer(state, action: PayloadAction<string, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (conversation && !conversation.running.includes(action.payload)) {
          conversation.running.push(action.payload)
        }
      },
      prepare: keyed<string>(),
    },
    /**
     * A stream ends — finished, errored or aborted, all the same here.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the stream id, and the conversation in `meta`.
     */
    streamEnded: {
      reducer(state, action: PayloadAction<string, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (conversation) {
          conversation.running = conversation.running.filter((id) => id !== action.payload)
        }
      },
      prepare: keyed<string>(),
    },
    /**
     * A paper the agent found. Merged into the workspace when this
     * conversation is the active one (the workspace slice handles that); held
     * here when it is not, so a background find can't land on the graph the
     * reader is currently looking at.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the nodes and edges, and the conversation in `meta`.
     */
    backgroundDiscovery: {
      reducer(
        state,
        action: PayloadAction<{ nodes: GraphNode[]; edges: GraphEdge[] }, string, Keyed>,
      ) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        conversation.pendingDiscoveries.nodes.push(...action.payload.nodes)
        conversation.pendingDiscoveries.edges.push(...action.payload.edges)
      },
      prepare: keyed<{ nodes: GraphNode[]; edges: GraphEdge[] }>(),
    },
    /**
     * Settle any step still claiming to be in progress on the last turn.
     *
     * Dispatched when a run ends, however it ended. A trace chip's spinner is
     * driven by `pending`, which only the *finished* trace clears — so a run
     * that dies mid-step (a tool erroring out, the stream cut) leaves chips
     * spinning for a request that no longer exists, under a header that has
     * already gone back to saying "2 steps". The save settles these too, but
     * that is far too late for the reader watching the panel.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the conversation in `meta`.
     */
    tracesSettled: {
      reducer(state, action: PayloadAction<undefined, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (!msg?.trace) return
        for (const step of msg.trace) {
          if (step.pending) {
            step.pending = false
            step.ok = false
          }
        }
      },
      prepare: (key?: string) => ({ payload: undefined, meta: { key } }),
    },
    /**
     * An answer ended without producing any prose.
     *
     * Recorded on the turn rather than in component state, because the
     * commonest cause is a run the reader *left* — closed the tab, or moved on
     * and the stream died with the page. They come back to a turn that shows a
     * trace and then simply stops, and a message that lived in the panel's
     * `error` state would be long gone.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the reason, and the conversation in `meta`.
     */
    answerFailed: {
      reducer(state, action: PayloadAction<string, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        // Only an answer that produced nothing: a partial answer is real work
        // and reads as an answer, not as a failure.
        if (msg && msg.role === 'assistant' && !msg.text) msg.failed = action.payload
      },
      prepare: keyed<string>(),
    },
    /**
     * Drop a failed exchange so it can be asked again.
     *
     * Removes the failed assistant turn *and* the question that produced it,
     * so the retry re-runs through the ordinary `turnStarted` path and the
     * transcript ends up with one exchange rather than a graveyard of
     * attempts.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the failed turn's index, and the conversation in `meta`.
     */
    failedTurnDropped: {
      reducer(state, action: PayloadAction<number, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const index = action.payload
        const msg = conversation.chat[index]
        if (!msg || msg.role !== 'assistant') return
        // The user turn immediately before it goes too.
        const from = index > 0 && conversation.chat[index - 1].role === 'user' ? index - 1 : index
        conversation.chat.splice(from, index - from + 1)
      },
      prepare: keyed<number>(),
    },
    /**
     * A lecture starts streaming: make its mode the visible one and reset its
     * cache slot to empty, ready for the beats to stream in. The chat and every
     * other mode's cached beats are left untouched.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the lecture mode, and the conversation in `meta`.
     */
    lectureStarted: {
      reducer(state, action: PayloadAction<LectureMode, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        conversation.activeMode = action.payload
        conversation.lectures[action.payload] = []
        delete conversation.lectureSources[action.payload]
      },
      prepare: keyed<LectureMode>(),
    },
    /**
     * The library index for a lecture's `[Sn]` markers, which arrives before
     * its first beat. Carried per mode (like the beats) so a lecture
     * streaming in the background fills the right slot.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the mode and its map, and the conversation in `meta`.
     */
    lectureSourcesSet: {
      reducer(
        state,
        action: PayloadAction<
          { mode: LectureMode; refs: Record<string, SourceRef> },
          string,
          Keyed
        >,
      ) {
        const conversation = target(state, action.meta.key)
        if (conversation) conversation.lectureSources[action.payload.mode] = action.payload.refs
      },
      prepare: keyed<{ mode: LectureMode; refs: Record<string, SourceRef> }>(),
    },
    /**
     * One finished lecture beat arrives from the stream — appended to its own
     * mode's cache slot. The mode is carried explicitly (not read from
     * `activeMode`) so a lecture streaming in the background — deselected, or
     * running alongside another that's on screen — still fills the right slot.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the beat and mode, and the conversation in `meta`.
     */
    beatAdded: {
      reducer(state, action: PayloadAction<{ mode: LectureMode; beat: Beat }, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const { mode, beat } = action.payload
        ;(conversation.lectures[mode] ??= []).push(beat)
      },
      prepare: keyed<{ mode: LectureMode; beat: Beat }>(),
    },
    /**
     * Show an already-cached lecture without re-fetching it (clicking a mode
     * button whose lecture was played earlier this session).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the mode, and the conversation in `meta`.
     */
    lectureShown: {
      reducer(state, action: PayloadAction<LectureMode, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (conversation) conversation.activeMode = action.payload
      },
      prepare: keyed<LectureMode>(),
    },
    /**
     * Hide the visible lecture (deselecting its button) while keeping its beats
     * cached, so re-selecting the mode reloads them instantly.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the conversation in `meta`.
     */
    lectureHidden: {
      reducer(state, action: PayloadAction<undefined, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (conversation) conversation.activeMode = null
      },
      prepare: (key?: string) => ({ payload: undefined, meta: { key } }),
    },
    /**
     * Drop a mode's cached beats (a stream that was aborted or errored before
     * finishing, so it should regenerate on the next click rather than reload a
     * partial lecture). Also hides it if it was the visible one.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the mode, and the conversation in `meta`.
     */
    lectureDropped: {
      reducer(state, action: PayloadAction<LectureMode, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        delete conversation.lectures[action.payload]
        delete conversation.lectureSources[action.payload]
        if (conversation.activeMode === action.payload) conversation.activeMode = null
      },
      prepare: keyed<LectureMode>(),
    },
    /**
     * A question begins: the user turn plus the empty assistant turn the
     * answer streams into.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the question, and the conversation in `meta`.
     */
    turnStarted: {
      reducer(state, action: PayloadAction<string, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        conversation.chat.push({ role: 'user', text: action.payload })
        conversation.chat.push({ role: 'assistant', text: '' })
      },
      prepare: keyed<string>(),
    },
    /**
     * A streamed answer token lands on the in-flight turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the token, and the conversation in `meta`.
     */
    tokenAppended: {
      reducer(state, action: PayloadAction<string, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.text += action.payload
      },
      prepare: keyed<string>(),
    },
    /**
     * Replace the in-flight turn's text outright.
     *
     * `tokenAppended`'s counterpart, for a path whose later text *supersedes*
     * its earlier text rather than continuing it: direct search paints the
     * local cache's hits the moment they resolve, then swaps in the scout's
     * full list when it lands. Appending would show the same papers twice.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the replacement, and the conversation in `meta`.
     */
    answerSet: {
      reducer(state, action: PayloadAction<string, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.text = action.payload
      },
      prepare: keyed<string>(),
    },
    /**
     * A researcher trace chip (read/expand/search) lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the trace event, and the conversation in `meta`.
     */
    traceAdded: {
      reducer(state, action: PayloadAction<TraceEvent, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (!msg) return
        const trace = msg.trace ?? []
        // A scout announces itself before it starts (a `pending` trace) so a run
        // several provider calls deep isn't a silent gap, then reports back when
        // it lands. Those are one step, so the finished trace REPLACES its
        // pending twin rather than appending beside it — otherwise every scouted
        // search leaves two chips saying the same thing.
        const incoming = action.payload
        const twin = trace.findIndex((event) => event.pending && event.action === incoming.action)
        if (!incoming.pending && twin !== -1) {
          msg.trace = trace.map((event, index) => (index === twin ? incoming : event))
          return
        }
        msg.trace = [...trace, incoming]
      },
      prepare: keyed<TraceEvent>(),
    },
    /**
     * An inline answer figure lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the figure, and the conversation in `meta`.
     */
    figureAdded: {
      reducer(state, action: PayloadAction<AnswerFigure, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.figures = [...(msg.figures ?? []), action.payload]
      },
      prepare: keyed<AnswerFigure>(),
    },
    /**
     * The library-retrieval summary (graph-free chat) lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the summary, and the conversation in `meta`.
     */
    retrieveSet: {
      reducer(state, action: PayloadAction<RetrieveEvent, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.retrieve = action.payload
      },
      prepare: keyed<RetrieveEvent>(),
    },
    /**
     * The answer's grounding set (cited node ids) lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the cited ids, and the conversation in `meta`.
     */
    citedSet: {
      reducer(state, action: PayloadAction<string[], string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.cited = action.payload
      },
      prepare: keyed<string[]>(),
    },
    /**
     * Attach the resolved `[n]` → node-id map once the answer finishes
     * streaming (see `useConversation.ask`). Written to the last turn, like the
     * other per-answer fields.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the map, and the conversation in `meta`.
     */
    graphRefsSet: {
      reducer(state, action: PayloadAction<Record<string, string>, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.graphRefs = action.payload
      },
      prepare: keyed<Record<string, string>>(),
    },
    /**
     * Attach the library index resolving this answer's `[Sn]` markers. Unlike
     * `graphRefsSet`, it arrives *before* the prose (the backend resolves it as
     * soon as retrieval settles), so markers render as real titles while the
     * answer is still streaming.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the map, and the conversation in `meta`.
     */
    sourceRefsSet: {
      reducer(state, action: PayloadAction<Record<string, SourceRef>, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.sourceRefs = action.payload
      },
      prepare: keyed<Record<string, SourceRef>>(),
    },
    /**
     * What actually grounded the finished answer — searched or not, what came
     * back, what it ended up citing. Observed server-side, so it lands with
     * the other end-of-answer fields.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the counts, and the conversation in `meta`.
     */
    provenanceSet: {
      reducer(state, action: PayloadAction<ProvenanceEvent, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.provenance = action.payload
      },
      prepare: keyed<ProvenanceEvent>(),
    },
    /**
     * The papers this answer's `[n]` markers name, resolved to title + URL —
     * the fallback that keeps a citation readable when there's no graph to
     * resolve it against.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the map, and the conversation in `meta`.
     */
    paperRefsSet: {
      reducer(state, action: PayloadAction<Record<string, PaperRef>, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (!conversation) return
        const msg = lastMsg(conversation)
        if (msg) msg.paperRefs = action.payload
      },
      prepare: keyed<Record<string, PaperRef>>(),
    },
    /**
     * Clear only the Q&A chat, leaving every cached lecture untouched — the
     * Clear button's behavior when no lecture is selected. (A selected lecture
     * is cleared on its own via `lectureDropped`.)
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the conversation in `meta`.
     */
    chatCleared: {
      reducer(state, action: PayloadAction<undefined, string, Keyed>) {
        const conversation = target(state, action.meta.key)
        if (conversation) conversation.chat = []
      },
      prepare: (key?: string) => ({ payload: undefined, meta: { key } }),
    },
  },
  extraReducers: (builder) => {
    builder
      // A new graph keeps your conversation and drops the lectures. The two
      // halves of this slice belong to different owners: the chat is the
      // user's — they asked those questions, and nothing about loading another
      // graph says they're finished with the answers, so clearing it is theirs
      // to do (the Clear button, or Home). Lectures belong to the *graph*: a
      // lecture narrates the neighborhood you built, and its beats point at
      // that graph's nodes, so carrying one onto a different graph would
      // narrate papers that aren't there.
      //
      // This is only safe because citations degrade — an `[n]` whose paper
      // isn't on the graph any more renders greyed and inert rather than
      // silently highlighting nothing (see `teacher/transcript/README.md`).
      // Before that, a surviving transcript meant a screenful of dead
      // pointers, which is why this used to reset wholesale.
      //
      // Scoped to the ACTIVE conversation: loading a graph is something the
      // reader did here, and it says nothing about an exploration still
      // running in the background.
      .addCase(loadGraph.fulfilled, (state) => {
        const conversation = state.byKey[state.activeKey]
        if (!conversation) return
        conversation.lectures = {}
        conversation.lectureSources = {}
        conversation.activeMode = null
      })
      // ✎ New Exploration: a brand-new conversation, with the old one left
      // exactly as it was — it may still be streaming, and it is still listed
      // in the rail.
      .addCase(workspaceCleared, (state, action) => {
        const key = action.payload?.conversationKey ?? newConversationKey()
        state.byKey[key] = emptyConversation()
        state.activeKey = key
      })
      // A restored exploration brings its saved transcript along, under the
      // key the restore minted for it.
      .addCase(restoreSession.fulfilled, (state, action) => {
        const { conversationKey, transcript } = action.payload
        state.byKey[conversationKey] = { ...emptyConversation(), ...transcript }
        state.activeKey = conversationKey
      })
  },
})

export const {
  answerFailed,
  tracesSettled,
  failedTurnDropped,
  conversationStarted,
  conversationActivated,
  conversationDropped,
  pendingDiscoveriesDrained,
  streamStarted,
  streamEnded,
  backgroundDiscovery,
  lectureStarted,
  lectureSourcesSet,
  beatAdded,
  lectureShown,
  lectureHidden,
  lectureDropped,
  turnStarted,
  tokenAppended,
  answerSet,
  traceAdded,
  figureAdded,
  retrieveSet,
  citedSet,
  graphRefsSet,
  sourceRefsSet,
  provenanceSet,
  paperRefsSet,
  chatCleared,
} = transcriptSlice.actions
export default transcriptSlice.reducer

/**
 * The conversation on screen. Everything the teacher panel renders reads
 * through here, so a background stream writing to another key changes nothing
 * the reader is looking at.
 *
 * @param state The root state.
 * @returns The active conversation, or a stable empty one if it has gone.
 */
export const selectConversation = (state: { transcript: TranscriptState }): Conversation =>
  state.transcript.byKey[state.transcript.activeKey] ?? NO_CONVERSATION

/**
 * The active conversation, for the autosave.
 *
 * @param state The root state.
 * @returns The active conversation.
 */
export const selectTranscript = selectConversation

/**
 * Which explorations still have a stream running, by conversation key — what
 * the rail marks as still working.
 *
 * @param state The root state.
 * @returns The keys of conversations with at least one live stream.
 */
export const selectRunningKeys = (state: { transcript: TranscriptState }): string[] =>
  Object.entries(state.transcript.byKey)
    .filter(([, conversation]) => conversation.running.length > 0)
    .map(([key]) => key)

/**
 * The beats of the currently-shown lecture, or a stable empty array when no
 * mode is selected — what the panel renders.
 *
 * @param state The root state.
 * @returns The visible lecture's beats.
 */
export const selectVisibleBeats = (state: { transcript: TranscriptState }): Beat[] => {
  const { activeMode, lectures } = selectConversation(state)
  return (activeMode && lectures[activeMode]) || NO_BEATS
}

/**
 * The library index for the currently-shown lecture's `[Sn]` markers, or a
 * stable empty map when no mode is selected (or the lecture cited no library
 * passage).
 *
 * @param state The root state.
 * @returns The visible lecture's `[Sn]` index → source map.
 */
export const selectVisibleSourceRefs = (state: {
  transcript: TranscriptState
}): Record<string, SourceRef> => {
  const { activeMode, lectureSources } = selectConversation(state)
  return (activeMode && lectureSources[activeMode]) || NO_SOURCE_REFS
}
