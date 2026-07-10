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
} from '../api'
import type { Base, VNode } from '../graph/model'

/** Arguments for {@link useSelection}. */
export interface UseSelectionArgs {
  /** The stable per-graph dataset (selection resolves against its nodes). */
  base: Base | null
  /** The loaded graph — selection resets to its seed whenever it changes. */
  graph: GraphResponse | null
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
  /** Figures per arXiv id, as they finish loading. */
  figures: Record<string, FiguresResponse>
  /** The arXiv id whose figures are currently being fetched (else null). */
  figLoading: string | null
  /** Code & artifact links (HF Papers) per arXiv id, as they finish loading. */
  codeLinks: Record<string, CodeLinksResponse>
  /** The paper's own arXiv category tags per arXiv id, as they finish loading. */
  categories: Record<string, CategoriesResponse>
  /** Canvas click handler: select on click, re-seed on quick double-click. */
  onNodeClick: (node: VNode) => void
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
export function useSelection({ base, graph, loadGraph }: UseSelectionArgs): SelectionApi {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, Partial<GraphNode>>>({})
  // Figures (ar5iv) per arXiv id, lazily fetched when a node is opened.
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
    return details[selectedId] ? ({ ...node, ...details[selectedId] } as VNode) : node
  }, [base, selectedId, details])

  // Lazily fetch the selected paper's figures (ar5iv) the first time it's
  // opened. Failures cache as unavailable so a flaky ar5iv isn't re-hit.
  useEffect(() => {
    const aid = selected?.arxiv_id
    if (!aid || figures[aid] || figLoading === aid) return
    setFigLoading(aid)
    fetchFigures(aid)
      .then((res) => setFigures((prev) => ({ ...prev, [aid]: res })))
      .catch(() => setFigures((prev) => ({ ...prev, [aid]: { available: false, figures: [] } })))
      .finally(() => setFigLoading((cur) => (cur === aid ? null : cur)))
  }, [selected, figures, figLoading])

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
      // Neighbor nodes arrive summary-light — hydrate the panel on first open.
      // By arXiv id when there is one, else the raw S2 paperId: journal papers
      // hydrate too (the old code's arxiv_id gate left them abstract-less,
      // the client half of the hydration bug fixed server-side in Phase 5).
      if (!node.tldr && !node.abstract && !details[node.id]) {
        fetchPaperDetail(node.arxiv_id ?? node.id)
          .then((full) => setDetails((prev) => ({ ...prev, [node.id]: full })))
          .catch(() => {})
      }
    },
    [details, loadGraph],
  )

  return {
    selectedId,
    setSelectedId,
    selected,
    figures,
    figLoading,
    codeLinks,
    categories,
    onNodeClick,
  }
}
