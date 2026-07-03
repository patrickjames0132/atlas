import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import ForceGraph2DImport from 'react-force-graph-2d'
// react-force-graph's own force lib (d3-force-3d) ships no types; we only need
// forceCollide to space timeline nodes out by their radius.
// @ts-expect-error - no type declarations
import { forceCollide } from 'd3-force-3d'
import {
  fetchFigures,
  fetchGraph,
  fetchPaperDetail,
  searchArxiv,
  searchLocal,
  type ArxivHit,
  type EdgeType,
  type FiguresResponse,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
  type LocalHit,
} from './api'
import Teacher from './Teacher'
import './atlas.css'

// The lib's generic prop typings fight our accessor signatures; render via an
// untyped alias so our canvas/link callbacks stay readable.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = ForceGraph2DImport as any

// A pasted arXiv id or abs/pdf URL — jump straight to a graph instead of a
// keyword search. Mirrors the backend's tolerance.
const ID_RE =
  /^(?:https?:\/\/arxiv\.org\/(?:abs|pdf)\/)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?\/\d{7}(?:v\d+)?)$/i

const REL_COLOR: Record<string, string> = {
  seed: '#ffd166', // gold — the paper you're exploring
  reference: '#6ea8fe', // blue — ancestors it cites
  citation: '#4ade80', // green — descendants that cite it
  similar: '#c084fc', // purple — embedding-similar papers
}
const EDGE_COLOR: Record<EdgeType, string> = {
  reference: 'rgba(110,168,254,0.30)',
  citation: 'rgba(74,222,128,0.30)',
  similar: 'rgba(192,132,252,0.24)',
}
const DIM_NODE = 'rgba(120,130,150,0.18)'
const DIM_EDGE = 'rgba(120,130,150,0.05)'

// Timeline layout: graph-x units per publication year. Wide enough that year
// columns read as distinct; zoomToFit handles the overall scale.
const YEAR_SPACING = 120

const REL_TYPES = ['reference', 'citation', 'similar'] as const
const REL_LABEL: Record<string, string> = {
  reference: 'References',
  citation: 'Citations',
  similar: 'Similar',
}

