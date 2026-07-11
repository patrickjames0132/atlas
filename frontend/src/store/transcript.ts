/**
 * The transcript slice: the teacher's conversation — chat turns and lecture
 * beats. The teacher panel dispatches as streams arrive; Save selects it;
 * restore repopulates it.
 *
 * This slice is why the old `onStateChange`/`teacherStateRef` plumbing died:
 * the transcript used to live in Teacher.tsx with a live duplicate hoisted
 * into Atlas purely so Save could read it. Now there is exactly one copy,
 * owned by neither component.
 */

import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import type { AnswerFigure, Beat, ChatMsg, LectureMode, RetrieveEvent, TraceEvent } from '../api'
import { loadGraph, restoreSession, workspaceCleared } from './workspace'

export interface TranscriptState {
  chat: ChatMsg[]
  /**
   * Per-mode lecture cache: a mode maps to its generated beats once it has
   * been played. Re-selecting a cached mode reloads its beats without a
   * re-fetch; the four modes are independent, so switching between them is
   * instant after the first play.
   */
  lectures: Partial<Record<LectureMode, Beat[]>>
  /** Which cached lecture is currently shown on screen (null = none visible —
   *  every mode button is deselected). */
  activeMode: LectureMode | null
}

const initialState: TranscriptState = { chat: [], lectures: {}, activeMode: null }

/** A stable empty-beats reference, so `selectVisibleBeats` never returns a
 *  fresh array (which would churn selector-driven re-renders). */
const NO_BEATS: Beat[] = []

/**
 * The in-flight assistant message — streams always write to the last turn.
 *
 * @param state The transcript slice state.
 * @returns The last chat turn, or undefined on an empty chat.
 */
const lastMsg = (state: TranscriptState) => state.chat[state.chat.length - 1]

const transcriptSlice = createSlice({
  name: 'transcript',
  initialState,
  reducers: {
    /**
     * A lecture starts streaming: make its mode the visible one and reset its
     * cache slot to empty, ready for the beats to stream in. The chat and every
     * other mode's cached beats are left untouched.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the lecture mode being played.
     */
    lectureStarted(state, action: PayloadAction<LectureMode>) {
      state.activeMode = action.payload
      state.lectures[action.payload] = []
    },
    /**
     * One finished lecture beat arrives from the stream — appended to its own
     * mode's cache slot. The mode is carried explicitly (not read from
     * `activeMode`) so a lecture streaming in the background — deselected, or
     * running alongside another that's on screen — still fills the right slot.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the beat and the mode it belongs to.
     */
    beatAdded(state, action: PayloadAction<{ mode: LectureMode; beat: Beat }>) {
      const { mode, beat } = action.payload
      ;(state.lectures[mode] ??= []).push(beat)
    },
    /**
     * Show an already-cached lecture without re-fetching it (clicking a mode
     * button whose lecture was played earlier this session).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the mode to reveal.
     */
    lectureShown(state, action: PayloadAction<LectureMode>) {
      state.activeMode = action.payload
    },
    /**
     * Hide the visible lecture (deselecting its button) while keeping its beats
     * cached, so re-selecting the mode reloads them instantly.
     *
     * @param state The slice state (mutated via immer).
     */
    lectureHidden(state) {
      state.activeMode = null
    },
    /**
     * Drop a mode's cached beats (a stream that was aborted or errored before
     * finishing, so it should regenerate on the next click rather than reload a
     * partial lecture). Also hides it if it was the visible one.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the mode to drop.
     */
    lectureDropped(state, action: PayloadAction<LectureMode>) {
      delete state.lectures[action.payload]
      if (state.activeMode === action.payload) state.activeMode = null
    },
    /**
     * A question begins: the user turn plus the empty assistant turn the
     * answer streams into.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the user's question text.
     */
    turnStarted(state, action: PayloadAction<string>) {
      state.chat.push({ role: 'user', text: action.payload })
      state.chat.push({ role: 'assistant', text: '' })
    },
    /**
     * A streamed answer token lands on the in-flight turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the token text.
     */
    tokenAppended(state, action: PayloadAction<string>) {
      const msg = lastMsg(state)
      if (msg) msg.text += action.payload
    },
    /**
     * A researcher trace chip (read/expand/search) lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the trace event.
     */
    traceAdded(state, action: PayloadAction<TraceEvent>) {
      const msg = lastMsg(state)
      if (msg) msg.trace = [...(msg.trace ?? []), action.payload]
    },
    /**
     * An inline answer figure lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the attached figure.
     */
    figureAdded(state, action: PayloadAction<AnswerFigure>) {
      const msg = lastMsg(state)
      if (msg) msg.figures = [...(msg.figures ?? []), action.payload]
    },
    /**
     * The library-retrieval summary (graph-free chat) lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the retrieval summary.
     */
    retrieveSet(state, action: PayloadAction<RetrieveEvent>) {
      const msg = lastMsg(state)
      if (msg) msg.retrieve = action.payload
    },
    /**
     * The answer's grounding set (cited node ids) lands on the turn.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the cited node ids.
     */
    citedSet(state, action: PayloadAction<string[]>) {
      const msg = lastMsg(state)
      if (msg) msg.cited = action.payload
    },
    /**
     * Attach the resolved `[n]` → node-id map once the answer finishes
     * streaming (see `useConversation.ask`). Written to the last turn, like the
     * other per-answer fields.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the marker → node-id map.
     */
    refsSet(state, action: PayloadAction<Record<string, string>>) {
      const msg = lastMsg(state)
      if (msg) msg.refs = action.payload
    },
    /**
     * Clear only the Q&A chat, leaving every cached lecture untouched — the
     * Clear button's behavior when no lecture is selected. (A selected lecture
     * is cleared on its own via `lectureDropped`.)
     *
     * @param state The slice state (mutated via immer).
     */
    chatCleared(state) {
      state.chat = []
    },
  },
  extraReducers: (builder) => {
    builder
      // A fresh graph starts a fresh conversation; Home clears everything.
      .addCase(loadGraph.fulfilled, () => initialState)
      .addCase(workspaceCleared, () => initialState)
      // A restored session brings its saved transcript along.
      .addCase(restoreSession.fulfilled, (_state, action) => action.payload.transcript)
  },
})

export const {
  lectureStarted,
  beatAdded,
  lectureShown,
  lectureHidden,
  lectureDropped,
  turnStarted,
  tokenAppended,
  traceAdded,
  figureAdded,
  retrieveSet,
  citedSet,
  refsSet,
  chatCleared,
} = transcriptSlice.actions
export default transcriptSlice.reducer

/**
 * The whole transcript slice (chat + lecture cache), for Save.
 *
 * @param state The root state.
 * @returns The transcript slice.
 */
export const selectTranscript = (state: { transcript: TranscriptState }) => state.transcript

/**
 * The beats of the currently-shown lecture, or a stable empty array when no
 * mode is selected — what the panel renders.
 *
 * @param state The root state.
 * @returns The visible lecture's beats.
 */
export const selectVisibleBeats = (state: { transcript: TranscriptState }): Beat[] => {
  const { activeMode, lectures } = state.transcript
  return (activeMode && lectures[activeMode]) || NO_BEATS
}
