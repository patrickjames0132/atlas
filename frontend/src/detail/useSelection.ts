/**
 * Selection state for the explorer: which node is open in the detail panel,
 * its lazily-hydrated details (abstract/TL;DR), its lazily-fetched figures,
 * and the click handler that both selects and (on a quick double-click)
 * re-seeds the graph.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchFigures, fetchPaperDetail } from '../api'
import type { FiguresResponse, GraphNode, GraphResponse } from '../api'
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
  /** Canvas click handler: select on click, re-seed on quick double-click. */
  onNodeClick: (node: VNode) => void
}

/**
 * Own the selected-paper state: selection, detail hydration, and figures.
 *
 * Per-paper caches (details, figures) reset — and the seed becomes the
 * selection — whenever a new graph loads.
 */
export function useSelection({ base, graph, loadGraph }: UseSelectionArgs): SelectionApi {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, Partial<GraphNode>>>({})
  // Figures (ar5iv) per arXiv id, lazily fetched when a node is opened.
  const [figures, setFigures] = useState<Record<string, FiguresResponse>>({})
  const [figLoading, setFigLoading] = useState<string | null>(null)

  // A new graph invalidates the per-paper caches and selects its seed.
  useEffect(() => {
    setDetails({})
    setFigures({})
    setSelectedId(graph ? graph.seed.id : null)
  }, [graph])

  /** The selected node, overlaid with any hydrated detail fields. */
  const selected = useMemo<VNode | null>(() => {
    if (!base || !selectedId) return null
    const n = base.nodes.find((x) => x.id === selectedId)
    if (!n) return null
    return details[selectedId] ? ({ ...n, ...details[selectedId] } as VNode) : n
  }, [base, selectedId, details])

  // Lazily fetch the selected paper's figures (ar5iv) the first time it's
  // opened. Failures cache as unavailable so a flaky ar5iv isn't re-hit.
  useEffect(() => {
    const aid = selected?.arxiv_id
    if (!aid || figures[aid] || figLoading === aid) return
    setFigLoading(aid)
    fetchFigures(aid)
      .then((res) => setFigures((f) => ({ ...f, [aid]: res })))
      .catch(() => setFigures((f) => ({ ...f, [aid]: { available: false, figures: [] } })))
      .finally(() => setFigLoading((cur) => (cur === aid ? null : cur)))
  }, [selected, figures, figLoading])

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
      // Neighbor nodes arrive summary-light — hydrate the panel on first open.
      if (node.arxiv_id && !node.tldr && !node.abstract && !details[node.id]) {
        fetchPaperDetail(node.arxiv_id)
          .then((full) => setDetails((d) => ({ ...d, [node.id]: full })))
          .catch(() => {})
      }
    },
    [details, loadGraph],
  )

  return { selectedId, setSelectedId, selected, figures, figLoading, onNodeClick }
}
