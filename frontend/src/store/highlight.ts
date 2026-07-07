/**
 * The highlight slice: which papers the teacher is currently talking about
 * (the active beat's nodes, or an answer's cited papers). The teacher writes
 * it; the canvas glows them. Stored as an array (serializable); the canvas
 * selects it as a memoized Set.
 */

import { createSelector, createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { loadGraph, restoreSession, workspaceCleared } from './workspace'

export interface HighlightState {
  ids: string[]
}

const initialState: HighlightState = { ids: [] }

const highlightSlice = createSlice({
  name: 'highlight',
  initialState,
  reducers: {
    highlightSet(state, action: PayloadAction<string[]>) {
      state.ids = action.payload
    },
  },
  extraReducers: (builder) => {
    // A new/restored graph starts unlit.
    builder
      .addCase(loadGraph.fulfilled, () => initialState)
      .addCase(restoreSession.fulfilled, () => initialState)
      .addCase(workspaceCleared, () => initialState)
  },
})

export const { highlightSet } = highlightSlice.actions
export default highlightSlice.reducer

/** The lit node ids as a Set — memoized so the canvas doesn't re-render on
 * every unrelated store change. */
export const selectHighlightSet = createSelector(
  (state: { highlight: HighlightState }) => state.highlight.ids,
  (ids) => new Set(ids),
)
