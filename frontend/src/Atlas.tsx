/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Atlas — the shell. Composes the header, the drawers, and the body; owns only
 * what it alone renders: drawer visibility, the seed-search instance (its
 * three render sites — the header form, the hit-list overlay, the submit
 * routing — all live here), and the loading/error overlays.
 *
 * **The body has two states, and the seam matters.** With no graph the
 * assistant is the landing surface (a centred chat, the app's front door) and
 * the overlays get their own layer over the body; with a graph it's the
 * explorer, and the assistant docks beside it. The `Teacher` element stays at
 * one position in the tree across both, so that transition never remounts it
 * and the conversation survives — see its own docstring.
 *
 * Everything cross-cutting lives in the store (see `store/README.md`):
 * the workspace (graph + discoveries + layout), the transcript, and the
 * highlight ids. The old Atlas's transcript-duplicating refs and remount
 * plumbing died with that move — Save reads the store, not a hoisted copy.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { getSettings } from './api'
import { getBuildShape, sameBuild, useBuildShape } from './graph/buildShape'
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
import SideBar from './shell/SideBar'
import type { ShellView } from './shell/SideBar'
import { useSessions } from './shell/useSessions'
import './shell/shell.css'

/** localStorage key remembering whether the left rail is expanded. */
const RAIL_KEY = 'atlas.railOpen'
import GraphExplorer from './graph/GraphExplorer'
import Teacher from './teacher/Teacher'
import Sources from './library/Sources'
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
  // Which main-pane view is up. The workspace stays MOUNTED behind the
  // library rather than unmounting — the graph and the conversation are
  // expensive, live state, and visiting the library is a detour, not a
  // teardown (the same reasoning that keeps Teacher at one tree position).
  const [view, setView] = useState<ShellView>('workspace')
  // The rail's expanded/collapsed state, remembered — it's a workspace
  // preference, not a per-visit one.
  const [railOpen, setRailOpen] = useState(() => localStorage.getItem(RAIL_KEY) !== '0')
  const [showSettings, setShowSettings] = useState(false)
  const theme = useTheme()
  // Open by default, because the assistant is now where you start: the
  // landing chat is always on screen, and entering graph mode should dock the
  // conversation beside the map rather than hide it. (It can't be derived from
  // `epoch` any more — that stopped bumping on graph loads in v6.11.0 so the
  // panel survives a chat-seeded jump, which would leave this stuck closed.)
  const [assistantOpen, setAssistantOpen] = useState(true)
  // Latest graph, readable from the mount-only effect below without making it
  // a dependency (that would re-fire the settings fetch on every graph load).
  const graphRef = useRef(graph)
  graphRef.current = graph

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

  // Re-surface the teacher on a session restore, in case it was collapsed
  // before. A graph *load* no longer bumps the epoch (v6.11.0), which is fine:
  // the panel defaults open and a load never closes it.
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
    setView('workspace')
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
    setView(stage === 'library' ? 'library' : 'workspace')
    if (stage === 'assistant') setAssistantOpen(true)
  }, [])

  /** New graph: back to the page-load default — no graph, the landing chat. */
  const goHome = useCallback(() => {
    dispatch(workspaceCleared())
    setAssistantOpen(true)
    setView('workspace')
    setOpenSessionId(null)
  }, [dispatch])

  useEffect(() => {
    localStorage.setItem(RAIL_KEY, railOpen ? '1' : '0')
  }, [railOpen])

  // The saved-graph list in the rail, and which of them is on screen. The id
  // is tracked here rather than in the store because it is a fact about this
  // *session of use* — which row to mark, and which one a re-save overwrites
  // — not about the graph itself.
  const {
    sessions,
    refresh: refreshSessions,
    rename: renameSessionRow,
    remove: removeSessionRow,
  } = useSessions()
  const [openSessionId, setOpenSessionId] = useState<string | null>(null)
  // The name a save just landed under, for the confirmation — and its own
  // clearing timer. Saving is otherwise silent, and in the collapsed rail
  // (where the button is a bare ＋ and the saved list isn't even rendered)
  // there is nothing at all to tell you it worked.
  // `leaving` is the exit phase: the notice stays MOUNTED through it so its
  // transitions can play out. Unmounting on the way out is what made both the
  // toast and the ✓ vanish in one frame.
  const [savedNotice, setSavedNotice] = useState<{ name: string; leaving: boolean } | null>(null)
  const savedTimers = useRef<number[]>([])
  useEffect(() => () => savedTimers.current.forEach((timer) => window.clearTimeout(timer)), [])

  /** Save the current workspace, named after its seed.
   *
   * No name prompt: the rail names it after the paper and lets you rename it
   * in place afterwards, which is how a saved thing should work — the moment
   * you want to save is the moment you least want a dialog. Re-saving an
   * already-saved graph overwrites that row rather than piling up copies.
   */
  const onSaveSession = useCallback(async () => {
    const name = graph?.seed.title || 'Untitled graph'
    const saved = await dispatch(saveWorkspace({ name, id: openSessionId ?? undefined })).unwrap()
    setOpenSessionId(saved.id)
    setSavedNotice({ name: saved.name, leaving: false })
    // Restarted rather than stacked, so saving twice quickly shows one notice
    // for its full life instead of the second cutting the first short.
    savedTimers.current.forEach((timer) => window.clearTimeout(timer))
    savedTimers.current = [
      window.setTimeout(
        () => setSavedNotice((prev) => (prev ? { ...prev, leaving: true } : prev)),
        2800,
      ),
      window.setTimeout(() => setSavedNotice(null), 3350),
    ]
    await refreshSessions()
  }, [dispatch, graph, openSessionId, refreshSessions])

  // The floating layer over whichever surface is up — search hits, the build
  // progress, the error. Built once here rather than inline so the graph and
  // landing branches below can't drift apart. (The old "Search for a paper…"
  // hint is gone: the landing chat says what to do by being a chat.)
  const overlays = (
    <>
      {/* Reopening the assistant once it's collapsed. It used to be a header
          tab; with the header gone it belongs beside the thing it opens, at
          the top-right of the CANVAS. Not the pane: the detail panel is a
          sibling of the canvas, so a pane-anchored button sat on top of that
          panel's own ✕ and trapped the reader inside it. */}
      {hasGraph && !assistantOpen && (
        <button
          type="button"
          className="pane-assistant"
          data-tour="assistant-btn"
          onClick={() => setAssistantOpen(true)}
          title="The AI assistant — a lecture and Q&A over the graph"
          aria-label="Open the assistant"
        >
          🎓
        </button>
      )}
      {/* Dim whatever is behind — a graph mid-re-seed, or the chat you were
          reading. The card alone was only ever legible against an empty canvas;
          over live content it has to push that content back to read at all. */}
      {(loading || error) && <div className="canvas-scrim" />}
      {loading && (
        <div className="overlay overlay-card">
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
      {error && (
        <div className="overlay error overlay-card">
          {error}
          {/* A build failure used to be a dead end: the card and its scrim sat
              over the page with nothing to dismiss them, so the only way back
              was to start another build. */}
          <button
            type="button"
            className="overlay-close"
            onClick={() => dispatch(errorSet(null))}
            aria-label="Dismiss"
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
    </>
  )

  return (
    <div className="atlas">
      <SideBar
        open={railOpen}
        onToggle={() => setRailOpen((prev) => !prev)}
        view={view}
        onView={setView}
        onNewGraph={goHome}
        sessions={sessions}
        openSessionId={openSessionId}
        onOpenSession={(id) => {
          dispatch(restoreSession(id))
          setOpenSessionId(id)
          setView('workspace')
        }}
        onRenameSession={(id, name) => void renameSessionRow(id, name)}
        onDeleteSession={(id) => {
          void removeSessionRow(id)
          // Deleting the row you have open doesn't close the graph — the
          // workspace is still yours to look at; it just isn't saved any more.
          if (id === openSessionId) setOpenSessionId(null)
        }}
        onSaveSession={hasGraph ? onSaveSession : undefined}
        justSaved={!!savedNotice && !savedNotice.leaving}
        onOpenSettings={() => setShowSettings(true)}
        onStartTour={() => setTourOpen(true)}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        provider={provider}
        onProviderChange={(next) => dispatch(switchProvider(next))}
        loadingGraph={loading}
        seedTitle={graph?.seed.title ?? null}
      />

      <div className="atlas-main">
        {/* Bottom-left, next to the rail: the confirmation belongs beside the
            control that caused it, not centred over the map. `key` on the
            name so saving a second graph replays the entrance rather than
            silently swapping the text of a notice already on screen. */}
        {savedNotice && (
          <div
            className={`save-toast${savedNotice.leaving ? ' leaving' : ''}`}
            key={savedNotice.name}
            role="status"
          >
            Graph saved to <strong>{savedNotice.name}</strong>
          </div>
        )}

        {tourOpen && (
          <Tour
            steps={hasGraph ? GRAPH_TOUR : HOME_TOUR}
            onClose={closeTour}
            onStage={onTourStage}
          />
        )}

        <SettingsModal
          open={showSettings}
          onClose={() => {
            setShowSettings(false)
            rebuildIfShapeChanged()
          }}
        />

        {/* The library is a VIEW, not a drawer, and the workspace behind it
            stays mounted — going to the library and back must not cost the
            graph or the conversation. */}
        <Sources open={view === 'library'} variant="pane" onClose={() => setView('workspace')} />

        <div className="atlas-body" hidden={view !== 'workspace'}>
          {/* The overlays belong to whichever surface is up: over the canvas in
              graph mode, over the landing chat before one exists. */}
          {graph ? (
            <GraphExplorer tourStage={tourOpen ? tourStage : undefined}>{overlays}</GraphExplorer>
          ) : (
            <div className="landing-overlays">{overlays}</div>
          )}

          {/* One instance, two shapes. Kept at a single position in the tree so
            entering graph mode collapses the landing chat into the side panel
            without remounting it — the conversation, its scroll position and
            its run state all survive the transition (see store/README.md on
            why a remount would undo exactly that). */}
          <Teacher
            key={epoch}
            landing={!graph}
            collapsed={!!graph && !assistantOpen}
            onClose={graph ? () => setAssistantOpen(false) : undefined}
          />
        </div>
      </div>
    </div>
  )
}
