/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The uploaded source library — ONE copy of "what's in the library", shared by
 * the Sources drawer (which changes it) and the teacher panel's source-scope
 * picker (which reads it).
 *
 * It became a slice for the same reason the lecture-scope picker reads
 * `transcript.lectures`: the two surfaces used to fetch their own copies, each
 * once — the drawer's uploads refreshed only the drawer, so the scope picker
 * (shown at two or more sources) didn't learn a second source existed until a
 * full page reload. Live state the drawer writes and the panel watches is
 * genuinely cross-cutting — exactly what the Phase 6 state directive sends to
 * the store.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import type { RootState } from './index'
import { listSources, type Source } from '../api'

/** The library slice's state. */
export interface LibraryState {
  /** Local embeddings + sqlite-vec loaded — false disables the whole feature. */
  available: boolean
  /** The uploaded sources, as of the last {@link loadLibrary}. */
  sources: Source[]
  /** A load has completed at least once — gates lazy first fetches, so two
   *  mounted readers don't each fire one. */
  loaded: boolean
  /** A load is in flight (the drawer's "Loading…" hint). */
  loading: boolean
}

const initialState: LibraryState = {
  available: true,
  sources: [],
  loaded: false,
  loading: false,
}

/** (Re-)fetch the library: on first read, drawer open, and after every
 *  upload / URL ingest / delete. `listSources` never rejects — failures come
 *  back as the disabled shape — so `fulfilled` is the only case that matters. */
export const loadLibrary = createAsyncThunk('library/load', () => listSources())

const library = createSlice({
  name: 'library',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(loadLibrary.pending, (state) => {
        state.loading = true
      })
      .addCase(loadLibrary.fulfilled, (state, action) => {
        state.available = action.payload.available
        state.sources = action.payload.sources
        state.loaded = true
        state.loading = false
      })
  },
})

/**
 * The whole slice — the drawer reads all four fields, the teacher panel
 * destructures the two it needs.
 *
 * @param state The root state.
 * @returns The library slice's state.
 */
export const selectLibrary = (state: RootState) => state.library

export default library.reducer
