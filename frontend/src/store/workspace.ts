/**
 * The workspace slice: the loaded graph, the agent's discoveries, the layout
 * choice, and the load/restore/save thunks — the cross-cutting core that the
 * canvas renders, the teacher grounds in, and Save serializes.
 *
 * Serializability rule: this slice holds the RAW GraphResponse and discovery
 * arrays (plain JSON). The mutable sim dataset (`Base`) is derived FROM this
 * state canvas-side and never enters the store — react-force-graph mutates
 * its objects, the exact opposite of what Redux state may be.
 */

import { createAsyncThunk, createSelector, createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import {
  fetchGraphStream,
  getSession,
  saveSession,
  type BuildProgress,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
  type SavedSessionMeta,
} from '../api'
import { cleanNode, countRels } from '../graph/model'
import type { VNode } from '../graph/model'
import type { TranscriptState } from './transcript'

export interface WorkspaceState {
  graph: GraphResponse | null
  /**
   * The exact reference this graph was loaded with (arXiv id, pasted URL, or
   * S2 paperId) — kept so "Refresh" can bust the *same* cache key the server
   * stored the snapshot under (a double-click re-seed keys by paperId, a
   * search by arXiv id). Null with no graph.
   */
  seedRef: string | null
  /** Papers the agent pulled in mid-conversation (deduped against the graph). */
  discoveredNodes: GraphNode[]
  discoveredEdges: GraphEdge[]
  /**
   * Ids of the nodes currently VISIBLE on the canvas — published by
   * GraphExplorer's view filter (relation chips, year range, citation-count
   * threshold). Agents ground on what's on screen, not the whole shipped pool
   * (which holds far more than the filters show), so this is the intersection
   * `selectGroundingNodes` applies. Empty until the first render.
   */
  visibleNodeIds: string[]
  /**
   * Ids the user has HAND-PICKED on the canvas (alt-drag marquee / shift-click)
   * to scope the teacher to a cluster of interest. When non-empty it narrows
   * grounding to the selected ∩ visible nodes (see `selectGroundingNodes`);
   * empty means "no manual pick" and grounding falls back to the whole visible
   * set. A transient exploration choice, like `visibleNodeIds` — reset on every
   * load/restore and never persisted in a save.
   */
  selectedNodeIds: string[]
  layout: 'force' | 'timeline'
  /** Bumps on every load/restore — the teacher panel remounts per epoch. */
  epoch: number
  loading: boolean
  /**
   * The current graph-build stage while `loading`, streamed from the SSE build
   * endpoint — drives the determinate "Building graph…" bar. Null before the
   * first frame (and on a cache hit, which streams none), so the overlay falls
   * back to a bare spinner until/unless a stage arrives.
   */
  buildProgress: BuildProgress | null
  /** The shared error surface (graph loads + seed search). */
  error: string | null
}

const initialState: WorkspaceState = {
  graph: null,
  seedRef: null,
  discoveredNodes: [],
  discoveredEdges: [],
  visibleNodeIds: [],
  selectedNodeIds: [],
  layout: 'timeline',
  epoch: 0,
  loading: false,
  buildProgress: null,
  error: null,
}

/**
 * Load (or re-seed) the graph for an arXiv id, pasted URL, or S2 paperId.
 *
 * @param seed    The paper reference to build the neighborhood around.
 * @param refresh Bypass the server's day-cached snapshot for this seed and
 *                rebuild from Semantic Scholar (the "Refresh" action) —
 *                useful when S2's data for a paper has visibly changed.
 */
export const loadGraph = createAsyncThunk(
  'workspace/loadGraph',
  ({ seed, refresh = false }: { seed: string; refresh?: boolean }, { dispatch }) =>
    fetchGraphStream(seed, refresh, (progress) => dispatch(buildProgressSet(progress))),
)

/**
 * Reopen a saved session: rebuild its graph directly (no S2 fetch, so no
 * rate-limit cost and the exact discovered papers are preserved). The
 * transcript slice restores itself from this thunk's payload.
 */
export const restoreSession = createAsyncThunk('workspace/restoreSession', async (id: string) => {
  const saved = await getSession(id)
  const data = saved.data
  const graph: GraphResponse = {
    seed: {
      id: data.seed.id,
      arxiv_id: data.seed.arxiv_id ?? null,
      title: data.seed.title,
    },
    nodes: data.nodes,
    edges: data.edges,
    counts: countRels(data.nodes),
  }
  return {
    graph,
    layout: data.layout ?? ('timeline' as const),
    // (Old saves may carry a hist_trace field from the retired lecture
    // backfill — ignored; lectures no longer expand the graph.)
    transcript: {
      chat: data.chat ?? [],
      // New saves carry the per-mode lecture cache directly. A pre-caching
      // save has only a flat `beats` array with no mode recorded — fold it in
      // under `history` (the primary "how we got here" mode) so the lecture
      // isn't lost, and show it.
      lectures: data.lectures ?? (data.beats?.length ? { history: data.beats } : {}),
      activeMode: data.activeMode ?? (data.beats?.length ? ('history' as const) : null),
    },
  }
})

/**
 * Save the current workspace. The store IS the source of truth: the graph's
 * nodes/edges plus the discovery arrays are exactly what the old code
 * reconstructed from the sim-mutated `base` objects — no canvas involvement.
 */
export const saveWorkspace = createAsyncThunk<
  SavedSessionMeta,
  { name: string; id?: string },
  { state: { workspace: WorkspaceState; transcript: TranscriptState } }
>('workspace/save', ({ name, id }, { getState }) => {
  const { workspace, transcript } = getState()
  const graph = workspace.graph
  if (!graph) throw new Error('No graph to save yet.')
  return saveSession({
    id,
    name,
    seed: graph.seed,
    layout: workspace.layout,
    // cleanNode strips the researcher's per-conversation idx from discovered nodes.
    nodes: [...graph.nodes, ...workspace.discoveredNodes].map((node) => cleanNode(node as VNode)),
    edges: [...graph.edges, ...workspace.discoveredEdges],
    chat: transcript.chat,
    lectures: transcript.lectures,
    activeMode: transcript.activeMode,
  })
})

const workspaceSlice = createSlice({
  name: 'workspace',
  initialState,
  reducers: {
    /**
     * Merge a discovery event, deduped against the graph and prior finds.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the discovered nodes and edges.
     */
    discoveryMerged(state, action: PayloadAction<{ nodes: GraphNode[]; edges: GraphEdge[] }>) {
      if (!state.graph) return
      const knownIds = new Set([
        ...state.graph.nodes.map((node) => node.id),
        ...state.discoveredNodes.map((node) => node.id),
      ])
      for (const node of action.payload.nodes) {
        if (knownIds.has(node.id)) continue
        knownIds.add(node.id)
        state.discoveredNodes.push(node)
      }
      const edgeKey = (edge: GraphEdge) => `${edge.source}|${edge.target}|${edge.type}`
      const knownEdges = new Set([...state.graph.edges, ...state.discoveredEdges].map(edgeKey))
      for (const edge of action.payload.edges) {
        if (knownEdges.has(edgeKey(edge))) continue
        knownEdges.add(edgeKey(edge))
        state.discoveredEdges.push(edge)
      }
    },
    /**
     * Switch the graph layout (Force ↔ Timeline).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the layout mode.
     */
    layoutSet(state, action: PayloadAction<'force' | 'timeline'>) {
      state.layout = action.payload
    },
    /**
     * A build-stage frame from the SSE build stream (see `loadGraph`).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the `{done, total, label}` stage.
     */
    buildProgressSet(state, action: PayloadAction<BuildProgress>) {
      state.buildProgress = action.payload
    },
    /**
     * GraphExplorer publishes the on-screen node ids here whenever its view
     * filter changes, so agent grounding tracks what's actually visible.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the visible node ids.
     */
    visibleNodesSet(state, action: PayloadAction<string[]>) {
      state.visibleNodeIds = action.payload
    },
    /**
     * Replace the hand-picked selection wholesale (a fresh marquee drag). The
     * ids come pre-filtered to what's visible, so grounding intersects cleanly.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the newly selected node ids.
     */
    nodeSelectionSet(state, action: PayloadAction<string[]>) {
      state.selectedNodeIds = [...new Set(action.payload)]
    },
    /**
     * Union more ids into the selection (a shift-held marquee drag adds a
     * cluster to what's already picked), deduped against the current set.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the ids to add.
     */
    nodeSelectionAdded(state, action: PayloadAction<string[]>) {
      state.selectedNodeIds = [...new Set([...state.selectedNodeIds, ...action.payload])]
    },
    /**
     * Flip one node in/out of the selection (a shift-click on a single node).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the node id to toggle.
     */
    nodeSelectionToggled(state, action: PayloadAction<string>) {
      const id = action.payload
      state.selectedNodeIds = state.selectedNodeIds.includes(id)
        ? state.selectedNodeIds.filter((other) => other !== id)
        : [...state.selectedNodeIds, id]
    },
    /**
     * Drop the whole hand-picked selection (the Clear button, or an alt-click
     * on empty canvas) — grounding falls back to the full visible set.
     *
     * @param state The slice state (mutated via immer).
     */
    nodeSelectionCleared(state) {
      state.selectedNodeIds = []
    },
    /**
     * Home: back to the default no-graph state (the page-load look). The
     * epoch bump remounts the teacher panel for fresh run state; the
     * transcript and highlights clear themselves via extraReducers.
     *
     * @param state The slice state (mutated via immer).
     */
    workspaceCleared(state) {
      state.graph = null
      state.seedRef = null
      state.discoveredNodes = []
      state.discoveredEdges = []
      state.visibleNodeIds = []
      state.selectedNodeIds = []
      state.layout = 'timeline'
      state.error = null
      state.epoch += 1
    },
    /**
     * The shared search/graph error overlay (null clears it).
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the message, or null to clear.
     */
    errorSet(state, action: PayloadAction<string | null>) {
      state.error = action.payload
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadGraph.pending, (state) => {
        state.loading = true
        state.buildProgress = null
        state.error = null
      })
      .addCase(loadGraph.fulfilled, (state, action) => {
        state.graph = action.payload
        state.buildProgress = null
        // The reference actually requested — refresh must re-fetch with this
        // same string to bust the exact snapshot the server keyed.
        state.seedRef = action.meta.arg.seed
        state.discoveredNodes = []
        state.discoveredEdges = []
        // Cleared until GraphExplorer republishes this graph's visible set —
        // never carry the previous graph's ids into the new one's grounding.
        state.visibleNodeIds = []
        // A hand-picked selection is per-graph; a new seed starts unscoped.
        state.selectedNodeIds = []
        state.epoch += 1
        state.loading = false
      })
      .addCase(loadGraph.rejected, (state, action) => {
        state.loading = false
        state.buildProgress = null
        state.error = action.error.message ?? 'Failed to load graph'
      })
      .addCase(restoreSession.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(restoreSession.fulfilled, (state, action) => {
        state.graph = action.payload.graph
        // A restore has no cached-snapshot origin; refreshing it does a real
        // S2 rebuild, best-effort keyed by the seed's arXiv id (else paperId).
        state.seedRef = action.payload.graph.seed.arxiv_id ?? action.payload.graph.seed.id
        state.discoveredNodes = []
        state.discoveredEdges = []
        state.visibleNodeIds = []
        state.selectedNodeIds = []
        state.layout = action.payload.layout
        state.epoch += 1
        state.loading = false
      })
      .addCase(restoreSession.rejected, (state, action) => {
        state.loading = false
        state.error = action.error.message ?? 'Failed to restore session'
      })
  },
})

export const {
  discoveryMerged,
  layoutSet,
  buildProgressSet,
  visibleNodesSet,
  nodeSelectionSet,
  nodeSelectionAdded,
  nodeSelectionToggled,
  nodeSelectionCleared,
  errorSet,
  workspaceCleared,
} = workspaceSlice.actions
export default workspaceSlice.reducer

// --- Selectors ---------------------------------------------------------------

type StateWithWorkspace = { workspace: WorkspaceState }

/**
 * The whole workspace slice (graph, discoveries, layout, load state).
 *
 * @param state The root state.
 * @returns The workspace slice.
 */
export const selectWorkspace = (state: StateWithWorkspace) => state.workspace

/** The full seed node (the stream bodies need every Node field, not the
 * GraphResponse's compact seed header). */
export const selectSeedNode = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (graph) => graph?.nodes.find((node) => node.is_seed) ?? null,
)

/**
 * The teacher's grounding scope: the nodes VISIBLE on the canvas plus
 * everything discovered this session, deduped — narrowed to the user's
 * hand-picked selection when there is one. Grounding tracks what's on
 * screen — the graph ships a much larger pool than the filters show, and the
 * agents must reason over the papers the user actually sees, not the hidden
 * remainder.
 *
 * When `selectedNodeIds` is non-empty the graph side is the **intersection**
 * of the selection with the visible set (`selected ∩ visible`): a hand-pick
 * narrows *within* what the filters already show, so hiding a relation after
 * selecting also drops those nodes from scope. An empty selection means "no
 * manual pick" and the whole visible set grounds. Either way, **discoveries
 * are always kept** (the agent pulled them in), even if a filter or the
 * selection would exclude them.
 *
 * `visibleNodeIds` is published by GraphExplorer's view filter; before it
 * lands (e.g. the instant a graph loads) grounding is just the discoveries,
 * which corrects on the next render.
 */
export const selectGroundingNodes = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (state: StateWithWorkspace) => state.workspace.visibleNodeIds,
  (state: StateWithWorkspace) => state.workspace.selectedNodeIds,
  (graph, discovered, visibleNodeIds, selectedNodeIds): GraphNode[] => {
    if (!graph) return []
    const visible = new Set(visibleNodeIds)
    const hasSelection = selectedNodeIds.length > 0
    const selected = new Set(selectedNodeIds)
    const seen = new Set<string>()
    const merged: GraphNode[] = []
    // On-screen graph nodes first — trimmed to the hand-picked set when one is
    // active — then all discoveries (kept regardless of filter/selection,
    // since the agent pulled them in).
    for (const node of graph.nodes) {
      if (!visible.has(node.id) || seen.has(node.id)) continue
      if (hasSelection && !selected.has(node.id)) continue
      seen.add(node.id)
      merged.push(node)
    }
    for (const node of discovered) {
      if (seen.has(node.id)) continue
      seen.add(node.id)
      merged.push(node)
    }
    return merged
  },
)

/**
 * The hand-picked selection as a Set, for the canvas's selection ring and
 * dimming (and any count readout). Empty when nothing is picked.
 *
 * @param state The root state.
 * @returns The selected node ids as a Set.
 */
export const selectNodeSelectionSet = createSelector(
  (state: StateWithWorkspace) => state.workspace.selectedNodeIds,
  (selectedNodeIds) => new Set(selectedNodeIds),
)

/** Legend flags: any agent-discovered papers on the canvas (dashed ring),
 * incl. a restored session's; any from ungrounded topic search (pink). */
export const selectHasDiscovered = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    discovered.length > 0 || (graph?.nodes.some((node) => node.discovered) ?? false),
)

export const selectHasSearchHits = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    discovered.some((node) => node.rels.includes('search')) ||
    (graph?.nodes.some((node) => node.discovered && node.rels.includes('search')) ?? false),
)
