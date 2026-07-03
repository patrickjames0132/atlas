/**
 * The arXiv Atlas explorer — owns all graph state and the force simulation.
 *
 * This component holds: seed search + graph loading, the stable `base`
 * node/link objects the simulation mutates, the filtered `view`, selection /
 * hover / highlight / pin state, layout switching (force vs. timeline), the
 * teacher's mid-conversation graph discoveries, and saved-session save /
 * restore (Phase 4).
 *
 * Presentational pieces live in `explorer/`: HitList (seed search results),
 * GraphControls (filters + layout), DetailPanel (selected paper), Legend,
 * plus the shared theme constants and view-model helpers.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import ForceGraph2DImport from 'react-force-graph-2d'
// react-force-graph's own force lib (d3-force-3d) ships no types; we only need
// forceCollide to space timeline nodes out by their radius.
// @ts-expect-error - no type declarations
import { forceCollide } from 'd3-force-3d'
import {
  fetchFigures,
  fetchGraph,
  fetchPaperDetail,
  getSession,
  saveSession,
  searchArxiv,
  searchLocal,
  type ArxivHit,
  type Beat,
  type ChatMsg,
  type FiguresResponse,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
  type LectureTrace,
  type LocalHit,
  type SavedSessionMeta,
  listSources,
} from './api'
import {
  ID_RE,
  cleanNode,
  countRels,
  nodeRadius,
  primaryRel,
  type Base,
  type VLink,
  type VNode,
} from './explorer/model'
import {
  DIM_EDGE,
  DIM_NODE,
  EDGE_COLOR,
  REL_COLOR,
  REL_TYPES,
  YEAR_SPACING,
} from './explorer/theme'
import HitList from './explorer/HitList'
import GraphControls from './explorer/GraphControls'
import DetailPanel from './explorer/DetailPanel'
import Legend from './explorer/Legend'
import Teacher from './Teacher'
import Sources from './Sources'
import Sessions from './Sessions'
import LibraryChat from './LibraryChat'
import './atlas.css'

// The lib's generic prop typings fight our accessor signatures; render via an
// untyped alias so our canvas/link callbacks stay readable.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = ForceGraph2DImport as any

export default function GraphExplorer() {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<ArxivHit[] | null>(null)
  // Cache-first results: papers already seen on previous graphs, shown the
  // moment they resolve (before the live arXiv search lands) — and the only
  // results available when the APIs are rate-limiting us.
  const [localHits, setLocalHits] = useState<LocalHit[] | null>(null)
  const [arxivFailed, setArxivFailed] = useState(false)
  const [searching, setSearching] = useState(false)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, Partial<GraphNode>>>({})
  // Figures (ar5iv) per arXiv id, lazily fetched when a node is opened.
  const [figures, setFigures] = useState<Record<string, FiguresResponse>>({})
  const [figLoading, setFigLoading] = useState<string | null>(null)

  // Declutter controls.
  // 'search' is always on (no filter chip): topic-search hits are agent-
  // discovered and few, so they stay visible; the year slider still filters them.
  const [enabled, setEnabled] = useState<Set<string>>(new Set([...REL_TYPES, 'search']))
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  const [pinned, setPinned] = useState<Set<string>>(new Set())
  const [hoverId, setHoverId] = useState<string | null>(null)
  // Nodes the AI teacher is currently talking about (active beat / cited papers).
  const [highlightIds, setHighlightIds] = useState<Set<string>>(new Set())
  // 'force' = organic force-directed; 'timeline' = x pinned to publication year.
  const [layout, setLayout] = useState<'force' | 'timeline'>('force')
  // Papers the Q&A agent has pulled in via expand_node this session (Phase 3b.2).
  // Mirrors what's been pushed into `base.nodes` — kept separately so it can
  // extend the teacher's grounding context on follow-up questions without
  // forcing `base` to rebuild (which would drop the sim's x/y on every node).
  const [discoveredNodes, setDiscoveredNodes] = useState<GraphNode[]>([])
  // Bumped whenever discoveredNodes/edges are pushed into `base` in place, so
  // `view` (and anything else keyed on it) recomputes despite `base` itself
  // keeping the same object identity.
  const [graphVersion, setGraphVersion] = useState(0)
  // The Sources drawer (Phase 3d) — the user's local semantic library.
  const [showSources, setShowSources] = useState(false)
  // Offline library chat (Phase 3d): a graph-free RAG chat over the library. We
  // track whether a library exists (>0 sources) so the entry point only shows
  // when there's something to ask; refreshed whenever the Sources drawer closes.
  const [showLibraryChat, setShowLibraryChat] = useState(false)
  const [libraryCount, setLibraryCount] = useState(0)
  // Saved sessions & workspaces (Phase 4).
  const [showSessions, setShowSessions] = useState(false)
  // Bumped on every graph load / restore. Used as the Teacher's key so it
  // remounts with a fresh conversation on each re-seed (or the restored one).
  const [graphKey, setGraphKey] = useState(0)
  // The transcript to seed the NEXT Teacher mount: empty for a fresh re-seed,
  // the saved chat/beats when restoring. Read at mount, so it's a ref.
  const teacherInitRef = useRef<{ chat: ChatMsg[]; beats: Beat[]; histTrace: LectureTrace[] }>({
    chat: [],
    beats: [],
    histTrace: [],
  })
  // The Teacher's latest transcript, reported up so Save can capture it.
  const teacherStateRef = useRef<{ chat: ChatMsg[]; beats: Beat[]; histTrace: LectureTrace[] }>({
    chat: [],
    beats: [],
    histTrace: [],
  })
  // A layout to apply once a restored graph is in place (see effect below).
  const restoreLayoutRef = useRef<'force' | 'timeline' | null>(null)
  const handleTeacherState = useCallback(
    (s: { chat: ChatMsg[]; beats: Beat[]; histTrace: LectureTrace[] }) => {
      teacherStateRef.current = s
    },
    [],
  )

  const refreshLibraryCount = useCallback(() => {
    listSources().then((res) => setLibraryCount(res.sources.length)).catch(() => {})
  }, [])
  useEffect(refreshLibraryCount, [refreshLibraryCount])

  const wrapRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null)
  const [size, setSize] = useState({ w: 800, h: 600 })
  const fitDone = useRef(false)

  useEffect(() => {
    if (!wrapRef.current) return
    const el = wrapRef.current
    const ro = new ResizeObserver(() =>
      setSize({ w: el.clientWidth, h: el.clientHeight }),
    )
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Stable per-graph node/link objects. react-force-graph mutates these (adds
  // x/y, resolves source/target), and we set fx/fy on them to pin — so they MUST
  // survive filter changes. Rebuilt only when a new graph loads.
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

  // Reset controls whenever a new graph loads.
  useEffect(() => {
    if (!base) return
    setEnabled(new Set([...REL_TYPES, 'search']))
    setYearLo(base.minYear)
    setYearHi(base.maxYear)
    setPinned(new Set())
    setHoverId(null)
    setHighlightIds(new Set())
    // Usually empty (discoveries arrive later via onDiscover); on a restored
    // session the saved node set already carries its discovered papers.
    setDiscoveredNodes(base.nodes.filter((n) => n.discovered))
    setGraphVersion(0)
  }, [base])

  // Re-pin x by year when a new graph loads while Timeline is active (a fresh
  // graph has no user pins yet, so every node gets its year column).
  useEffect(() => {
    if (!base || layout !== 'timeline') return
    base.nodes.forEach((n) => {
      n.fx = nodeTimelineX(n)
      n.fy = undefined
    })
    const fg = fgRef.current
    const charge = fg?.d3Force?.('charge')
    if (charge) charge.strength(-30)
    fg?.d3Force?.('collide', forceCollide((n: VNode) => nodeRadius(n) + 6))
    fitDone.current = false
    fg?.d3ReheatSimulation?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base])

  // Filtered view. Nodes keep their identity (so positions/pins persist); links
  // are copied with source/target reset to ids so RFG re-resolves cleanly.
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

  // Neighbors of the hovered node (for focus-on-hover dimming).
  const hoverSet = useMemo(() => {
    if (!base || !hoverId) return null
    const s = new Set<string>([hoverId])
    base.links.forEach((l) => {
      if (l._s === hoverId) s.add(l._t)
      if (l._t === hoverId) s.add(l._s)
    })
    return s
  }, [base, hoverId])

  // What to focus the canvas on: hovering wins; otherwise the papers the AI
  // teacher is currently talking about (so beats/answers light up their nodes).
  const focusSet = useMemo(
    () => hoverSet ?? (highlightIds.size ? highlightIds : null),
    [hoverSet, highlightIds],
  )

  const selected = useMemo<VNode | null>(() => {
    if (!base || !selectedId) return null
    const n = base.nodes.find((x) => x.id === selectedId)
    if (!n) return null
    return details[selectedId] ? ({ ...n, ...details[selectedId] } as VNode) : n
  }, [base, selectedId, details])

  // Lazily fetch the selected paper's figures (ar5iv) the first time it's opened.
  useEffect(() => {
    const aid = selected?.arxiv_id
    if (!aid || figures[aid] || figLoading === aid) return
    setFigLoading(aid)
    fetchFigures(aid)
      .then((res) => setFigures((f) => ({ ...f, [aid]: res })))
      .catch(() => setFigures((f) => ({ ...f, [aid]: { available: false, figures: [] } })))
      .finally(() => setFigLoading((cur) => (cur === aid ? null : cur)))
  }, [selected, figures, figLoading])

  /** Load (or re-seed) the graph for a seed and remount the teacher fresh. */
  const loadGraph = useCallback(async (seed: string) => {
    setLoadingGraph(true)
    setError(null)
    setHits(null)
    setLocalHits(null)
    setDetails({})
    setFigures({})
    fitDone.current = false
    try {
      const g = await fetchGraph(seed)
      // A fresh seed starts a fresh conversation — remount the teacher empty.
      teacherInitRef.current = { chat: [], beats: [], histTrace: [] }
      restoreLayoutRef.current = null
      setGraph(g)
      setSelectedId(g.seed.id)
      setGraphKey((k) => k + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingGraph(false)
    }
  }, [])

  /** Run the seed search: local cache first (instant), live arXiv alongside. */
  const runSearch = useCallback(async (q: string) => {
    setSearching(true)
    setError(null)
    setHits(null)
    setLocalHits(null)
    setArxivFailed(false)
    // Cache-first: local hits resolve near-instantly and render while the live
    // arXiv search is still in flight (or failing, when we're rate-limited).
    const localP = searchLocal(q, 10)
    localP.then((l) => setLocalHits(l.length ? l : null))
    try {
      const res = await searchArxiv(q, 12)
      setHits(res.papers)
      if (res.papers.length === 0 && (await localP).length === 0)
        setError(`Nothing matched "${q}" — not on arXiv, not in your cache.`)
    } catch (e) {
      setArxivFailed(true)
      if ((await localP).length === 0)
        setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSearching(false)
    }
  }, [])

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

  // Single click selects a node; a quick second click on the SAME node re-seeds
  // the whole graph on it — letting you wander the literature node-to-node. We
  // re-seed by Semantic Scholar id (node.id) so journal papers work too.
  const lastClick = useRef<{ id: string; t: number }>({ id: '', t: 0 })
  const onNodeClick = useCallback(
    (node: VNode) => {
      const now = performance.now()
      if (lastClick.current.id === node.id && now - lastClick.current.t < 350) {
        lastClick.current = { id: '', t: 0 }
        if (!node.is_seed) loadGraph(node.id)
        return
      }
      lastClick.current = { id: node.id, t: now }
      setSelectedId(node.id)
      if (node.arxiv_id && !node.tldr && !node.abstract && !details[node.id]) {
        fetchPaperDetail(node.arxiv_id)
          .then((full) => setDetails((d) => ({ ...d, [node.id]: full })))
          .catch(() => {})
      }
    },
    [details, loadGraph],
  )

  // Map a year to its gridline x on the timeline. Papers with no year sit in an
  // "n.d." lane just left of the earliest year.
  const yearToX = useCallback(
    (year: number | null | undefined) => {
      if (!base) return 0
      const y = typeof year === 'number' ? year : base.minYear - 1
      return (y - base.minYear) * YEAR_SPACING
    },
    [base],
  )

  // A node's timeline x: its year plus a month fraction, so papers sit *between*
  // the yearly gridlines by publication month (unknown month → start of year).
  const nodeTimelineX = useCallback(
    (node: { year: number | null; month?: number | null }) => {
      if (!base) return 0
      const y = typeof node.year === 'number' ? node.year : base.minYear - 1
      const frac = typeof node.month === 'number' ? (node.month - 1) / 12 : 0
      return (y - base.minYear + frac) * YEAR_SPACING
    },
    [base],
  )

  // The Q&A agent pulled in papers not yet on the graph (expand_node). Merge
  // them into `base` IN PLACE — appending to base.nodes/links, never rebuilding
  // it — so react-force-graph's existing node objects (and the x/y/fx/fy the
  // sim + user pins have set on them) survive. graphVersion signals `view` (and
  // the repaint effect) to recompute since `base`'s own identity doesn't change.
  const onDiscover = useCallback(
    (newNodes: GraphNode[], newEdges: GraphEdge[]) => {
      if (!base || (newNodes.length === 0 && newEdges.length === 0)) return
      const knownIds = new Set(base.nodes.map((n) => n.id))
      const addedNodes: GraphNode[] = []
      for (const n of newNodes) {
        if (knownIds.has(n.id)) continue
        knownIds.add(n.id)
        // Start near whichever already-placed node it was discovered from, so
        // it doesn't fly in from the origin when the sim reheats. Topic-search
        // hits have no edge (ungrounded) — anchor them on the seed and scatter
        // wider so they settle into a loose cluster instead of stacking on it.
        const anchorEdge = newEdges.find((e) => e.source === n.id || e.target === n.id)
        const anchorId = anchorEdge
          ? anchorEdge.source === n.id
            ? anchorEdge.target
            : anchorEdge.source
          : null
        const anchor = anchorId
          ? base.nodes.find((x) => x.id === anchorId)
          : base.nodes.find((x) => x.is_seed)
        const spread = anchorEdge ? 40 : 120
        const vn: VNode = { ...n }
        if (anchor && typeof anchor.x === 'number' && typeof anchor.y === 'number') {
          vn.x = anchor.x + (Math.random() - 0.5) * spread
          vn.y = anchor.y + (Math.random() - 0.5) * spread
        }
        if (layout === 'timeline') vn.fx = nodeTimelineX(vn)
        base.nodes.push(vn)
        addedNodes.push(n)
        n.rels.forEach((r) => {
          if (r in base.counts) base.counts[r]++
        })
        if (typeof n.year === 'number') {
          if (n.year < base.minYear) {
            base.minYear = n.year
            setYearLo(n.year)
          }
          if (n.year > base.maxYear) {
            base.maxYear = n.year
            setYearHi(n.year)
          }
        }
      }

      const knownLinkKeys = new Set(base.links.map((l) => `${l._s}|${l._t}|${l.type}`))
      let addedLinks = 0
      for (const e of newEdges) {
        const key = `${e.source}|${e.target}|${e.type}`
        if (knownLinkKeys.has(key)) continue
        knownLinkKeys.add(key)
        base.links.push({ ...e, _s: e.source, _t: e.target })
        addedLinks++
      }

      if (addedNodes.length) setDiscoveredNodes((prev) => [...prev, ...addedNodes])
      if (addedNodes.length || addedLinks) {
        setGraphVersion((v) => v + 1)
        // Reheat so new nodes settle into place, but don't yank the camera —
        // the user may be mid-conversation, not looking at the graph.
        fgRef.current?.d3ReheatSimulation?.()
      }
    },
    [base, layout, nodeTimelineX],
  )

  const onNodeDragEnd = useCallback(
    (node: VNode) => {
      if (layout === 'timeline') {
        // Keep the paper at its date column; the drag only sets its height.
        node.fx = nodeTimelineX(node)
        node.fy = node.y
      } else {
        node.fx = node.x
        node.fy = node.y
      }
      setPinned((p) => new Set(p).add(node.id))
    },
    [layout, nodeTimelineX],
  )

  /** Pin the selected node in place, or release it if already pinned. */
  const togglePinSelected = useCallback(() => {
    if (!base || !selectedId) return
    const n = base.nodes.find((x) => x.id === selectedId)
    if (!n) return
    if (pinned.has(selectedId)) {
      // Unpin: in Timeline, keep the date-column x-pin; in Force, fully release.
      n.fx = layout === 'timeline' ? nodeTimelineX(n) : undefined
      n.fy = undefined
      setPinned((p) => {
        const s = new Set(p)
        s.delete(selectedId)
        return s
      })
      fgRef.current?.d3ReheatSimulation?.()
    } else {
      n.fx = n.x
      n.fy = n.y
      setPinned((p) => new Set(p).add(selectedId))
    }
  }, [base, selectedId, pinned, layout, nodeTimelineX])

  /** Unpin every node (keeps timeline date columns when in Timeline). */
  const releaseAll = useCallback(() => {
    base?.nodes.forEach((n) => {
      // Clearing user pins keeps the timeline structure (re-pin x by date).
      n.fx = base && layout === 'timeline' ? nodeTimelineX(n) : undefined
      n.fy = undefined
    })
    setPinned(new Set())
    fitDone.current = false
    fgRef.current?.d3ReheatSimulation?.()
  }, [base, layout, nodeTimelineX])

  const toggleType = useCallback((t: string) => {
    setEnabled((prev) => {
      const s = new Set(prev)
      if (s.has(t)) s.delete(t)
      else s.add(t)
      return s
    })
  }, [])

  // Switch layout. Timeline pins each node's x to its year (y stays force-driven
  // so citation threads form); Force releases those x-pins. User-pinned nodes
  // keep their fixed position either way.
  const applyLayout = useCallback(
    (mode: 'force' | 'timeline') => {
      if (!base) return
      // Switching layout releases all user pins — otherwise a node pinned in one
      // mode stays stuck at that position in the other.
      base.nodes.forEach((n) => {
        if (mode === 'timeline') {
          n.fx = nodeTimelineX(n)
          n.fy = undefined
        } else {
          n.fx = undefined
          n.fy = undefined
        }
      })
      setPinned(new Set())
      // Timeline: a collision force sized to each node's radius spreads papers
      // apart within a year column (no overlap, even spacing) rather than letting
      // them clump. Force mode keeps the default (no collide).
      const fg = fgRef.current
      const charge = fg?.d3Force?.('charge')
      if (charge) charge.strength(-30)
      fg?.d3Force?.(
        'collide',
        mode === 'timeline' ? forceCollide((n: VNode) => nodeRadius(n) + 6) : null,
      )
      fitDone.current = false
      fg?.d3ReheatSimulation?.()
    },
    [base, nodeTimelineX],
  )

  const setLayoutMode = useCallback(
    (mode: 'force' | 'timeline') => {
      setLayout(mode)
      applyLayout(mode)
    },
    [applyLayout],
  )

  // Apply a restored session's layout once its graph has been rebuilt into
  // `base`. Routed through the ref (rather than setLayoutMode in the restore
  // handler) so applyLayout runs against the NEW base — setting the right forces
  // and pinning timeline columns. No-ops for a normal graph load.
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
   */
  const handleSave = useCallback(
    async (name: string, id?: string): Promise<SavedSessionMeta> => {
      if (!base || !graph) throw new Error('No graph to save yet.')
      const ts = teacherStateRef.current
      return saveSession({
        id, // set → overwrite that saved session in place; omitted → create new
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
      setHits(null)
      setLocalHits(null)
      setDetails({})
      setFigures({})
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
      setSelectedId(d.seed.id)
      setGraphKey((k) => k + 1)
      setShowSessions(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingGraph(false)
    }
  }, [])

  const onEngineStop = useCallback(() => {
    // In Timeline, once the sim settles, freeze y as well (x is already pinned by
    // year) so the layout is stable and dragging one node can't re-relax the rest.
    if (layout === 'timeline' && base) {
      base.nodes.forEach((n) => {
        if (!pinned.has(n.id) && typeof n.y === 'number') n.fy = n.y
      })
    }
    if (!fitDone.current && fgRef.current) {
      fgRef.current.zoomToFit(400, 60)
      fitDone.current = true
    }
  }, [layout, base, pinned])

  // Draw the year axis behind the graph in Timeline mode: a faint gridline +
  // label per year, thinned out when zoomed too far to fit them all.
  const drawAxis = useCallback(
    (ctx: CanvasRenderingContext2D, globalScale: number) => {
      const fg = fgRef.current
      if (layout !== 'timeline' || !base || !fg || base.maxYear <= base.minYear)
        return
      const tl = fg.screen2GraphCoords(0, 0)
      const br = fg.screen2GraphCoords(size.w, size.h)
      // Only label as many years as comfortably fit (≥28px apart on screen).
      const px = YEAR_SPACING * globalScale
      const step = px < 28 ? Math.ceil(28 / px) : 1
      ctx.save()
      ctx.font = `${11 / globalScale}px -apple-system, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.lineWidth = 1 / globalScale
      for (let yr = base.minYear; yr <= base.maxYear; yr++) {
        if ((yr - base.minYear) % step !== 0) continue
        const x = yearToX(yr)
        ctx.strokeStyle = 'rgba(120,130,150,0.12)'
        ctx.beginPath()
        ctx.moveTo(x, tl.y)
        ctx.lineTo(x, br.y)
        ctx.stroke()
        ctx.fillStyle = 'rgba(150,160,180,0.65)'
        ctx.fillText(String(yr), x, tl.y + 4 / globalScale)
      }
      ctx.restore()
    },
    [layout, base, size, yearToX],
  )

  // Repaint when highlight/selection/pins/layout change (the sim may be at rest).
  useEffect(() => {
    fgRef.current?.refresh?.()
  }, [hoverId, selectedId, pinned, view, highlightIds, layout])

  // In Timeline, refit when the visible year range changes so narrowing the
  // slider zooms into those years — bigger nodes, less empty space.
  useEffect(() => {
    if (layout !== 'timeline') return
    const id = setTimeout(() => fgRef.current?.zoomToFit(400, 60), 150)
    return () => clearTimeout(id)
  }, [layout, yearLo, yearHi])

  const hasGraph = !!base && base.nodes.length > 0

  return (
    <div className="atlas">
      <header className="atlas-top">
        <div className="brand">
          arXiv <span>Atlas</span>
        </div>
        <form className="seed-search" onSubmit={onSubmit}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a paper by title, or paste an arXiv id / URL…"
            aria-label="Search for a paper to explore"
          />
          <button type="submit" disabled={searching || loadingGraph}>
            {searching ? 'Searching…' : 'Explore'}
          </button>
        </form>
        {graph && (
          <div className="seed-info" title={graph.seed.title}>
            {graph.seed.title}
          </div>
        )}
        <button
          className="sources-toggle top-right-start"
          onClick={() => setShowSources(true)}
          title="Your sources — books, PDFs, and pages the teacher can search"
        >
          📚 Sources
        </button>
        {libraryCount > 0 && (
          <button
            className="sources-toggle"
            onClick={() => setShowLibraryChat(true)}
            title="Ask questions answered straight from your uploaded library — no graph needed"
          >
            💬 Ask library
          </button>
        )}
        <button
          className="sources-toggle"
          onClick={() => setShowSessions(true)}
          title="Save the current graph + chat, or reopen a saved one"
        >
          🗂 Sessions
        </button>
        <a
          className="cc-credit"
          href="https://www.anthropic.com/claude"
          target="_blank"
          rel="noreferrer"
          title="The AI teacher runs on Claude"
        >
          <svg className="cc-credit-mark" viewBox="0 0 24 24" aria-hidden="true">
            <g
              stroke="#D97757"
              strokeWidth="1.7"
              strokeLinecap="round"
            >
              <line x1="15" y1="12" x2="22" y2="12" />
              <line x1="14.6" y1="13.5" x2="20.66" y2="17" />
              <line x1="13.5" y1="14.6" x2="17" y2="20.66" />
              <line x1="12" y1="15" x2="12" y2="22" />
              <line x1="10.5" y1="14.6" x2="7" y2="20.66" />
              <line x1="9.4" y1="13.5" x2="3.34" y2="17" />
              <line x1="9" y1="12" x2="2" y2="12" />
              <line x1="9.4" y1="10.5" x2="3.34" y2="7" />
              <line x1="10.5" y1="9.4" x2="7" y2="3.34" />
              <line x1="12" y1="9" x2="12" y2="2" />
              <line x1="13.5" y1="9.4" x2="17" y2="3.34" />
              <line x1="14.6" y1="10.5" x2="20.66" y2="7" />
            </g>
          </svg>
          Powered by Claude
        </a>
      </header>

      <Sources
        open={showSources}
        onClose={() => {
          setShowSources(false)
          refreshLibraryCount() // they may have added/removed sources
        }}
      />
      {showLibraryChat && <LibraryChat onClose={() => setShowLibraryChat(false)} />}

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
            onClose={() => {
              setHits(null)
              setLocalHits(null)
            }}
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
                    onClick={() => setShowLibraryChat(true)}
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
            <ForceGraph2D
              ref={fgRef}
              width={size.w}
              height={size.h}
              graphData={view}
              backgroundColor="#0f1115"
              nodeLabel={(n: GraphNode) =>
                `${n.title}${n.year ? ` (${n.year})` : ''}`
              }
              nodeRelSize={1}
              onNodeClick={onNodeClick}
              onNodeHover={(n: VNode | null) => setHoverId(n ? n.id : null)}
              onNodeDragEnd={onNodeDragEnd}
              onEngineStop={onEngineStop}
              onRenderFramePre={drawAxis}
              cooldownTicks={120}
              linkColor={(l: VLink) =>
                focusSet && !focusSet.has(l._s) && !focusSet.has(l._t)
                  ? DIM_EDGE
                  : EDGE_COLOR[l.type]
              }
              linkWidth={(l: { influential?: boolean }) =>
                l.influential ? 1.6 : 0.6
              }
              linkDirectionalArrowLength={(l: VLink) =>
                l.type === 'similar' ? 0 : 2.4
              }
              linkDirectionalArrowRelPos={1}
              nodeCanvasObject={(
                node: VNode & { x: number; y: number },
                ctx: CanvasRenderingContext2D,
                globalScale: number,
              ) => {
                const r = nodeRadius(node)
                const dim = focusSet ? !focusSet.has(node.id) : false
                const isPinned = pinned.has(node.id)
                const isSel = selectedId === node.id
                const isLit = highlightIds.has(node.id)

                // Glow behind papers the teacher is highlighting.
                if (isLit && !dim) {
                  ctx.beginPath()
                  ctx.arc(node.x, node.y, r + 5, 0, 2 * Math.PI)
                  ctx.fillStyle = 'rgba(255,209,102,0.22)'
                  ctx.fill()
                }
                ctx.beginPath()
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
                ctx.fillStyle = dim ? DIM_NODE : REL_COLOR[primaryRel(node)]
                ctx.fill()
                if (node.discovered && !dim) {
                  // Dashed ring marks a paper the AI teacher pulled in mid-chat.
                  ctx.lineWidth = 1.2 / globalScale
                  ctx.strokeStyle = 'rgba(242,244,248,0.6)'
                  ctx.setLineDash([2 / globalScale, 2 / globalScale])
                  ctx.stroke()
                  ctx.setLineDash([])
                }
                if (isLit && !dim) {
                  ctx.lineWidth = 2 / globalScale
                  ctx.strokeStyle = '#ffd166'
                  ctx.stroke()
                }
                if (isPinned && !dim) {
                  ctx.lineWidth = 1.5 / globalScale
                  ctx.strokeStyle = 'rgba(242,244,248,0.55)'
                  ctx.stroke()
                }
                if (isSel) {
                  ctx.lineWidth = 2 / globalScale
                  ctx.strokeStyle = '#f2f4f8'
                  ctx.stroke()
                }
                if (!dim && (node.is_seed || isSel || isLit || globalScale > 1.6)) {
                  const fontSize = Math.max(11 / globalScale, 2)
                  ctx.font = `${fontSize}px -apple-system, sans-serif`
                  ctx.textAlign = 'center'
                  ctx.textBaseline = 'top'
                  ctx.fillStyle = 'rgba(231,236,245,0.9)'
                  const t = node.title
                  ctx.fillText(
                    t.length > 42 ? t.slice(0, 40) + '…' : t,
                    node.x,
                    node.y + r + 1,
                  )
                }
              }}
              nodePointerAreaPaint={(
                node: VNode & { x: number; y: number },
                color: string,
                ctx: CanvasRenderingContext2D,
              ) => {
                ctx.fillStyle = color
                ctx.beginPath()
                ctx.arc(node.x, node.y, nodeRadius(node) + 2, 0, 2 * Math.PI)
                ctx.fill()
              }}
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
            isPinned={pinned.has(selected.id)}
            onTogglePin={togglePinSelected}
            onClose={() => setSelectedId(null)}
            onExplore={loadGraph}
          />
        )}

        {hasGraph && graph && (
          <Teacher
            key={graphKey}
            graph={graph}
            extraNodes={discoveredNodes}
            onHighlight={setHighlightIds}
            onDiscover={onDiscover}
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
