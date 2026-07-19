/**
 * Selection state for the explorer: which node is open in the detail panel,
 * its lazily-hydrated details (abstract/TL;DR), its lazily-fetched figures,
 * code links, and arXiv category tags, and the click handler that both
 * selects and (on a quick double-click) re-seeds the graph.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchCategories, fetchCodeLinks, fetchFigures, fetchPaperDetail } from '../api'
import type {
  CategoriesResponse,
  CodeLinksResponse,
  FiguresResponse,
  GraphNode,
  GraphResponse,
  Provider,
} from '../api'
import type { Base, VNode } from '../graph/model'

/** Arguments for {@link useSelection}. */
export interface UseSelectionArgs {
  /** The stable per-graph dataset (selection resolves against its nodes). */
  base: Base | null
  /** The loaded graph — selection resets to its seed whenever it changes. */
  graph: GraphResponse | null
  /** The active provider — detail hydration comes from the backend the graph
   *  was built with. */
  provider: Provider
  /** Re-seed the whole graph on a paper (fired by a quick double-click). */
  loadGraph: (seed: string) => void
}

/** What {@link useSelection} returns for GraphExplorer to wire up. */
export interface SelectionApi {
  /** The selected node id (null = detail panel closed). */
  selectedId: string | null
  /** Select a node by id, or null to close the panel. */
  setSelectedId: (id: string | null) => void
  /** The selected node, merged with any hydrated detail fields. */
  selected: VNode | null
  /** The node id whose summary hydration (fetchPaperDetail) is in flight
   *  (else null) — the detail panel shows its summary skeleton for it. */
  detailLoading: string | null
  /** Figures per figure key — a node's arXiv id, else its node id (papers
   *  off arXiv get theirs mined from their open-access PDF) — as they
   *  finish loading (failures cache as unavailable, so a missing entry
   *  always means "in flight"). */
  figures: Record<string, FiguresResponse>
  /** Code & artifact links (HF Papers) per arXiv id, as they finish loading. */
  codeLinks: Record<string, CodeLinksResponse>
  /** The paper's own arXiv category tags per arXiv id, as they finish loading. */
  categories: Record<string, CategoriesResponse>
  /** Canvas click handler: select on click, re-seed on quick double-click. */
  onNodeClick: (node: VNode) => void
  /** Overlay extra hydrated fields onto one node — e.g. a TL;DR the panel
   *  just generated — so `selected` (and the graph's session save, via the
   *  same detail overlay) reflects them immediately. */
  mergeDetail: (id: string, fields: Partial<GraphNode>) => void
}

/**
 * Own the selected-paper state: selection, detail hydration, figures, code
 * links, and category tags.
 *
 * Per-paper caches (details, figures, code links, categories) reset — and
 * the seed becomes the selection — whenever a new graph loads.
 *
 * @returns The selection state + handlers (see {@link SelectionApi}).
 */
