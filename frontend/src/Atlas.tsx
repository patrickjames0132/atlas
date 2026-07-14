/**
 * Atlas — the shell. Composes the header, the drawers, the graph explorer,
 * and the teacher panel; owns only what it alone renders: drawer visibility,
 * the library count, the seed-search instance (its three render sites — the
 * header form, the hit-list overlay, the submit routing — all live here),
 * and the loading/error/hint overlays.
 *
 * Everything cross-cutting lives in the store (see `store/README.md`):
 * the workspace (graph + discoveries + layout), the transcript, and the
 * highlight ids. The old Atlas's transcript-duplicating refs and remount
 * plumbing died with that move — the teacher remounts per workspace epoch,
 * and Save reads the store, not a hoisted copy.
 */

import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { listSources } from './api'
import { ID_RE } from './graph/model'
import { useAppDispatch, useAppSelector } from './store'
import {
  errorSet,
  loadGraph,
  restoreSession,
  saveWorkspace,
  switchProvider,
  workspaceCleared,
} from './store/workspace'
import { useSeedSearch } from './search/useSeedSearch'
import AtlasHeader from './header/AtlasHeader'
import GraphExplorer from './graph/GraphExplorer'
import HitList from './search/HitList'
import Teacher from './teacher/Teacher'
import Sources from './library/Sources'
import Sessions from './sessions/Sessions'
import './atlas.css'

/**
 * Render the app shell: header, drawers, and the graph area with its overlays.
 *
 * @returns The whole application tree.
 */
export default function Atlas() {
  const dispatch = useAppDispatch()
  const { graph, epoch, loading, buildProgress, error, provider } = useAppSelector(
    (state) => state.workspace,
  )

  // Drawer visibility + the assistant toggle — shell-local UI.
  const [showSources, setShowSources] = useState(false)
  const [showSessions, setShowSessions] = useState(false)
  const [assistantOpen, setAssistantOpen] = useState(false)
  // Gates the graph-free library-chat entry point; refreshed when the
  // Sources drawer closes (they may have added/removed sources).
  const [libraryCount, setLibraryCount] = useState(0)

  const refreshLibraryCount = useCallback(() => {
    listSources()
      .then((res) => setLibraryCount(res.sources.length))
      .catch(() => {})
  }, [])
  useEffect(refreshLibraryCount, [refreshLibraryCount])

  // Surface the teacher whenever a graph loads or a session restores. (Home
  // also bumps the epoch, but with no graph there's nothing to surface.)
  useEffect(() => {
    if (epoch > 0 && graph) setAssistantOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [epoch])

  // Seed search: query + optional filters, cache-first local / live S2 hits.
  // Search errors share the workspace error overlay with graph-load errors.
  const onSearchError = useCallback(
    (message: string | null) => {
      dispatch(errorSet(message))
    },
    [dispatch],
  )
  const {
    query,
    setQuery,
    filters,
    setFilters,
    hits,
    localHits,
    searching,
    liveFailed,
    runSearch,
    clearHits,
  } = useSeedSearch(onSearchError)

  /** Load a graph and dismiss any open search results. */
  const pickSeed = useCallback(
    (seed: string) => {
      clearHits()
      dispatch(loadGraph({ seed }))
    },
    [clearHits, dispatch],
  )

  /** Route the search form: a pasted arXiv id/URL jumps straight to its
   * graph; anything else runs the keyword search. */
  const onSubmit = useCallback(
    (event: FormEvent) => {
      event.preventDefault()
      const trimmed = query.trim()
      if (!trimmed) return
      if (ID_RE.test(trimmed)) pickSeed(trimmed)
      else runSearch(trimmed)
    },
    [query, pickSeed, runSearch],
  )

  /** Home: back to the page-load default — no graph, no results, no panel. */
  const goHome = useCallback(() => {
    dispatch(workspaceCleared())
    clearHits()
    setQuery('')
    setAssistantOpen(false)
  }, [dispatch, clearHits, setQuery])

  const hasGraph = !!graph && graph.nodes.length > 0

  return (
    <div className="atlas">
      <AtlasHeader
        query={query}
        onQueryChange={setQuery}
        onSubmit={onSubmit}
        searching={searching}
        loadingGraph={loading}
        filters={filters}
        onFilters={setFilters}
        provider={provider}
        onProviderChange={(next) => dispatch(switchProvider(next))}
        seedTitle={graph?.seed.title ?? null}
        onHome={goHome}
        onOpenSources={() => setShowSources(true)}
        assistantAvailable={hasGraph || libraryCount > 0}
        assistantOpen={assistantOpen}
        onToggleAssistant={() => setAssistantOpen((prev) => !prev)}
        onOpenSessions={() => setShowSessions(true)}
      />

      <Sources
        open={showSources}
        onClose={() => {
          setShowSources(false)
          refreshLibraryCount()
        }}
      />

      <Sessions
        open={showSessions}
        onClose={() => setShowSessions(false)}
        onSave={(name, id) => dispatch(saveWorkspace({ name, id })).unwrap()}
        onOpen={(id) => {
          dispatch(restoreSession(id))
          setShowSessions(false)
        }}
        canSave={hasGraph}
        defaultName={graph?.seed.title ?? ''}
      />

      <div className="atlas-body">
        <GraphExplorer>
          <HitList
            hits={hits}
            localHits={localHits}
            searching={searching}
            liveFailed={liveFailed}
            onPick={pickSeed}
            onClose={clearHits}
          />

          {(loading || (error && !hits)) && hasGraph && <div className="canvas-scrim" />}
          {loading && (
            <div className={`overlay${hasGraph ? ' overlay-card' : ''}`}>
              <div className="overlay-loading">
                <span className="spin" /> {buildProgress?.label ?? 'Building graph…'}
              </div>
              {buildProgress && (
                <div
                  className="build-progress"
                  role="progressbar"
                  aria-valuenow={buildProgress.done}
                  aria-valuemin={0}
                  aria-valuemax={buildProgress.total}
                >
                  <div
                    className="build-progress-fill"
                    style={{
                      width: `${Math.round((buildProgress.done / buildProgress.total) * 100)}%`,
                    }}
                  />
                </div>
              )}
            </div>
          )}
          {error && !hits && (
            <div className={`overlay error${hasGraph ? ' overlay-card' : ''}`}>{error}</div>
          )}
          {!hasGraph && !loading && !hits && !error && (
            <div className="overlay hint">
              Search for a paper to map its citations, references, and similar work.
              {libraryCount > 0 && (
                <>
                  <div className="hint-or">— or —</div>
                  <button className="hint-cta" onClick={() => setAssistantOpen(true)}>
                    💬 Chat with your library
                  </button>
                </>
              )}
            </div>
          )}
        </GraphExplorer>

        {/* Mounted (not just rendered) whenever there's something to assist
            with, and merely hidden when collapsed — so toggling the panel
            preserves the conversation. Remounts per workspace epoch for a
            fresh per-graph run state (the transcript itself lives in the
            store and resets/restores via the load/restore thunks). */}
        {(hasGraph || libraryCount > 0) && (
          <Teacher key={epoch} collapsed={!assistantOpen} onClose={() => setAssistantOpen(false)} />
        )}
      </div>
    </div>
  )
}
