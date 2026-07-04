/**
 * Atlas — the workspace orchestrator that wires the whole app together. It
 * owns the loaded graph, the stable `base` dataset the force simulation
 * mutates, the filtered `view`, layout switching, hover/highlight focus,
 * saved-session save/restore (Phase 4), and the drawer visibility.
 *
 * Everything else is delegated to concern folders:
 *   - header/    AtlasHeader (brand, search form, drawer toggles)
 *   - search/    Search + HitList + useSeedSearch (seed search)
 *   - graph/     GraphCanvas + GraphControls + Legend, theme/model, and the
 *                useTimeline / usePinning / useDiscovery hooks
 *   - detail/    DetailPanel + useSelection (the selected paper)
 *   - teacher/   Teacher (the unified assistant: graph lecture + Q&A, or a
 *                graph-free chat over the uploaded library)
 *   - library/   Sources (the bring-your-own-sources drawer)
 *   - sessions/  Sessions (the saved-workspaces drawer)
 *
 * The load-bearing invariant everything shares: `base`'s node/link objects
 * are mutated by react-force-graph (x/y) and by pins (fx/fy), so they must
 * keep their identity for a graph's whole life — filters produce views over
 * them, and discoveries append in place.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  fetchGraph,
  getSession,
  saveSession,
  type Beat,
  type ChatMsg,
  type GraphResponse,
  type LectureTrace,
  type SavedSessionMeta,
  listSources,
} from './api'
import {
  ID_RE,
  cleanNode,
  countRels,
  type Base,
  type VLink,
  type VNode,
} from './graph/model'
import { REL_TYPES } from './graph/theme'
import { useTimeline } from './graph/useTimeline'
import { usePinning } from './graph/usePinning'
import { useDiscovery } from './graph/useDiscovery'
import { useSeedSearch } from './search/useSeedSearch'
import { useSelection } from './detail/useSelection'
import AtlasHeader from './header/AtlasHeader'
import HitList from './search/HitList'
import GraphCanvas from './graph/GraphCanvas'
import GraphControls from './graph/GraphControls'
import Legend from './graph/Legend'
import DetailPanel from './detail/DetailPanel'
import Teacher from './teacher/Teacher'
import Sources from './library/Sources'
import Sessions from './sessions/Sessions'
import './atlas.css'

/** The transcript bundle passed between the Teacher and saved sessions. */
type TeacherTranscript = { chat: ChatMsg[]; beats: Beat[]; histTrace: LectureTrace[] }

