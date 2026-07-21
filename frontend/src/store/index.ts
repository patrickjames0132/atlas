/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The Redux store: four slices for the app's genuinely cross-cutting state,
 * everything else stays component-local (the Phase 6 state directive).
 *
 *   workspace  — the loaded graph, discoveries, layout + load/restore/save
 *   transcript — the teacher's conversation (chat, beats)
 *   highlight  — the papers the teacher is currently talking about
 *   library    — the uploaded sources (drawer writes, scope picker reads)
 *
 * NOT here, by design: the sim dataset `Base` (mutable, canvas-owned),
 * declutter filters, hover, selection, drawer visibility, search state —
 * each lives with the component that renders it.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { configureStore } from '@reduxjs/toolkit'
import { useDispatch, useSelector } from 'react-redux'
import highlight from './highlight'
import library from './library'
import transcript from './transcript'
import workspace from './workspace'

export const store = configureStore({
  reducer: { workspace, transcript, highlight, library },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch

/** Typed hooks — components use these, never the raw react-redux ones. */
export const useAppDispatch = useDispatch.withTypes<AppDispatch>()
export const useAppSelector = useSelector.withTypes<RootState>()
