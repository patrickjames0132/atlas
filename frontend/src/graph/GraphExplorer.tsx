/**
 * The graph exploration area: the canvas, its controls, the legend, and the
 * detail panel — plus every piece of state only they read (the `base` sim
 * dataset, declutter filters, hover, selection, canvas size).
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
import { useAppDispatch, useAppSelector } from '../store'
import { selectHighlightSet } from '../store/highlight'
import {
  layoutSet,
  loadGraph,
  selectHasDiscovered,
  selectHasSearchHits,
  selectWorkspace,
} from '../store/workspace'
import { useSelection } from '../detail/useSelection'
import DetailPanel from '../detail/DetailPanel'
import GraphCanvas from './GraphCanvas'
import GraphControls from './GraphControls'
import Legend from './Legend'
import { REL_TYPES } from './theme'
import { useDiscovery } from './hooks/useDiscovery'
import { usePinning } from './hooks/usePinning'
import { useTimeline } from './hooks/useTimeline'
import type { Base, VLink, VNode } from './model'

export default function GraphExplorer({ children }: { children?: ReactNode }) {
  const dispatch = useAppDispatch()
  const { graph, discoveredNodes, discoveredEdges, layout } =
    useAppSelector(selectWorkspace)
  const highlightIds = useAppSelector(selectHighlightSet)
  const hasDiscovered = useAppSelector(selectHasDiscovered)
  const hasSearchHits = useAppSelector(selectHasSearchHits)

  // Declutter controls. 'search' is always on (no filter chip): topic-search
  // hits are agent-discovered and few, so they stay visible; the year slider
  // still filters them.
  const [enabled, setEnabled] = useState<Set<string>>(new Set([...REL_TYPES, 'search']))
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  const [hoverId, setHoverId] = useState<string | null>(null)

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
    const nodes: VNode[] = graph.nodes.map((n) => ({ ...n }))
    const links: VLink[] = graph.edges.map((e) => ({ ...e, _s: e.source, _t: e.target }))
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

  // Reset the declutter controls whenever a new graph loads. (Selection and
  // pins reset themselves inside their own hooks.)
  useEffect(() => {
    if (!base) return
    setEnabled(new Set([...REL_TYPES, 'search']))
    setYearLo(base.minYear)
    setYearHi(base.maxYear)
    setHoverId(null)
  }, [base])

  // Timeline layout physics (year-column pinning, collide force, year axis,
  // settle-freeze) — plus its keep-in-sync effects.
  const { nodeTimelineX, applyLayoutPhysics, drawAxis, freezeSettledY } = useTimeline({
    base, layout, fgRef, size, fitDone, yearLo, yearHi,
  })

  // User pins: drag-to-pin, the detail panel's Pin button, Release-all.
  const { pinned, clearPins, onNodeDragEnd, togglePin, releaseAll } = usePinning({
    base, layout, nodeTimelineX, fgRef, fitDone,
  })

  const doLoadGraph = useCallback(
    (seed: string) => {
      dispatch(loadGraph(seed))
    },
    [dispatch],
  )

  // Selection: the open detail panel, its hydration + figures + code links.
  const { selectedId, setSelectedId, selected, figures, figLoading, codeLinks, onNodeClick } =
    useSelection({ base, graph, loadGraph: doLoadGraph })

  // The sim-side discovery merge. The discovery LISTS live in the store (the
  // teacher dispatches them); this effect feeds them into the in-place merge,
  // whose internal dedupe makes re-feeding the full arrays safe.
  const { graphVersion, onDiscover } = useDiscovery({
    base, layout, nodeTimelineX, fgRef, onYearLo: setYearLo, onYearHi: setYearHi,
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
    const nodeOk = (n: VNode) => {
      if (n.is_seed) return true
      if (!n.rels.some((r) => r !== 'seed' && enabled.has(r))) return false
      if (typeof n.year === 'number' && (n.year < yearLo || n.year > yearHi)) return false
      return true
    }
    const nodes = base.nodes.filter(nodeOk)
    const ids = new Set(nodes.map((n) => n.id))
    const links = base.links
      .filter((l) => enabled.has(l.type) && ids.has(l._s) && ids.has(l._t))
      .map((l) => ({ ...l, source: l._s, target: l._t }))
    return { nodes, links }
    // graphVersion isn't read directly — it's a signal that base.nodes/links
    // were mutated in place (discoveries) and this must recompute.
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

  /** What to focus the canvas on: hovering wins; otherwise the papers the AI
   * teacher is currently talking about. */
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

        {hasGraph && <Legend hasDiscovered={hasDiscovered} hasSearchHits={hasSearchHits} />}
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
          onExplore={doLoadGraph}
        />
      )}
    </>
  )
}
