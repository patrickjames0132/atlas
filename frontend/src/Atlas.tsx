/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
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
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { getSettings, listSources, PROVIDER_LABEL } from './api'
import { getBuildShape, sameBuild, useBuildShape } from './graph/buildShape'
import { ID_RE } from './graph/model'
import { applyConfiguredDefault, setTheme, useTheme } from './ui/theme'
import { useAppDispatch, useAppSelector } from './store'
import {
  errorSet,
  loadGraph,
  providerSet,
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
import SettingsModal from './settings/SettingsModal'
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
  const { graph, epoch, loading, buildProgress, error, provider, seedRef } = useAppSelector(
    (state) => state.workspace,
  )

  // Drawer visibility + the assistant toggle — shell-local UI.
  const [showSources, setShowSources] = useState(false)
  const [showSessions, setShowSessions] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const theme = useTheme()
  const [assistantOpen, setAssistantOpen] = useState(false)
  // Gates the graph-free library-chat entry point; refreshed when the
  // Sources drawer closes (they may have added/removed sources).
  const [libraryCount, setLibraryCount] = useState(0)

  const refreshLibraryCount = useCallback(() => {
    listSources()
      .then((res) => setLibraryCount(res.sources.length))
      .catch(() => {})
  }, [])
  // Latest graph, readable from the mount-only effect below without making it
  // a dependency (that would re-fire the settings fetch on every graph load).
  const graphRef = useRef(graph)
  graphRef.current = graph

  useEffect(refreshLibraryCount, [refreshLibraryCount])

  // The build shape as it was when the settings modal opened. The modal's shape
  // rows write through immediately (they're browser state, not config draft), so
  // this snapshot is the only way to tell on close whether the graph on screen
  // was built the way the user now wants it built.
  const shapeOnOpen = useRef(getBuildShape())
  useEffect(() => {
    if (showSettings) shapeOnOpen.current = getBuildShape()
  }, [showSettings])

  /**
   * Rebuild the current graph when the settings modal changed how it'd be built.
   *
   * Runs on *close*, which is right for the band-shape number inputs: they
   * write on every character, and rebuilding per keystroke would hammer the
   * provider. The `adaptive` switch is handled separately below — one click is
   * a complete intent, so it shouldn't wait for the modal to close.
   *
   * No `refresh` flag either way: a changed shape is part of the cache key, so
   * it misses the old snapshot on its own, and switching back is a cache hit.
   */
  const rebuildIfShapeChanged = useCallback(() => {
    if (!seedRef || sameBuild(shapeOnOpen.current, getBuildShape())) return
    dispatch(loadGraph({ seed: seedRef }))
    shapeOnOpen.current = getBuildShape()
  }, [dispatch, seedRef])

  // The adaptive switch rebuilds immediately. Watched here rather than wired
  // through the modal so the modal stays a settings editor that knows nothing
  // about the graph — it just writes the store, and this notices.
  const { adaptive } = useBuildShape()
  const previousAdaptive = useRef(adaptive)
  useEffect(() => {
    if (previousAdaptive.current === adaptive) return // mount, or an unrelated edit
    previousAdaptive.current = adaptive
    // Keep the close-time comparison honest: this rebuild already applied the
    // switch, so closing the modal mustn't rebuild a second time for it.
    shapeOnOpen.current = getBuildShape()
    if (seedRef) dispatch(loadGraph({ seed: seedRef }))
  }, [adaptive, seedRef, dispatch])

  // Seed browser-level defaults from config: the header's data-source
  // selector and (for a browser with no saved choice) the colour theme. The
  // store's initial value is a placeholder — the honest default lives in
  // config (`providers.default_provider`, editable in the settings modal),
  // and without this the setting would be inert: the dropdown always started
  // on 's2' and the frontend names a provider on every request, so the
  // backend's own fallback never fired either. Only applied before anything
  // is loaded, so it can't yank a restored session onto another provider.
  useEffect(() => {
    let cancelled = false
    void getSettings()
      .then((settings) => {
        if (cancelled) return
        const configured = settings.config.providers.default_provider
        if (!graphRef.current && configured) dispatch(providerSet(configured))
        // Only fills a browser that has never chosen a theme — see the store.
        applyConfiguredDefault(settings.config.ui.default_theme)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, [])

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
   *  graph tour's own lecture and ask stops. 'details' and 'controls' pass
   *  through to GraphExplorer (via tourStage), which selects the seed when
   *  nothing is / expands a collapsed controls panel. */
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
        onOpenSettings={() => setShowSettings(true)}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        onStartTour={() => setTourOpen(true)}
      />

      {tourOpen && (
        <Tour steps={hasGraph ? GRAPH_TOUR : HOME_TOUR} onClose={closeTour} onStage={onTourStage} />
      )}

      <SettingsModal
        open={showSettings}
        onClose={() => {
          setShowSettings(false)
          rebuildIfShapeChanged()
        }}
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
