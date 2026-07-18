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
import { listSources, PROVIDER_LABEL } from './api'
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
import Tour from './tour/Tour'
import { GRAPH_TOUR, HOME_TOUR, TOUR_KEYS } from './tour/steps'
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

  // The guided tour, in two phases keyed by whether a graph is up: the HOME
  // tour (the search surface) auto-runs once on first launch, the GRAPH tour
  // (the graph tools) once on the first graph. Each phase auto-runs once ever
  // (its own localStorage flag); the header's "?" re-runs the current phase
  // any time.
  const hasGraph = !!graph && graph.nodes.length > 0
  const [tourOpen, setTourOpen] = useState(false)
  const [tourStage, setTourStage] = useState<string | undefined>(undefined)
  useEffect(() => {
    const seenKey = graph ? TOUR_KEYS.graph : TOUR_KEYS.home
    if (!localStorage.getItem(seenKey)) setTourOpen(true)
  }, [graph])
  const closeTour = useCallback(() => {
    // Done, Skip, ✕, and Esc all count as "seen" — the auto-run never nags
    // twice; a re-run is a deliberate "?" click. Drawers a step staged open
    // are put away (the assistant panel stays — it invites use).
    localStorage.setItem(hasGraph ? TOUR_KEYS.graph : TOUR_KEYS.home, '1')
    setShowSources(false)
    setShowSessions(false)
    setTourStage(undefined)
    setTourOpen(false)
  }, [hasGraph])
  /** Stage what a tour step asks for: open the named drawer/panel; a step
   *  wanting nothing (undefined) puts the drawers away as the walk moves on.
   *  The assistant only ever opens — collapsing it mid-walk would hide the
   *  graph tour's own lecture and ask stops. 'details' passes through to
   *  GraphExplorer (via tourStage), which selects the seed when nothing is. */
  const onTourStage = useCallback((stage?: string) => {
    setTourStage(stage)
    setShowSources(stage === 'library')
    setShowSessions(stage === 'sessions')
    if (stage === 'assistant') setAssistantOpen(true)
  }, [])

  // Seed search: query + optional search options, cache-first local / live S2
  // hits. Search errors share the workspace error overlay with graph-load errors.
  const onSearchError = useCallback(
    (message: string | null) => {
      dispatch(errorSet(message))
    },
    [dispatch],
  )
  const {
    query,
    setQuery,
    options,
    setOptions,
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

  return (
    <div className="atlas">
      <AtlasHeader
        query={query}
        onQueryChange={setQuery}
        onSubmit={onSubmit}
        searching={searching}
        loadingGraph={loading}
        options={options}
        onOptions={setOptions}
        provider={provider}
        onProviderChange={(next) => dispatch(switchProvider(next))}
        seedTitle={graph?.seed.title ?? null}
        onHome={goHome}
        onOpenSources={() => setShowSources(true)}
        assistantAvailable={hasGraph || libraryCount > 0}
        assistantOpen={assistantOpen}
        onToggleAssistant={() => setAssistantOpen((prev) => !prev)}
        onOpenSessions={() => setShowSessions(true)}
        onStartTour={() => setTourOpen(true)}
      />

      {tourOpen && (
        <Tour steps={hasGraph ? GRAPH_TOUR : HOME_TOUR} onClose={closeTour} onStage={onTourStage} />
      )}

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
        <GraphExplorer tourStage={tourOpen ? tourStage : undefined}>
          <HitList
            hits={hits}
            localHits={localHits}
            searching={searching}
            liveFailed={liveFailed}
            providerLabel={PROVIDER_LABEL[provider]}
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