type VNode = GraphNode & { x?: number; y?: number; fx?: number; fy?: number }
type VLink = GraphEdge & { _s: string; _t: string }
type Base = {
  nodes: VNode[]
  links: VLink[]
  minYear: number
  maxYear: number
  counts: Record<string, number>
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

// Human-readable publication date: "Jun 12, 2017" from a "YYYY-MM-DD" string,
// gracefully degrading to "Jun 2017" / the year / "—" as data thins out. Parsed
// by hand (not new Date) to avoid timezone off-by-one on date-only strings.
function formatPubDate(pubDate?: string | null, year?: number | null): string {
  if (pubDate) {
    const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(pubDate)
    if (m) {
      const mon = MONTHS[Number(m[2]) - 1]
      if (mon && m[3]) return `${mon} ${Number(m[3])}, ${m[1]}`
      if (mon) return `${mon} ${m[1]}`
      return m[1]
    }
  }
  return year != null ? String(year) : '—'
}

function primaryRel(node: GraphNode): string {
  if (node.is_seed) return 'seed'
  for (const rel of REL_TYPES) if (node.rels.includes(rel)) return rel
  return 'similar'
}

function nodeRadius(node: GraphNode): number {
  if (node.is_seed) return 10
  const c = node.citation_count ?? 0
  return Math.min(3 + Math.sqrt(c) / 6, 18)
}

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
  const [enabled, setEnabled] = useState<Set<string>>(new Set(REL_TYPES))
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  const [pinned, setPinned] = useState<Set<string>>(new Set())
  const [hoverId, setHoverId] = useState<string | null>(null)
  // Nodes the AI teacher is currently talking about (active beat / cited papers).
  const [highlightIds, setHighlightIds] = useState<Set<string>>(new Set())
  // 'force' = organic force-directed; 'timeline' = x pinned to publication year.
  const [layout, setLayout] = useState<'force' | 'timeline'>('force')

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
    setEnabled(new Set(REL_TYPES))
    setYearLo(base.minYear)
    setYearHi(base.maxYear)
    setPinned(new Set())
    setHoverId(null)
    setHighlightIds(new Set())
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
  }, [base, enabled, yearLo, yearHi])

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
      setGraph(g)
      setSelectedId(g.seed.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingGraph(false)
    }
  }, [])

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
  const showYears = !!base && base.maxYear > base.minYear
  // Position (0–100%) of a year along the range track, for the fill + knobs.
  const yearSpan = base ? base.maxYear - base.minYear : 0
  const yearPct = (y: number) =>
    yearSpan && base ? ((y - base.minYear) / yearSpan) * 100 : 0

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
      </header>

      <div className="atlas-body">
        <main className="canvas-wrap" ref={wrapRef}>
          {(hits || localHits) && (
            <div className="hit-list">
              <div className="hit-head">
                Pick a paper to explore
                <button
                  className="link-btn"
                  onClick={() => {
                    setHits(null)
                    setLocalHits(null)
                  }}
                >
                  ✕
                </button>
              </div>
              {localHits && (
                <>
                  <div className="hit-sub">From your cache</div>
                  {localHits.map((h) => (
                    <button
                      key={h.id}
                      className="hit"
                      onClick={() => loadGraph(h.arxiv_id ?? h.id)}
                    >
                      <div className="hit-title">
                        {h.title}
                        {h.has_graph && (
                          <span className="hit-badge" title="Graph snapshot cached — explores without hitting the API">
                            instant
                          </span>
                        )}
                      </div>
                      <div className="hit-meta">
                        {h.authors ? `${h.authors} · ` : ''}
                        {h.year ?? '—'} ·{' '}
                        {(h.citation_count ?? 0).toLocaleString()} citations
                      </div>
                    </button>
                  ))}
                </>
              )}
              {localHits && (searching || hits || arxivFailed) && (
                <div className="hit-sub">From arXiv</div>
              )}
              {searching && <div className="hit-note">Searching arXiv…</div>}
              {arxivFailed && (
                <div className="hit-note">
                  arXiv search unavailable — showing cached papers only.
                </div>
              )}
              {hits && hits.length === 0 && !searching && (
                <div className="hit-note">No results from arXiv.</div>
              )}
              {hits
                ?.filter(
                  (h) => !localHits?.some((l) => l.arxiv_id === h.arxiv_id),
                )
                .map((h) => (
                  <button
                    key={h.arxiv_id}
                    className="hit"
                    onClick={() => loadGraph(h.arxiv_id)}
                  >
                    <div className="hit-title">{h.title}</div>
                    <div className="hit-meta">
                      {h.authors} · {h.arxiv_id}
                    </div>
                  </button>
                ))}
            </div>
          )}

          {loadingGraph && <div className="overlay">Building graph…</div>}
          {error && !hits && <div className="overlay error">{error}</div>}
          {!hasGraph && !loadingGraph && !hits && !error && (
            <div className="overlay hint">
              Search for a paper to map its citations, references, and similar
              work.
            </div>
          )}

          {hasGraph && (
            <div className="controls">
              <div className="layout-toggle">
                <button
                  className={layout === 'force' ? 'on' : ''}
                  onClick={() => setLayoutMode('force')}
                >
                  Force
                </button>
                <button
                  className={layout === 'timeline' ? 'on' : ''}
                  onClick={() => setLayoutMode('timeline')}
                >
                  Timeline
                </button>
              </div>
              <div className="ctrl-chips">
                {REL_TYPES.map((t) => (
                  <button
                    key={t}
                    className={`chip ${enabled.has(t) ? 'on' : ''}`}
                    onClick={() => toggleType(t)}
                    style={{ '--c': REL_COLOR[t] } as CSSProperties}
                  >
                    <i />
                    {REL_LABEL[t]}
                    <em>{base!.counts[t]}</em>
                  </button>
                ))}
              </div>

              {showYears && (
                <div className="years">
                  <div className="years-label">
                    Years <b>{yearLo}</b> – <b>{yearHi}</b>
                  </div>
                  <div className="range-dual">
                    <div className="range-track" />
                    <div
                      className="range-fill"
                      style={{
                        left: `${yearPct(yearLo)}%`,
                        width: `${yearPct(yearHi) - yearPct(yearLo)}%`,
                      }}
                    />
                    <input
                      type="range"
                      min={base!.minYear}
                      max={base!.maxYear}
                      value={yearLo}
                      aria-label="Earliest year"
                      onChange={(e) =>
                        setYearLo(Math.min(Number(e.target.value), yearHi))
                      }
                    />
                    <input
                      type="range"
                      min={base!.minYear}
                      max={base!.maxYear}
                      value={yearHi}
                      aria-label="Latest year"
                      onChange={(e) =>
                        setYearHi(Math.max(Number(e.target.value), yearLo))
                      }
                    />
                  </div>
                </div>
              )}

              <div className="ctrl-foot">
                <span className="count-readout">
                  {view.nodes.length} / {base!.nodes.length} papers
                </span>
                <div className="ctrl-btns">
                  <button
                    className="mini-btn"
                    onClick={releaseAll}
                    disabled={pinned.size === 0}
                    title="Unpin every node"
                  >
                    Release {pinned.size || ''}
                  </button>
                  <button
                    className="mini-btn"
                    onClick={() => fgRef.current?.zoomToFit(400, 60)}
                    title="Re-center the graph"
                  >
                    Fit
                  </button>
                </div>
              </div>
              <div className="ctrl-hint">
                {layout === 'timeline'
                  ? 'papers placed left→right by year · double-click to re-seed'
                  : 'drag to pin · double-click a node to re-seed'}
              </div>
            </div>
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
            <div className="legend">
              <span>
                <i style={{ background: REL_COLOR.seed }} />
                Seed
              </span>
              <span>
                <i style={{ background: REL_COLOR.reference }} />
                References
              </span>
              <span>
                <i style={{ background: REL_COLOR.citation }} />
                Citations
              </span>
              <span>
                <i style={{ background: REL_COLOR.similar }} />
                Similar
              </span>
            </div>
          )}
        </main>

        {selected && (
          <aside className="detail">
            <button className="link-btn close" onClick={() => setSelectedId(null)}>
              ✕
            </button>
            <div className="detail-badges">
              {selected.rels.map((r) => (
                <span key={r} className="badge" style={{ color: REL_COLOR[r] }}>
                  {r}
                </span>
              ))}
            </div>
            <h2>{selected.title}</h2>
            <div className="detail-meta">
              {selected.authors && <div>{selected.authors}</div>}
              <div>
                {formatPubDate(selected.pub_date, selected.year)} ·{' '}
                {(selected.citation_count ?? 0).toLocaleString()} citations
              </div>
            </div>
            {(selected.tldr || selected.abstract) && (
              <p className="detail-summary">
                {selected.tldr ? (
                  <>
                    <strong>TL;DR </strong>
                    {selected.tldr}
                  </>
                ) : (
                  selected.abstract
                )}
              </p>
            )}
            {selected.arxiv_id &&
              (() => {
                const figs = figures[selected.arxiv_id]
                if (!figs) {
                  return figLoading === selected.arxiv_id ? (
                    <div className="detail-figs-hint">Loading figures…</div>
                  ) : null
                }
                if (!figs.available || figs.figures.length === 0) return null
                return (
                  <div className="detail-figs">
                    <div className="detail-figs-head">Figures</div>
                    {figs.figures.map((f, i) => (
                      <figure key={i} className="detail-fig">
                        <img src={f.image} alt={f.caption || `Figure ${i + 1}`} loading="lazy" />
                        {f.caption && <figcaption>{f.caption}</figcaption>}
                      </figure>
                    ))}
                  </div>
                )
              })()}
            <div className="detail-actions">
              {selected.url && (
                <a href={selected.url} target="_blank" rel="noreferrer">
                  Abstract ↗
                </a>
              )}
              {selected.url && selected.arxiv_id && (
                <a
                  href={selected.url.replace('/abs/', '/pdf/')}
                  target="_blank"
                  rel="noreferrer"
                >
                  PDF ↗
                </a>
              )}
              <button className="ghost-btn" onClick={togglePinSelected}>
                {pinned.has(selected.id) ? 'Unpin' : 'Pin'}
              </button>
              {!selected.is_seed && (
                <button onClick={() => loadGraph(selected.id)}>
                  Explore from here →
                </button>
              )}
            </div>
          </aside>
        )}

        {hasGraph && graph && (
          <Teacher graph={graph} onHighlight={setHighlightIds} />
        )}
      </div>
    </div>
  )
}