export default function Atlas() {
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [loadingGraph, setLoadingGraph] = useState(false)
  /** One shared error surface for search failures and graph-load failures. */
  const [error, setError] = useState<string | null>(null)

  // Declutter controls.
  // 'search' is always on (no filter chip): topic-search hits are agent-
  // discovered and few, so they stay visible; the year slider still filters them.
  const [enabled, setEnabled] = useState<Set<string>>(new Set([...REL_TYPES, 'search']))
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  const [hoverId, setHoverId] = useState<string | null>(null)
  // Nodes the AI teacher is currently talking about (active beat / cited papers).
  const [highlightIds, setHighlightIds] = useState<Set<string>>(new Set())
  // 'force' = organic force-directed; 'timeline' = x pinned to publication year.
  const [layout, setLayout] = useState<'force' | 'timeline'>('force')

  // The Sources drawer (Phase 3d) — the user's local semantic library.
  const [showSources, setShowSources] = useState(false)
  // The unified assistant panel: one docked side panel toggled from the header.
  // With a graph it's the AI teacher (lecture + agentic Q&A); with no graph but a
  // library it's a graph-free chat over the user's sources. It auto-opens when a
  // graph loads (below) so the teacher appears as before, and can be opened for
  // library chat before any graph exists. `libraryCount` gates the graph-free
  // entry point; refreshed whenever the Sources drawer closes.
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [libraryCount, setLibraryCount] = useState(0)
  // Saved sessions & workspaces (Phase 4).
  const [showSessions, setShowSessions] = useState(false)
  // Bumped on every graph load / restore. Used as the Teacher's key so it
  // remounts with a fresh conversation on each re-seed (or the restored one).
  const [graphKey, setGraphKey] = useState(0)

  // The transcript to seed the NEXT Teacher mount: empty for a fresh re-seed,
  // the saved chat/beats when restoring. Read at mount, so it's a ref.
  const teacherInitRef = useRef<TeacherTranscript>({ chat: [], beats: [], histTrace: [] })
  // The Teacher's latest transcript, reported up so Save can capture it.
  const teacherStateRef = useRef<TeacherTranscript>({ chat: [], beats: [], histTrace: [] })
  // A layout to apply once a restored graph is in place (see effect below).
  const restoreLayoutRef = useRef<'force' | 'timeline' | null>(null)

  /** Capture the Teacher's transcript as it evolves (for Save). */
  const handleTeacherState = useCallback((s: TeacherTranscript) => {
    teacherStateRef.current = s
  }, [])

  /** Re-count the library (the Ask-library entry point only shows when >0). */
  const refreshLibraryCount = useCallback(() => {
    listSources().then((res) => setLibraryCount(res.sources.length)).catch(() => {})
  }, [])
  useEffect(refreshLibraryCount, [refreshLibraryCount])

  const wrapRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null)
  const [size, setSize] = useState({ w: 800, h: 600 })
  /** One-shot latch: zoomToFit runs once per graph/layout, on engine stop. */
  const fitDone = useRef(false)

  // Track the canvas container's size so ForceGraph2D always fills it.
  useEffect(() => {
    if (!wrapRef.current) return
    const el = wrapRef.current
    const ro = new ResizeObserver(() =>
      setSize({ w: el.clientWidth, h: el.clientHeight }),
    )
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  /**
   * Stable per-graph node/link objects. react-force-graph mutates these (adds
   * x/y, resolves source/target), and pins set fx/fy on them — so they MUST
   * survive filter changes. Rebuilt only when a new graph loads.
   */
  const base = useMemo<Base | null>(() => {
    if (!graph) return null
    const nodes: VNode[] = graph.nodes.map((n) => ({ ...n }))
    const links: VLink[] = graph.edges.map((e) => ({
      ...e,
      _s: e.source,
      _t: e.target,
    }))
    const years = nodes
      .map((n) => n.year)
      .filter((y): y is number => typeof y === 'number')
    const counts: Record<string, number> = { reference: 0, citation: 0, similar: 0 }
    nodes.forEach((n) =>
      n.rels.forEach((r) => {
        if (r in counts) counts[r]++
      }),
    )
    return {
      nodes,
      links,
      minYear: years.length ? Math.min(...years) : 0,
      maxYear: years.length ? Math.max(...years) : 0,
      counts,
    }
  }, [graph])

  // Reset the declutter controls whenever a new graph loads. (Selection,
  // pins, and discoveries reset themselves inside their own hooks.)
  useEffect(() => {
    if (!base) return
    setEnabled(new Set([...REL_TYPES, 'search']))
    setYearLo(base.minYear)
    setYearHi(base.maxYear)
    setHoverId(null)
    setHighlightIds(new Set())
  }, [base])

  // Timeline layout physics (year-column pinning, collide force, year axis,
  // settle-freeze) — plus its keep-in-sync effects. Mutates the same sim
  // objects as the pin/discovery hooks below, through the shared fgRef.
  const { nodeTimelineX, applyLayoutPhysics, drawAxis, freezeSettledY } =
    useTimeline({ base, layout, fgRef, size, fitDone, yearLo, yearHi })

  // User pins: drag-to-pin, the detail panel's Pin button, Release-all.
  const { pinned, clearPins, onNodeDragEnd, togglePin, releaseAll } =
    usePinning({ base, layout, nodeTimelineX, fgRef, fitDone })

  // Seed search: query + optional filters, cache-first local / live arXiv results.
  const {
    query, setQuery, filters, setFilters,
    hits, localHits, searching, arxivFailed, runSearch, clearHits,
  } = useSeedSearch(setError)

  /**
   * Load (or re-seed) the graph for a seed — an arXiv id, pasted URL, or S2
   * paperId — and remount the Teacher with a fresh conversation.
   */
  const loadGraph = useCallback(async (seed: string) => {
    setLoadingGraph(true)
    setError(null)
    clearHits()
    fitDone.current = false
    try {
      const g = await fetchGraph(seed)
      // A fresh seed starts a fresh conversation — remount the teacher empty.
      teacherInitRef.current = { chat: [], beats: [], histTrace: [] }
      restoreLayoutRef.current = null
      setGraph(g)
      setGraphKey((k) => k + 1)
      setAssistantOpen(true) // surface the teacher for the freshly loaded graph
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingGraph(false)
    }
  }, [clearHits])

  /**
   * Route the search form: a pasted arXiv id/URL jumps straight to its graph;
   * anything else runs the keyword search.
   */
  const onSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault()
      const q = query.trim()
      if (!q) return
      if (ID_RE.test(q)) loadGraph(q)
      else runSearch(q)
    },
    [query, loadGraph, runSearch],
  )

  // Selection: the open detail panel, its hydration + figures + code links,
  // click handling.
  const { selectedId, setSelectedId, selected, figures, figLoading, codeLinks, onNodeClick } =
    useSelection({ base, graph, loadGraph })

  // Agent discoveries: papers the teacher pulls in mid-chat, merged into
  // `base` in place; graphVersion signals the view to recompute.
  const { discoveredNodes, graphVersion, onDiscover } = useDiscovery({
    base,
    layout,
    nodeTimelineX,
    fgRef,
    onYearLo: setYearLo,
    onYearHi: setYearHi,
  })

  /**
   * The filtered view the canvas renders. Nodes keep their identity (so
   * positions/pins persist); links are copied with source/target reset to ids
   * so RFG re-resolves cleanly.
   */
  const view = useMemo(() => {
    if (!base) return { nodes: [] as VNode[], links: [] as VLink[] }
    const nodeOk = (n: VNode) => {
      if (n.is_seed) return true
      if (!n.rels.some((r) => r !== 'seed' && enabled.has(r))) return false
      if (typeof n.year === 'number' && (n.year < yearLo || n.year > yearHi))
        return false
      return true
    }
    const nodes = base.nodes.filter(nodeOk)
    const ids = new Set(nodes.map((n) => n.id))
    const links = base.links
      .filter((l) => enabled.has(l.type) && ids.has(l._s) && ids.has(l._t))
      .map((l) => ({ ...l, source: l._s, target: l._t }))
    return { nodes, links }
    // graphVersion isn't read directly — it's a signal that base.nodes/links
    // were mutated in place (expand_node discoveries) and this must recompute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, enabled, yearLo, yearHi, graphVersion])

  /** Neighbors of the hovered node (for focus-on-hover dimming). */
  const hoverSet = useMemo(() => {
    if (!base || !hoverId) return null
    const s = new Set<string>([hoverId])
    base.links.forEach((l) => {
      if (l._s === hoverId) s.add(l._t)
      if (l._t === hoverId) s.add(l._s)
    })
    return s
  }, [base, hoverId])

  /**
   * What to focus the canvas on: hovering wins; otherwise the papers the AI
   * teacher is currently talking about (so beats/answers light up their nodes).
   */
  const focusSet = useMemo(
    () => hoverSet ?? (highlightIds.size ? highlightIds : null),
    [hoverSet, highlightIds],
  )

  /** Toggle one relation type's visibility (the filter chips). */
  const toggleType = useCallback((t: string) => {
    setEnabled((prev) => {
      const s = new Set(prev)
      if (s.has(t)) s.delete(t)
      else s.add(t)
      return s
    })
  }, [])

  /**
   * Switch layout. Timeline pins each node's x to its year (y stays
   * force-driven so citation threads form); Force releases those x-pins. The
   * physics live in useTimeline; clearing pin state stays here because
   * switching layout releases all user pins — otherwise a node pinned in one
   * mode stays stuck at that position in the other.
   */
  const setLayoutMode = useCallback(
    (mode: 'force' | 'timeline') => {
      setLayout(mode)
      if (!base) return
      applyLayoutPhysics(mode)
      clearPins()
    },
    [base, applyLayoutPhysics, clearPins],
  )

  // Apply a restored session's layout once its graph has been rebuilt into
  // `base`. Routed through the ref (rather than setLayoutMode in the restore
  // handler) so applyLayoutPhysics runs against the NEW base — setting the
  // right forces and pinning timeline columns. No-ops for a normal graph load.
  useEffect(() => {
    if (!base) return
    const want = restoreLayoutRef.current
    if (!want) return
    restoreLayoutRef.current = null
    setLayoutMode(want)
  }, [base, setLayoutMode])

  // --- Saved sessions & workspaces (Phase 4) ---------------------------------

  /**
   * Save the current workspace: the full graph as it stands (every node/edge,
   * including agent-discovered ones) + the teacher transcript. `base` is the
   * source of truth — it holds the merged, mutated node/edge objects.
   *
   * @param name The session's display name.
   * @param id   Set → overwrite that saved session in place; omitted → create new.
   */
  const handleSave = useCallback(
    async (name: string, id?: string): Promise<SavedSessionMeta> => {
      if (!base || !graph) throw new Error('No graph to save yet.')
      const ts = teacherStateRef.current
      return saveSession({
        id,
        name,
        seed: {
          id: graph.seed.id,
          arxiv_id: graph.seed.arxiv_id,
          title: graph.seed.title,
        },
        layout,
        nodes: base.nodes.map(cleanNode),
        edges: base.links.map((l) => ({
          source: l._s,
          target: l._t,
          type: l.type,
          influential: l.influential,
        })),
        chat: ts.chat,
        beats: ts.beats,
        hist_trace: ts.histTrace,
      })
    },
    [base, graph, layout],
  )

  /**
   * Reopen a saved session: rebuild its graph directly (no Semantic Scholar
   * fetch, so no rate-limit cost and the exact discovered papers are
   * preserved) and remount the teacher with the saved transcript + layout.
   */
  const restoreSession = useCallback(async (id: string) => {
    setLoadingGraph(true)
    setError(null)
    try {
      const s = await getSession(id)
      const d = s.data
      teacherInitRef.current = {
        chat: d.chat ?? [],
        beats: d.beats ?? [],
        histTrace: d.hist_trace ?? [],
      }
      restoreLayoutRef.current = d.layout ?? 'force'
      clearHits()
      fitDone.current = false
      setGraph({
        seed: {
          id: d.seed.id,
          arxiv_id: d.seed.arxiv_id ?? '',
          title: d.seed.title,
        },
        nodes: d.nodes,
        edges: d.edges,
        counts: countRels(d.nodes),
      })
      setGraphKey((k) => k + 1)
      setAssistantOpen(true) // surface the teacher for the restored graph
      setShowSessions(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingGraph(false)
    }
  }, [clearHits])

  /**
   * When the simulation settles: freeze Timeline y positions (so dragging one
   * node can't re-relax the rest) and run the one-shot zoomToFit.
   */
  const onEngineStop = useCallback(() => {
    freezeSettledY(pinned)
    if (!fitDone.current && fgRef.current) {
      fgRef.current.zoomToFit(400, 60)
      fitDone.current = true
    }
  }, [freezeSettledY, pinned])

  // Repaint when highlight/selection/pins/layout change (the sim may be at rest).
  useEffect(() => {
    fgRef.current?.refresh?.()
  }, [hoverId, selectedId, pinned, view, highlightIds, layout])

  const hasGraph = !!base && base.nodes.length > 0

  return (
    <div className="atlas">
      <AtlasHeader
        query={query}
        onQueryChange={setQuery}
        onSubmit={onSubmit}
        searching={searching}
        loadingGraph={loadingGraph}
        filters={filters}
        onFilters={setFilters}
        seedTitle={graph?.seed.title ?? null}
        onOpenSources={() => setShowSources(true)}
        assistantAvailable={hasGraph || libraryCount > 0}
        assistantOpen={assistantOpen}
        onToggleAssistant={() => setAssistantOpen((o) => !o)}
        onOpenSessions={() => setShowSessions(true)}
      />

      <Sources
        open={showSources}
        onClose={() => {
          setShowSources(false)
          refreshLibraryCount() // they may have added/removed sources
        }}
      />

      <Sessions
        open={showSessions}
        onClose={() => setShowSessions(false)}
        onSave={handleSave}
        onOpen={restoreSession}
        canSave={hasGraph}
        defaultName={graph?.seed.title ?? ''}
      />

      <div className="atlas-body">
        <main className="canvas-wrap" ref={wrapRef}>
          <HitList
            hits={hits}
            localHits={localHits}
            searching={searching}
            arxivFailed={arxivFailed}
            onPick={loadGraph}
            onClose={clearHits}
          />

          {loadingGraph && <div className="overlay">Building graph…</div>}
          {error && !hits && <div className="overlay error">{error}</div>}
          {!hasGraph && !loadingGraph && !hits && !error && (
            <div className="overlay hint">
              Search for a paper to map its citations, references, and similar
              work.
              {libraryCount > 0 && (
                <>
                  <div className="hint-or">— or —</div>
                  <button
                    className="hint-cta"
                    onClick={() => setAssistantOpen(true)}
                  >
                    💬 Chat with your library
                  </button>
                </>
              )}
            </div>
          )}

          {hasGraph && (
            <GraphControls
              layout={layout}
              onLayout={setLayoutMode}
              enabled={enabled}
              onToggleType={toggleType}
              counts={base!.counts}
              minYear={base!.minYear}
              maxYear={base!.maxYear}
              yearLo={yearLo}
              yearHi={yearHi}
              onYearLo={setYearLo}
              onYearHi={setYearHi}
              visibleCount={view.nodes.length}
              totalCount={base!.nodes.length}
              pinnedCount={pinned.size}
              onReleaseAll={releaseAll}
              onFit={() => fgRef.current?.zoomToFit(400, 60)}
            />
          )}

          {hasGraph && (
            <GraphCanvas
              fgRef={fgRef}
              width={size.w}
              height={size.h}
              data={view}
              focusSet={focusSet}
              pinned={pinned}
              selectedId={selectedId}
              highlightIds={highlightIds}
              onNodeClick={onNodeClick}
              onNodeHover={setHoverId}
              onNodeDragEnd={onNodeDragEnd}
              onEngineStop={onEngineStop}
              onRenderFramePre={drawAxis}
            />
          )}

          {hasGraph && (
            <Legend
              hasDiscovered={discoveredNodes.length > 0}
              hasSearchHits={discoveredNodes.some((n) => n.rels.includes('search'))}
            />
          )}
        </main>

        {selected && (
          <DetailPanel
            node={selected}
            figures={selected.arxiv_id ? figures[selected.arxiv_id] : undefined}
            figuresLoading={figLoading === selected.arxiv_id}
            codeLinks={selected.arxiv_id ? codeLinks[selected.arxiv_id] : undefined}
            isPinned={pinned.has(selected.id)}
            onTogglePin={() => togglePin(selected.id)}
            onClose={() => setSelectedId(null)}
            onExplore={loadGraph}
          />
        )}

        {/* Mounted (not just rendered) whenever there's something to assist with,
            and merely hidden when collapsed — so toggling the panel preserves the
            in-progress conversation. Remounts on graph load (keyed) for a fresh
            per-graph transcript. */}
        {(hasGraph || libraryCount > 0) && (
          <Teacher
            key={graphKey}
            graph={graph}
            collapsed={!assistantOpen}
            extraNodes={discoveredNodes}
            onHighlight={setHighlightIds}
            onDiscover={onDiscover}
            onClose={() => setAssistantOpen(false)}
            onStateChange={handleTeacherState}
            initialChat={teacherInitRef.current.chat}
            initialBeats={teacherInitRef.current.beats}
            initialHistTrace={teacherInitRef.current.histTrace}
          />
        )}
      </div>
    </div>
  )
}
