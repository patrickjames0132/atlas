/**
 * The graph exploration area: the canvas, its controls, the legend, and the
 * detail panel (plus its figure lightbox) — plus every piece of state only
 * they read (the `base` sim dataset, declutter filters, hover, selection,
 * canvas size).
 *
 * Store boundary (the Phase 6 state directive, drawn precisely here):
 *   READS  workspace.graph (to build `base`), workspace discoveries (merged
 *          into the sim in place as they arrive), workspace.layout, and the
 *          highlight ids the teacher lights up.
 *   OWNS   everything mutable/sim-side — `base` keeps object identity for a
 *          graph's whole life; react-force-graph mutates its objects, which
 *          is exactly why none of this may live in Redux.
 *
 * `children` renders inside the canvas wrap — the shell drops its overlays
 * (hit list, loading/error/hint) there without this component knowing them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { AnswerFigure } from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { selectHighlightSet } from '../store/highlight'
import {
  layoutSet,
  loadGraph,
  selectHasDiscovered,
  selectHasSearchHits,
  selectWorkspace,
  visibleNodesSet,
} from '../store/workspace'
import { useSelection } from '../detail/useSelection'
import DetailPanel from '../detail/DetailPanel'
import Lightbox from '../figures/Lightbox'
import GraphCanvas from './canvas/GraphCanvas'
import GraphControls from './controls/GraphControls'
import Legend from './controls/Legend'
import { REL_DEFAULT_LIMIT, REL_TYPES } from './theme'
import { useDiscovery } from './hooks/useDiscovery'
import { usePinning } from './hooks/usePinning'
import { useTimeline } from './hooks/useTimeline'
import type { Base, VLink, VNode } from './model'

/**
 * Render the graph area: canvas + controls + legend + detail panel, plus the
 * shell's overlays as `children`.
 *
 * @returns The graph exploration area.
 */
