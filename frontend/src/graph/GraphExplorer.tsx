/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
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
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { generateTldr } from '../api'
import type { AnswerFigure } from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { highlightSet, selectHighlightSet } from '../store/highlight'
import {
  layoutSet,
  loadGraph,
  nodeSelectionAdded,
  nodeSelectionCleared,
  nodeSelectionToggled,
  selectHasDiscovered,
  selectHasSearchHits,
  selectNodeSelectionSet,
  selectWorkspace,
  visibleNodesSet,
} from '../store/workspace'
import { useSelection } from '../detail/useSelection'
import DetailPanel from '../detail/DetailPanel'
import Lightbox from '../figures/Lightbox'
import GraphCanvas from './canvas/GraphCanvas'
import FindBar from './controls/FindBar'
import GraphControls from './controls/GraphControls'
import Legend from './controls/Legend'
import { useBuildShape } from './buildShape'
import { REL_TYPES } from './theme'
import { deriveOrigins } from './clusterForce'
import { useDiscovery } from './hooks/useDiscovery'
import { useEscapeClear } from './hooks/useEscapeClear'
import { useMarquee } from './hooks/useMarquee'
import { usePinning } from './hooks/usePinning'
import { useTimeline } from './hooks/useTimeline'
import {
  CITE_SLIDER_STEPS,
  citationThreshold,
  findMatches,
  type Base,
  type VLink,
  type VNode,
} from './model'

/**
 * Render the graph area: canvas + controls + legend + detail panel, plus the
 * shell's overlays as `children`. `tourStage` is the guided tour's staging
 * signal: when it asks for `'details'` and nothing is selected, the seed is
 * selected so the detail-panel stops have a panel to walk, and `'controls'`
 * passes down to GraphControls to expand a collapsed panel (the selection
 * and the expansion both stay after — a tour that tidies up behind itself
 * would be jarring).
 *
 * @returns The graph exploration area.
 */
/**
 * The Field-Landmarks provider note: tells the user which citation source backs
 * an s2 graph's landmarks, or null when it doesn't apply (OpenAlex returns its
 * landmarks server-sorted; no graph yet means nothing to annotate).
 *
 * @param provider        The active data provider.
 * @param citationSource  Where the s2 graph's citers came from ('corpus' full
 *                        history, or 'live' recency-biased), when known.
 * @returns The note text, or null when no note should show.
 */
function landmarkNote(
  provider: 's2' | 'openalex',
  citationSource: 'corpus' | 'live' | null | undefined,
): string | null {
  if (provider !== 's2') return null
  if (citationSource === 'corpus') {
    return 'Semantic Scholar: Field Landmarks are drawn from the offline citations corpus — the full citation history, ranked by citation count.'
  }
  return 'Semantic Scholar: Field Landmarks are the top-cited among the ~10k most recent citers (live-API limit), not the full citation history — the citations corpus will lift this.'
}

