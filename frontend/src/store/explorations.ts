/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Exploration ownership and atomic thread navigation.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { createAction, createSlice, nanoid } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import type { SessionData } from '../api'
import type { WorkspaceState } from './workspace'

export interface ThreadRecord {
  id: string
  title: string
  identity: string | null
  data: SessionData
  workspace?: WorkspaceState
  summary?: string
  summarizedThrough?: number
  origin?: string
}
export interface ExplorationRecord {
  id: string
  title: string
  threads: ThreadRecord[]
  activeThreadId: string
  revision: number
}
export interface ExplorationsState {
  activeId: string
  byId: Record<string, ExplorationRecord>
}

/** Start an exploration with its permanent General thread.
 * @param id Optional stable saved-row id.
 * @returns Empty exploration.
 */
export function newExploration(id = nanoid()): ExplorationRecord {
  const threadId = nanoid()
  return {
    id,
    title: 'Untitled exploration',
    activeThreadId: threadId,
    revision: 0,
    threads: [
      { id: threadId, title: 'General', identity: null, data: { chat: [], layout: 'timeline' } },
    ],
  }
}

export const explorationOpened = createAction<ExplorationRecord>('explorations/opened')
export const threadActivated = createAction<{
  explorationId: string
  thread: ThreadRecord
  outgoingId: string
  outgoing: WorkspaceState
  requestId?: string
}>('explorations/threadActivated')
const first = newExploration()
first.threads[0].id = 'initial'
first.activeThreadId = 'initial'
const initialState: ExplorationsState = { activeId: first.id, byId: { [first.id]: first } }
const slice = createSlice({
  name: 'explorations',
  initialState,
  reducers: {
    /** Remove a graph thread; General is permanent.
     * @param state Exploration state.
     * @param action Thread id to remove.
     */
    threadRemoved(state, action: PayloadAction<string>) {
      for (const record of Object.values(state.byId)) {
        const thread = record.threads.find((item) => item.id === action.payload)
        if (!thread?.identity) continue
        record.threads = record.threads.filter((item) => item.id !== thread.id)
        record.revision++
      }
    },
    /** Mark an intentional view edit for autosave.
     * @param state Exploration state.
     */
    threadEdited(state) {
      const record = state.byId[state.activeId]
      if (record) record.revision++
    },
    /** Rename without triggering model-generated title churn.
     * @param state Exploration state.
     * @param action Target and new title.
     */
    explorationRenamed(state, action: PayloadAction<{ id: string; title: string }>) {
      const record = state.byId[action.payload.id]
      if (record) {
        record.title = action.payload.title
        record.revision++
      }
    },
    /** Remove local ownership so a pending save cannot resurrect a deletion.
     * @param state Exploration state.
     * @param action Removed id.
     */
    explorationRemoved(state, action: PayloadAction<string>) {
      delete state.byId[action.payload]
    },
    /** Persist a reader's graph-thread title.
     * @param state Exploration state.
     * @param action Thread and title.
     */
    threadRenamed(state, action: PayloadAction<{ id: string; title: string }>) {
      const record = state.byId[state.activeId]
      const thread = record.threads.find((item) => item.id === action.payload.id)
      if (thread?.identity) {
        thread.title = action.payload.title
        record.revision++
      }
    },
    /** Store a summary only for the revision the summarizer actually read.
     * @param state Exploration state.
     * @param action Summary with its owning thread and revision.
     */
    threadSummarized(
      state,
      action: PayloadAction<{
        explorationId: string
        id: string
        summary: string
        through: number
      }>,
    ) {
      const record = state.byId[action.payload.explorationId]
      const thread = record?.threads.find((item) => item.id === action.payload.id)
      if (thread) {
        thread.summary = action.payload.summary
        thread.summarizedThrough = action.payload.through
        record.revision++
      }
    },
  },
  extraReducers: (builder) =>
    builder
      .addCase(explorationOpened, (state, action) => {
        state.byId[action.payload.id] = action.payload
        state.activeId = action.payload.id
      })
      .addCase(threadActivated, (state, action) => {
        const record = state.byId[action.payload.explorationId]
        if (!record) return
        const outgoing = record.threads.find((item) => item.id === action.payload.outgoingId)
        if (outgoing) outgoing.workspace = action.payload.outgoing
        if (!record.threads.some((item) => item.id === action.payload.thread.id))
          record.threads.push(action.payload.thread)
        record.activeThreadId = action.payload.thread.id
        record.revision++
        state.activeId = record.id
      })
      .addMatcher(
        (action) => action.type === 'transcript/chatCleared',
        (state, action) => {
          const key = (action as { meta?: { key?: string } }).meta?.key
          for (const record of Object.values(state.byId)) {
            const thread = record.threads.find(
              (item) => item.id === (key ?? state.byId[state.activeId]?.activeThreadId),
            )
            if (thread) {
              delete thread.summary
              delete thread.summarizedThrough
              record.revision++
            }
          }
        },
      ),
})
export const {
  threadRemoved,
  threadEdited,
  explorationRenamed,
  explorationRemoved,
  threadRenamed,
  threadSummarized,
} = slice.actions
export default slice.reducer