export default function GraphExplorer({ children }: { children?: ReactNode }) {
  const dispatch = useAppDispatch()
  const { graph, discoveredNodes, discoveredEdges, layout, loading, seedRef } =
    useAppSelector(selectWorkspace)
  const highlightIds = useAppSelector(selectHighlightSet)
  const hasDiscovered = useAppSelector(selectHasDiscovered)
  const hasSearchHits = useAppSelector(selectHasSearchHits)

  // Declutter controls. 'search' is always on (no filter chip): topic-search
  // hits are agent-discovered and few, so they stay visible; the year slider
  // still filters them.
  const [enabled, setEnabled] = useState<Set<string>>(new Set([...REL_TYPES, 'search']))
  // Per-relation visible count (the live sliders). The backend ships the whole
  // ranked pool; this keeps ranks 0..limit-1 of each relation, seeded from the
  // defaults on load and capped to what the paper actually has.
  const [limits, setLimits] = useState<Record<string, number>>({ ...REL_DEFAULT_LIMIT })
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  const [hoverId, setHoverId] = useState<string | null>(null)
  // The detail panel's figures, enlarged full-screen (same lightbox the
  // teacher's answer figures use).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)

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
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
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
    fitDone.current = false
    const nodes: VNode[] = graph.nodes.map((node) => ({ ...node }))
    const links: VLink[] = graph.edges.map((edge) => ({
      ...edge,
      _s: edge.source,
      _t: edge.target,
    }))
    const years = nodes
      .map((node) => node.year)
      .filter((year): year is number => typeof year === 'number')
    const counts: Record<string, number> = { reference: 0, citation: 0, latest: 0, similar: 0 }
    nodes.forEach((node) =>
      node.rels.forEach((rel) => {
        if (rel in counts) counts[rel]++
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

  // Reset the declutter controls whenever a new graph loads. (Selection and
  // pins reset themselves inside their own hooks.)
  useEffect(() => {
    if (!base) return
    setEnabled(new Set([...REL_TYPES, 'search']))
    // Each slider starts at its default, clamped to what this paper actually has.
    setLimits(
      Object.fromEntries(
        REL_TYPES.map((type) => [type, Math.min(REL_DEFAULT_LIMIT[type], base.counts[type] ?? 0)]),
      ),
    )
    setYearLo(base.minYear)
    setYearHi(base.maxYear)
    setHoverId(null)
  }, [base])

  // Timeline layout physics (year-column pinning, collide force, year axis,
  // settle-freeze) — plus its keep-in-sync effects.
  const { nodeTimelineX, applyLayoutPhysics, drawAxis, freezeSettledY } = useTimeline({
    base,
    layout,
    fgRef,
    size,
    fitDone,
    yearLo,
    yearHi,
  })

  // User pins: drag-to-pin, the detail panel's Pin button, Release-all.
  const { pinned, clearPins, onNodeDragEnd, togglePin, releaseAll } = usePinning({
    base,
    layout,
    nodeTimelineX,
    fgRef,
    fitDone,
  })

  const doLoadGraph = useCallback(
    (seed: string) => {
      dispatch(loadGraph({ seed }))
    },
    [dispatch],
  )

  /**
   * Re-fetch the current seed bypassing the server's day-cached snapshot,
   * busting the exact cache entry (`graph:{seedRef}`) so a paper whose S2 data
   * changed mid-session picks up the new neighborhood on demand.
   */
  const onRefresh = useCallback(() => {
    if (seedRef) dispatch(loadGraph({ seed: seedRef, refresh: true }))
  }, [dispatch, seedRef])

  // Selection: the open detail panel, its hydration + figures + code links +
  // category tags.
  const {
    selectedId,
    setSelectedId,
    selected,
    figures,
    figLoading,
    codeLinks,
    categories,
    onNodeClick,
  } = useSelection({ base, graph, loadGraph: doLoadGraph })

  // The sim-side discovery merge. The discovery LISTS live in the store (the
  // teacher dispatches them); this effect feeds them into the in-place merge,
  // whose internal dedupe makes re-feeding the full arrays safe.
  const { graphVersion, onDiscover } = useDiscovery({
    base,
    layout,
    nodeTimelineX,
    fgRef,
    onYearLo: setYearLo,
    onYearHi: setYearHi,
  })
  useEffect(() => {
    if (discoveredNodes.length || discoveredEdges.length)
      onDiscover(discoveredNodes, discoveredEdges)
  }, [discoveredNodes, discoveredEdges, onDiscover])

  /**
   * The filtered view the canvas renders. Nodes keep their identity (so
   * positions/pins persist); links are copied with source/target reset to ids
   * so RFG re-resolves cleanly.
   */
  const view = useMemo(() => {
    if (!base) return { nodes: [] as VNode[], links: [] as VLink[] }
    // An edge is allowed when its relation is toggled on AND its rank falls
    // within that relation's slider (search edges have no slider — always on).
    // Ranks are per-relation; a `similar` slider of 15 keeps similar ranks 0-14
    // regardless of how many references are shown.
    const linkOk = (link: VLink) => {
      if (!enabled.has(link.type)) return false
      if (!(link.type in limits)) return true // 'search' — no per-relation cap
      return (link.rank ?? 0) < limits[link.type]
    }
    // A neighbor is shown when at least one edge reaches it within the sliders;
    // the seed is always shown. Nodes reached only via a hidden/over-limit edge
    // drop out — that's how a slider trims the graph, dedupe-safe (a paper kept
    // by its reference edge stays even if its similar edge is over the limit).
    const reachable = new Set<string>()
    base.links.forEach((link) => {
      if (linkOk(link)) {
        reachable.add(link._s)
        reachable.add(link._t)
      }
    })
    const nodeOk = (node: VNode) => {
      if (node.is_seed) return true // the seed is always shown, ignoring filters
      if (typeof node.year === 'number' && (node.year < yearLo || node.year > yearHi)) return false
      return reachable.has(node.id)
    }
    const nodes = base.nodes.filter(nodeOk)
    const ids = new Set(nodes.map((node) => node.id))
    const links = base.links
      .filter((link) => linkOk(link) && ids.has(link._s) && ids.has(link._t))
      .map((link) => ({ ...link, source: link._s, target: link._t }))
    return { nodes, links }
    // graphVersion isn't read directly — it's a signal that base.nodes/links
    // were mutated in place (discoveries) and this must recompute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, enabled, limits, yearLo, yearHi, graphVersion])

  // Publish the on-screen node ids so agent grounding (selectGroundingNodes)
  // tracks the visible view, not the whole shipped pool. Fires whenever the
  // filters change; consumers re-render only when the id set actually differs.
  useEffect(() => {
    dispatch(visibleNodesSet(view.nodes.map((node) => node.id)))
  }, [view, dispatch])

  /** Neighbors of the hovered node (for focus-on-hover dimming). */
  const hoverSet = useMemo(() => {
    if (!base || !hoverId) return null
    const neighbors = new Set<string>([hoverId])
    base.links.forEach((link) => {
      if (link._s === hoverId) neighbors.add(link._t)
      if (link._t === hoverId) neighbors.add(link._s)
    })
    return neighbors
  }, [base, hoverId])

  /** What to focus the canvas on: hovering wins; otherwise the papers the AI
   * teacher is currently talking about. */
  const focusSet = useMemo(
    () => hoverSet ?? (highlightIds.size ? highlightIds : null),
    [hoverSet, highlightIds],
  )

  /** Toggle one relation type's visibility (the filter chips). */
  const toggleType = useCallback((type: string) => {
    setEnabled((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  /** Set one relation's visible count (the live count sliders). */
  const setLimit = useCallback((type: string, value: number) => {
    setLimits((prev) => ({ ...prev, [type]: value }))
  }, [])

  /**
   * Switch layout. The physics live in useTimeline; clearing pin state stays
   * here because switching layout releases all user pins. (A restored
   * session's layout arrives via the store instead — useTimeline's own
   * new-base effect pins its year columns, no user pins to clear.)
   */
  const setLayoutMode = useCallback(
    (mode: 'force' | 'timeline') => {
      dispatch(layoutSet(mode))
      if (!base) return
      applyLayoutPhysics(mode)
      clearPins()
    },
    [dispatch, base, applyLayoutPhysics, clearPins],
  )

  /** When the sim settles: freeze Timeline y positions and run the one-shot
   * zoomToFit. */
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
    <>
      <main className="canvas-wrap" ref={wrapRef}>
        {children}

        {hasGraph && (
          <GraphControls
            layout={layout}
            onLayout={setLayoutMode}
            enabled={enabled}
            onToggleType={toggleType}
            counts={base!.counts}
            limits={limits}
            onLimit={setLimit}
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
            onRefresh={onRefresh}
            refreshing={loading}
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

        {hasGraph && <Legend hasDiscovered={hasDiscovered} hasSearchHits={hasSearchHits} />}
      </main>

      {selected && (
        <DetailPanel
          node={selected}
          figures={selected.arxiv_id ? figures[selected.arxiv_id] : undefined}
          figuresLoading={figLoading === selected.arxiv_id}
          codeLinks={selected.arxiv_id ? codeLinks[selected.arxiv_id] : undefined}
          categories={selected.arxiv_id ? categories[selected.arxiv_id] : undefined}
          onEnlarge={setLightbox}
          isPinned={pinned.has(selected.id)}
          onTogglePin={() => togglePin(selected.id)}
          onClose={() => setSelectedId(null)}
          onExplore={doLoadGraph}
        />
      )}
      {lightbox && <Lightbox figure={lightbox} onClose={() => setLightbox(null)} />}
    </>
  )
}
