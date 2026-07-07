/**
 * The transcript slice: the teacher's conversation — chat turns, lecture
 * beats, and the history-backfill trace. The teacher panel dispatches as
 * streams arrive; Save selects it; restore repopulates it.
 *
 * This slice is why the old `onStateChange`/`teacherStateRef` plumbing died:
 * the transcript used to live in Teacher.tsx with a live duplicate hoisted
 * into Atlas purely so Save could read it. Now there is exactly one copy,
 * owned by neither component.
 */

import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import type {
  AnswerFigure,
  BackfillTrace,
  Beat,
  ChatMsg,
  RetrieveEvent,
  TraceEvent,
} from '../api'
import { loadGraph, restoreSession, workspaceCleared } from './workspace'

export interface TranscriptState {
  chat: ChatMsg[]
  beats: Beat[]
  histTrace: BackfillTrace[]
}

const initialState: TranscriptState = { chat: [], beats: [], histTrace: [] }

/** The in-flight assistant message — streams always write to the last turn. */
const lastMsg = (state: TranscriptState) => state.chat[state.chat.length - 1]

const transcriptSlice = createSlice({
  name: 'transcript',
  initialState,
  reducers: {
    /** A lecture starts: clear beats + backfill trace, keep the chat. */
    lectureStarted(state) {
      state.beats = []
      state.histTrace = []
    },
    beatAdded(state, action: PayloadAction<Beat>) {
      state.beats.push(action.payload)
    },
    histTraceAdded(state, action: PayloadAction<BackfillTrace>) {
      state.histTrace.push(action.payload)
    },
    /** A question begins: the user turn plus the empty assistant turn the
     * answer streams into. */
    turnStarted(state, action: PayloadAction<string>) {
      state.chat.push({ role: 'user', text: action.payload })
      state.chat.push({ role: 'assistant', text: '' })
    },
    tokenAppended(state, action: PayloadAction<string>) {
      const msg = lastMsg(state)
      if (msg) msg.text += action.payload
    },
    traceAdded(state, action: PayloadAction<TraceEvent>) {
      const msg = lastMsg(state)
      if (msg) msg.trace = [...(msg.trace ?? []), action.payload]
    },
    figureAdded(state, action: PayloadAction<AnswerFigure>) {
      const msg = lastMsg(state)
      if (msg) msg.figures = [...(msg.figures ?? []), action.payload]
    },
    retrieveSet(state, action: PayloadAction<RetrieveEvent>) {
      const msg = lastMsg(state)
      if (msg) msg.retrieve = action.payload
    },
    citedSet(state, action: PayloadAction<string[]>) {
      const msg = lastMsg(state)
      if (msg) msg.cited = action.payload
    },
    /** Wipe the conversation (the panel's Clear button). */
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
  histTraceAdded,
  turnStarted,
  tokenAppended,
  traceAdded,
  figureAdded,
  retrieveSet,
  citedSet,
  cleared,
} = transcriptSlice.actions
export default transcriptSlice.reducer

export const selectTranscript = (state: { transcript: TranscriptState }) =>
  state.transcript