export default function GraphExplorer({
  children,
  tourStage,
}: {
  children?: ReactNode
  tourStage?: string
}) {
  const dispatch = useAppDispatch()
  const { graph, discoveredNodes, discoveredEdges, layout, loading, seedRef, provider } =
    useAppSelector(selectWorkspace)
  const highlightIds = useAppSelector(selectHighlightSet)
  const selectedIds = useAppSelector(selectNodeSelectionSet)
  const hasDiscovered = useAppSelector(selectHasDiscovered)
  const hasSearchHits = useAppSelector(selectHasSearchHits)

  // Declutter controls. 'search' and 'similar' are always on (no filter chip):
  // both only appear on papers the researcher pulled in mid-conversation (few,
  // agent-discovered), so they stay visible; the year slider still filters them.
  const [enabled, setEnabled] = useState<Set<string>>(new Set([...REL_TYPES, 'search', 'similar']))
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  // The citation-count window's knob positions (0…CITE_SLIDER_STEPS). Full-open
  // by default (show every paper); a display filter over the already
  // citation-budgeted pool the backend ships — see `citationThreshold`.
  const [citeLo, setCiteLo] = useState(0)
  const [citeHi, setCiteHi] = useState(CITE_SLIDER_STEPS)
  // Per-relation display caps: how many papers of each relation to show, most-
  // cited first. A missing key means "all of them", which is every relation
  // until the user drags a slider. These only exist while the build is
  // user-sized — an adaptive build is already trimmed by the backend's own
  // rules, and stacking a second trim on top of it is the clutter the adaptive
  // sizing exists to avoid.
  const [relCaps, setRelCaps] = useState<Record<string, number>>({})
  const buildShape = useBuildShape()
  const capsActive = !buildShape.adaptive
  const [hoverId, setHoverId] = useState<string | null>(null)
  // The local find (the floating bottom-right FindBar): spotlights on-screen
  // papers by title/author substring. Purely lexical — no API call.
  const [findQuery, setFindQuery] = useState('')
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
    // A restored session's discoveries arrive folded into the graph itself —
    // re-derive their expansion origins so the satellites re-form (live
    // discoveries get stamped by useDiscovery's merge instead).
    deriveOrigins(nodes, links, graph.seed.id)
    const years = nodes
      .map((node) => node.year)
      .filter((year): year is number => typeof year === 'number')
    const counts: Record<string, number> = { reference: 0, citation: 0, latest: 0, similar: 0 }
    nodes.forEach((node) =>
      node.rels.forEach((rel) => {
        if (rel in counts) counts[rel]++
      }),
    )
    // The citation slider's bounds ignore the seed — it's fixed-large and always
    // shown, so it shouldn't stretch the scale the neighbors filter on. Spanning
    // the real min…max (like the year slider) keeps both knobs live.
    const neighborCitations = nodes
      .filter((node) => !node.is_seed)
      .map((node) => node.citation_count ?? 0)
    const minCitations = neighborCitations.length ? Math.min(...neighborCitations) : 0
    const maxCitations = neighborCitations.length ? Math.max(...neighborCitations) : 0
    return {
      nodes,
      links,
      minYear: years.length ? Math.min(...years) : 0,
      maxYear: years.length ? Math.max(...years) : 0,
      counts,
      minCitations,
      maxCitations,
    }
  }, [graph])

  // Reset the declutter controls whenever a new graph loads. (Selection and
  // pins reset themselves inside their own hooks.)
  useEffect(() => {
    if (!base) return
    setEnabled(new Set([...REL_TYPES, 'search', 'similar']))
    setYearLo(base.minYear)
    setYearHi(base.maxYear)
    // A fresh graph shows every citation count; the user narrows from there.
    setCiteLo(0)
    setCiteHi(CITE_SLIDER_STEPS)
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
    detailLoading,
    figures,
    codeLinks,
    categories,
    onNodeClick,
    mergeDetail,
  } = useSelection({ base, graph, provider, loadGraph: doLoadGraph })

  // The guided tour's detail-panel stops: when the tour stages 'details' and
  // nothing is selected (the user ✕'d the panel), select the seed so the
  // walk has a panel to spotlight.
  useEffect(() => {
    if (tourStage === 'details' && !selectedId && graph) setSelectedId(graph.seed.id)
  }, [tourStage, selectedId, graph, setSelectedId])

  /**
   * Canvas click, split by modifier: a shift-click toggles the node in the
   * hand-picked selection (never opening the detail panel or re-seeding); a
   * plain click falls through to the usual select/re-seed behavior.
   */
  const onCanvasNodeClick = useCallback(
    (node: VNode, event?: MouseEvent) => {
      if (event?.shiftKey) {
        dispatch(nodeSelectionToggled(node.id))
        return
      }
      onNodeClick(node)
    },
    [dispatch, onNodeClick],
  )

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
  /**
   * Each relation's papers ranked most-cited first, as `id -> rank`, plus how
   * many it holds — what the per-chip count sliders bound and trim against.
   *
   * Ranked over `base`, not the filtered view, so dragging the year slider
   * doesn't silently renumber what "top 20 landmarks" means. Most-cited first
   * mirrors how the backend ranks each relation, so the slider trims the tail
   * the same way the adaptive budget would have.
   */
  const { relRank, relTotals } = useMemo(() => {
    const rank = new Map<string, Map<string, number>>()
    const totals: Record<string, number> = {}
    if (!base) return { relRank: rank, relTotals: totals }
    for (const type of REL_TYPES) {
      const members = base.nodes
        .filter((node) => !node.is_seed && node.rels.includes(type))
        .sort((one, other) => (other.citation_count ?? 0) - (one.citation_count ?? 0))
      rank.set(type, new Map(members.map((node, index) => [node.id, index])))
      totals[type] = members.length
    }
    return { relRank: rank, relTotals: totals }
  }, [base])

  const view = useMemo(() => {
    if (!base) return { nodes: [] as VNode[], links: [] as VLink[] }
    // The citation window a neighbor must fall inside (0…maxCitations = filter
    // off). The backend already ranks by citations and caps the pool; this is a
    // live display trim on top of it.
    const citeMin = citationThreshold(citeLo, base.minCitations, base.maxCitations)
    const citeMax = citationThreshold(citeHi, base.minCitations, base.maxCitations)
    // An edge is allowed when its relation chip is toggled on ('search' edges
    // have no chip — always on). Node-type filtering now lives entirely in the
    // chips; the citation slider trims by magnitude on the node side below.
    const linkOk = (link: VLink) => enabled.has(link.type)
    // A neighbor is shown when at least one enabled edge reaches it; the seed is
    // always shown. Nodes reached only via a hidden relation drop out — that's
    // how a chip trims the graph, dedupe-safe (a paper kept by its reference
    // edge stays even if its similar relation is hidden). `linked` tracks nodes
    // with ANY edge, so a genuinely edge-less node (an ungrounded topic-search
    // hit) can be told apart from one hidden by its relation.
    const reachable = new Set<string>()
    const linked = new Set<string>()
    base.links.forEach((link) => {
      linked.add(link._s)
      linked.add(link._t)
      if (linkOk(link)) {
        reachable.add(link._s)
        reachable.add(link._t)
      }
    })
    const nodeOk = (node: VNode) => {
      if (node.is_seed) return true // the seed is always shown, ignoring filters
      // Timeline is a time axis: placing a paper on it claims a publication
      // date, and an undated paper gives us none to claim. They used to be
      // parked on the seed's column, which drew them as a vertical bar through
      // the seed — so Timeline hides them and Force (where x means nothing)
      // still shows them.
      if (layout === 'timeline' && typeof node.year !== 'number') return false
      if (typeof node.year === 'number' && (node.year < yearLo || node.year > yearHi)) return false
      const citations = node.citation_count ?? 0
      if (citations < citeMin || citations > citeMax) return false
      if (reachable.has(node.id)) return true
      // Ungrounded topic-search hits have NO edge to be reached by — show them
      // when their own relation ('search', always-on) is enabled. A node hidden
      // only because its relation is off (it HAS edges, just none enabled) stays
      // hidden.
      if (!linked.has(node.id)) return node.rels.some((rel) => enabled.has(rel))
      return false
    }
    const filtered = base.nodes.filter(nodeOk)
    // PER-RELATION COUNT CAPS — the sliders that exist only while the build is
    // user-sized (adaptive off). Non-adaptive builds ship everything up to the
    // payload guard, so this is where the user trims it back to something
    // readable. A node survives when it ranks inside the cap of at least ONE of
    // its enabled relations, mirroring the reachability rule above: a paper
    // that's both a top reference and a mid-ranked landmark keeps the slot its
    // best relation earns it.
    const nodes = capsActive
      ? filtered.filter((node) => {
          const capped = node.rels.filter((rel) => enabled.has(rel) && relCaps[rel] !== undefined)
          // No capped relation applies (or it's the seed) — nothing to trim by.
          if (node.is_seed || capped.length === 0) return true
          return capped.some((rel) => (relRank.get(rel)?.get(node.id) ?? 0) < relCaps[rel])
        })
      : filtered
    const ids = new Set(nodes.map((node) => node.id))
    const links = base.links
      .filter((link) => linkOk(link) && ids.has(link._s) && ids.has(link._t))
      .map((link) => ({ ...link, source: link._s, target: link._t }))
    return { nodes, links }
    // graphVersion isn't read directly — it's a signal that base.nodes/links
    // were mutated in place (discoveries) and this must recompute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    base,
    enabled,
    layout,
    yearLo,
    yearHi,
    citeLo,
    citeHi,
    graphVersion,
    capsActive,
    relCaps,
    relRank,
  ])

  // Publish the on-screen node ids so agent grounding (selectGroundingNodes)
  // tracks the visible view, not the whole shipped pool. Fires whenever the
  // filters change; consumers re-render only when the id set actually differs.
  useEffect(() => {
    dispatch(visibleNodesSet(view.nodes.map((node) => node.id)))
  }, [view, dispatch])

  // Alt-drag marquee selection: arms while Alt is held, captures the drag on an
  // overlay so RFG never pans, and commits the enclosed nodes to the selection.
  const marquee = useMarquee({ view, fgRef, wrapRef })

  /** Drop every active highlight at once — the hand-picked selection, the
   * teacher's lit papers (whose beat/answer/ref marks follow the emptied
   * highlight; see useConversation), AND the local find. One gesture,
   * wherever the light came from. */
  const onClearAll = useCallback(() => {
    dispatch(nodeSelectionCleared())
    dispatch(highlightSet([]))
    setFindQuery('')
  }, [dispatch])
  // Esc = the same reset, unless an overlay owns the key right now: the
  // lightbox and the tour both close on their own Esc, and clearing the graph
  // underneath them would be a surprise.
  useEscapeClear(
    useCallback(() => {
      if (lightbox || tourStage) return
      onClearAll()
    }, [lightbox, tourStage, onClearAll]),
  )

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

  /** The local find's matches over the VISIBLE view (hidden papers can't
   * match invisibly), or null when the box is empty. */
  const findSet = useMemo(() => findMatches(view.nodes, findQuery), [view, findQuery])

  // A new graph starts with an empty find box — a query about the old
  // neighborhood has nothing honest to match against the new one.
  useEffect(() => {
    setFindQuery('')
  }, [base])

  /** What the canvas lights up: an active find takes the highlight machinery
   * over from the teacher (glow + labels on matches — clearing the box hands
   * it back). */
  const litSet = useMemo(() => findSet ?? highlightIds, [findSet, highlightIds])

  /** The find pill's one-press select: commit every current match to the
   * hand-picked teacher scope (additive, like the marquee) and clear the
   * find, so the cyan selection — not the find spotlight — shows the result. */
  const onFindSelectAll = useCallback(() => {
    if (!findSet || findSet.size === 0) return
    dispatch(nodeSelectionAdded([...findSet]))
    setFindQuery('')
  }, [dispatch, findSet])

  /** What to focus the canvas on: hovering wins; then an active find (an
   * EMPTY match set dims everything — honest "no hits" feedback); then the
   * papers the AI teacher is currently talking about. */
  const focusSet = useMemo(
    () => hoverSet ?? findSet ?? (highlightIds.size ? highlightIds : null),
    [hoverSet, findSet, highlightIds],
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
  }, [hoverId, selectedId, selectedIds, pinned, view, highlightIds, layout])

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
            showRelCaps={capsActive}
            relCaps={relCaps}
            relTotals={relTotals}
            onRelCap={(type, cap) =>
              setRelCaps((prev) => {
                const next = { ...prev }
                // At full span the cap stops existing rather than being set to
                // the total — so a later discovery widening the relation isn't
                // silently clipped to yesterday's count.
                if (cap >= (relTotals[type] ?? 0)) delete next[type]
                else next[type] = cap
                return next
              })
            }
            minYear={base!.minYear}
            maxYear={base!.maxYear}
            yearLo={yearLo}
            yearHi={yearHi}
            onYearLo={setYearLo}
            onYearHi={setYearHi}
            minCitations={base!.minCitations}
            maxCitations={base!.maxCitations}
            citeLo={citeLo}
            citeHi={citeHi}
            onCiteLo={setCiteLo}
            onCiteHi={setCiteHi}
            visibleCount={view.nodes.length}
            totalCount={base!.nodes.length}
            selectedCount={selectedIds.size}
            litCount={highlightIds.size}
            onClearAll={onClearAll}
            pinnedCount={pinned.size}
            onReleaseAll={releaseAll}
            onFit={() => fgRef.current?.zoomToFit(400, 60)}
            onRefresh={onRefresh}
            refreshing={loading}
            providerNote={landmarkNote(provider, graph?.citation_source)}
            stagedOpen={tourStage === 'controls'}
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
            selectedIds={selectedIds}
            highlightIds={litSet}
            onNodeClick={onCanvasNodeClick}
            onNodeHover={setHoverId}
            onNodeDragEnd={onNodeDragEnd}
            onEngineStop={onEngineStop}
            onRenderFramePre={drawAxis}
          />
        )}

        {/* Marquee node-selector: the arm overlay captures the alt-drag (so RFG
            never pans) and the outline paints the in-progress rectangle. The arm
            sits below the controls (z-index) so alt-interacting with the panel
            still works; it's inert unless Alt is held. */}
        {hasGraph && (
          <div
            className={`marquee-arm${marquee.armed ? ' armed' : ''}`}
            onMouseDown={marquee.onArmMouseDown}
          />
        )}
        {marquee.rect && (
          <div
            className="marquee-rect"
            style={{
              left: marquee.rect.left,
              top: marquee.rect.top,
              width: marquee.rect.width,
              height: marquee.rect.height,
            }}
          />
        )}

        {hasGraph && (
          <FindBar
            query={findQuery}
            onQuery={setFindQuery}
            count={findSet ? findSet.size : null}
            onSelectAll={onFindSelectAll}
          />
        )}
        {hasGraph && <Legend hasDiscovered={hasDiscovered} hasSearchHits={hasSearchHits} />}
      </main>

      {selected && (
        <DetailPanel
          node={selected}
          detailLoading={detailLoading === selected.id}
          fieldsLabel={provider === 'openalex' ? 'OpenAlex tags' : 'Semantic Scholar tags'}
          figures={figures[selected.arxiv_id ?? selected.id]}
          codeLinks={selected.arxiv_id ? codeLinks[selected.arxiv_id] : undefined}
          categories={selected.arxiv_id ? categories[selected.arxiv_id] : undefined}
          onEnlarge={setLightbox}
          isPinned={pinned.has(selected.id)}
          onTogglePin={() => togglePin(selected.id)}
          onClose={() => setSelectedId(null)}
          onExplore={doLoadGraph}
          onGenerateTldr={async () => {
            // The panel's TL;DR toggle — the one gesture allowed to bill.
            const tldr = await generateTldr(selected.id, selected.title, selected.abstract ?? '')
            mergeDetail(selected.id, { tldr })
          }}
        />
      )}
      {lightbox && <Lightbox figure={lightbox} onClose={() => setLightbox(null)} />}
    </>
  )
}
