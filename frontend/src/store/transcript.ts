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
import type { AnswerFigure, Beat, ChatMsg, RetrieveEvent, TraceEvent } from '../api'
import { loadGraph, restoreSession, workspaceCleared } from './workspace'

export interface TranscriptState {
  chat: ChatMsg[]
  beats: Beat[]
}

const initialState: TranscriptState = { chat: [], beats: [] }

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
     * A lecture starts: clear the beats, keep the chat.
     *
     * @param state The slice state (mutated via immer).
     */
    lectureStarted(state) {
      state.beats = []
    },
    /**
     * One finished lecture beat arrives from the stream.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the completed beat.
     */
    beatAdded(state, action: PayloadAction<Beat>) {
      state.beats.push(action.payload)
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
     * Wipe the conversation (the panel's Clear button).
     *
     * @returns The pristine empty transcript.
     */
    cleared() {
      return initialState
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
  turnStarted,
  tokenAppended,
  traceAdded,
  figureAdded,
  retrieveSet,
  citedSet,
  refsSet,
  cleared,
} = transcriptSlice.actions
export default transcriptSlice.reducer

/**
 * The whole transcript slice (chat + beats), for rendering and Save.
 *
 * @param state The root state.
 * @returns The transcript slice.
 */
export const selectTranscript = (state: { transcript: TranscriptState }) => state.transcript
