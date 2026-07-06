/**
 * The Redux store: three slices for the app's genuinely cross-cutting state,
 * everything else stays component-local (the Phase 6 state directive).
 *
 *   workspace  — the loaded graph, discoveries, layout + load/restore/save
 *   transcript — the teacher's conversation (chat, beats, backfill trace)
 *   highlight  — the papers the teacher is currently talking about
 *
 * NOT here, by design: the sim dataset `Base` (mutable, canvas-owned),
 * declutter filters, hover, selection, drawer visibility, search state —
 * each lives with the component that renders it.
 */

import { configureStore } from '@reduxjs/toolkit'
import { useDispatch, useSelector } from 'react-redux'
import highlight from './highlight'
import transcript from './transcript'
import workspace from './workspace'

export const store = configureStore({
  reducer: { workspace, transcript, highlight },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch

/** Typed hooks — components use these, never the raw react-redux ones. */
export const useAppDispatch = useDispatch.withTypes<AppDispatch>()
export const useAppSelector = useSelector.withTypes<RootState>()