export function useSelection({ base, graph, provider, loadGraph }: UseSelectionArgs): SelectionApi {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, Partial<GraphNode>>>({})
  // The node id whose summary hydration is in flight — drives the panel's
  // summary skeleton so the abstract doesn't just pop in.
  const [detailLoading, setDetailLoading] = useState<string | null>(null)
  // Figures per figure key (arXiv id, else node id — those come mined from
  // the paper's OA PDF), lazily fetched when a node is opened.
  const [figures, setFigures] = useState<Record<string, FiguresResponse>>({})
  const [figLoading, setFigLoading] = useState<string | null>(null)
  // Code & artifact links (HF Papers) per arXiv id, same lazy pattern.
  const [codeLinks, setCodeLinks] = useState<Record<string, CodeLinksResponse>>({})
  const codeRequested = useRef<Set<string>>(new Set())
  // The paper's own arXiv category tags per arXiv id, same lazy pattern.
  const [categories, setCategories] = useState<Record<string, CategoriesResponse>>({})
  const categoriesRequested = useRef<Set<string>>(new Set())

  // A new graph invalidates the per-paper caches and selects its seed.
  useEffect(() => {
    setDetails({})
    setFigures({})
    setCodeLinks({})
    codeRequested.current = new Set()
    setCategories({})
    categoriesRequested.current = new Set()
    setSelectedId(graph ? graph.seed.id : null)
  }, [graph])

  /** The selected node, overlaid with any hydrated detail fields. */
  const selected = useMemo<VNode | null>(() => {
    if (!base || !selectedId) return null
    const node = base.nodes.find((candidate) => candidate.id === selectedId)
    if (!node) return null
    const detail = details[selectedId]
    if (!detail) return node
    // Preserve a known arxiv_id through hydration. Under OpenAlex, hydrating the
    // exact record by its DOI can return arxiv_id: null (a published-only OA
    // record carries no arXiv location, even when the paper is on arXiv) — don't
    // let that null out the id the graph build already extracted, or the arXiv
    // category tags (fetched by arxiv_id) would vanish for a paper that has one.
    return { ...node, ...detail, arxiv_id: detail.arxiv_id ?? node.arxiv_id } as VNode
  }, [base, selectedId, details])

  // Lazily fetch the selected paper's figures the first time it's opened —
  // by arXiv id (ar5iv) when it has one, else by node id (the backend mines
  // the paper's OA PDF, so this works for journal papers too). Failures
  // cache as unavailable so a flaky upstream isn't re-hit.
  useEffect(() => {
    const figKey = selected ? (selected.arxiv_id ?? selected.id) : null
    if (!figKey || figures[figKey] || figLoading === figKey) return
    setFigLoading(figKey)
    fetchFigures(figKey, provider)
      .then((res) => setFigures((prev) => ({ ...prev, [figKey]: res })))
      .catch(() => setFigures((prev) => ({ ...prev, [figKey]: { available: false, figures: [] } })))
      .finally(() => setFigLoading((cur) => (cur === figKey ? null : cur)))
  }, [selected, figures, figLoading, provider])

  // Same for the paper's code & artifact links (HF Papers). fetchCodeLinks
  // never throws — failures land as { available: false }.
  useEffect(() => {
    const aid = selected?.arxiv_id
    if (!aid || codeRequested.current.has(aid)) return
    codeRequested.current.add(aid)
    fetchCodeLinks(aid).then((res) => setCodeLinks((prev) => ({ ...prev, [aid]: res })))
  }, [selected])

  // Same for the paper's own arXiv category tags. fetchCategories never
  // throws — failures land as { available: false }.
  useEffect(() => {
    const aid = selected?.arxiv_id
    if (!aid || categoriesRequested.current.has(aid)) return
    categoriesRequested.current.add(aid)
    fetchCategories(aid).then((res) => setCategories((prev) => ({ ...prev, [aid]: res })))
  }, [selected])

  // Single click selects a node; a quick second click on the SAME node re-seeds
  // the whole graph on it — letting you wander the literature node-to-node. We
  // re-seed by Semantic Scholar id (node.id) so journal papers work too.
  const lastClick = useRef<{ id: string; time: number }>({ id: '', time: 0 })
  const onNodeClick = useCallback(
    (node: VNode) => {
      const now = performance.now()
      if (lastClick.current.id === node.id && now - lastClick.current.time < 350) {
        lastClick.current = { id: '', time: 0 }
        if (!node.is_seed) loadGraph(node.id)
        return
      }
      lastClick.current = { id: node.id, time: now }
      setSelectedId(node.id)
      // Neighbor nodes arrive summary-light — hydrate the panel on first open,
      // from the same backend the graph was built with. Under S2, hydrate by
      // arXiv id when there is one (else the paperId) — S2 resolves both. Under
      // OpenAlex, hydrate by the node id (the reliable DOI:/W… form): a bare
      // arXiv id can miss (a published paper's canonical OA record isn't aliased
      // to the arXiv-minted DOI), but the node's own id always resolves.
      const detailRef = provider === 'openalex' ? node.id : (node.arxiv_id ?? node.id)
      if (!node.tldr && !node.abstract && !details[node.id]) {
        setDetailLoading(node.id)
        fetchPaperDetail(detailRef, provider)
          .then((full) => setDetails((prev) => ({ ...prev, [node.id]: full })))
          .catch(() => {})
          .finally(() => setDetailLoading((cur) => (cur === node.id ? null : cur)))
      }
    },
    [details, provider, loadGraph],
  )

  /** Merge extra fields into a node's hydrated-detail overlay. */
  const mergeDetail = useCallback((id: string, fields: Partial<GraphNode>) => {
    setDetails((prev) => ({ ...prev, [id]: { ...prev[id], ...fields } }))
  }, [])

  return {
    selectedId,
    setSelectedId,
    selected,
    detailLoading,
    figures,
    codeLinks,
    categories,
    onNodeClick,
    mergeDetail,
  }
}
