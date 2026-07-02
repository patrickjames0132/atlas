import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import ForceGraph2DImport from 'react-force-graph-2d'
import {
  fetchGraph,
  fetchPaperDetail,
  searchArxiv,
  type ArxivHit,
  type EdgeType,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
} from './api'
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
  const [searching, setSearching] = useState(false)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, Partial<GraphNode>>>({})

  // Declutter controls.
  const [enabled, setEnabled] = useState<Set<string>>(new Set(REL_TYPES))
  const [yearLo, setYearLo] = useState(0)
  const [yearHi, setYearHi] = useState(0)
  const [pinned, setPinned] = useState<Set<string>>(new Set())
  const [hoverId, setHoverId] = useState<string | null>(null)

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

  const selected = useMemo<VNode | null>(() => {
    if (!base || !selectedId) return null
    const n = base.nodes.find((x) => x.id === selectedId)
    if (!n) return null
    return details[selectedId] ? ({ ...n, ...details[selectedId] } as VNode) : n
  }, [base, selectedId, details])

  const loadGraph = useCallback(async (seed: string) => {
    setLoadingGraph(true)
    setError(null)
    setHits(null)
    setDetails({})
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
    try {
      const res = await searchArxiv(q, 12)
      setHits(res.papers)
      if (res.papers.length === 0) setError(`Nothing on arXiv matched "${q}".`)
    } catch (e) {
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

  const onNodeDragEnd = useCallback((node: VNode) => {
    node.fx = node.x
    node.fy = node.y
    setPinned((p) => new Set(p).add(node.id))
  }, [])

  const togglePinSelected = useCallback(() => {
    if (!base || !selectedId) return
    const n = base.nodes.find((x) => x.id === selectedId)
    if (!n) return
    if (pinned.has(selectedId)) {
      n.fx = undefined
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
  }, [base, selectedId, pinned])

  const releaseAll = useCallback(() => {
    base?.nodes.forEach((n) => {
      n.fx = undefined
      n.fy = undefined
    })
    setPinned(new Set())
    fgRef.current?.d3ReheatSimulation?.()
  }, [base])

  const toggleType = useCallback((t: string) => {
    setEnabled((prev) => {
      const s = new Set(prev)
      if (s.has(t)) s.delete(t)
      else s.add(t)
      return s
    })
  }, [])

  const onEngineStop = useCallback(() => {
    if (!fitDone.current && fgRef.current) {
      fgRef.current.zoomToFit(400, 60)
      fitDone.current = true
    }
  }, [])

  // Repaint when highlight/selection/pins change (the sim may be at rest).
  useEffect(() => {
    fgRef.current?.refresh?.()
  }, [hoverId, selectedId, pinned, view])

  const hasGraph = !!base && base.nodes.length > 0
  const showYears = !!base && base.maxYear > base.minYear

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
          {hits && (
            <div className="hit-list">
              <div className="hit-head">
                Pick a paper to explore
                <button className="link-btn" onClick={() => setHits(null)}>
                  ✕
                </button>
              </div>
              {hits.map((h) => (
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
                  <input
                    type="range"
                    min={base!.minYear}
                    max={base!.maxYear}
                    value={yearLo}
                    onChange={(e) =>
                      setYearLo(Math.min(Number(e.target.value), yearHi))
                    }
                  />
                  <input
                    type="range"
                    min={base!.minYear}
                    max={base!.maxYear}
                    value={yearHi}
                    onChange={(e) =>
                      setYearHi(Math.max(Number(e.target.value), yearLo))
                    }
                  />
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
                drag to pin · double-click a node to re-seed
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
              cooldownTicks={120}
              linkColor={(l: VLink) =>
                hoverId && l._s !== hoverId && l._t !== hoverId
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
                const dim = hoverSet ? !hoverSet.has(node.id) : false
                const isPinned = pinned.has(node.id)
                const isSel = selectedId === node.id

                ctx.beginPath()
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
                ctx.fillStyle = dim ? DIM_NODE : REL_COLOR[primaryRel(node)]
                ctx.fill()
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
                if (!dim && (node.is_seed || isSel || globalScale > 1.6)) {
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
                {selected.year ?? '—'} ·{' '}
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
            <div className="detail-actions">
              {selected.url && (
                <a href={selected.url} target="_blank" rel="noreferrer">
                  Open ↗
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
      </div>
    </div>
  )
}
