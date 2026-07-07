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
  fetchGraph,
  getSession,
  saveSession,
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
  /** Papers the agent pulled in mid-conversation (deduped against the graph). */
  discoveredNodes: GraphNode[]
  discoveredEdges: GraphEdge[]
  layout: 'force' | 'timeline'
  /** Bumps on every load/restore — the teacher panel remounts per epoch. */
  epoch: number
  loading: boolean
  /** The shared error surface (graph loads + seed search). */
  error: string | null
}

const initialState: WorkspaceState = {
  graph: null,
  discoveredNodes: [],
  discoveredEdges: [],
  layout: 'force',
  epoch: 0,
  loading: false,
  error: null,
}

/** Load (or re-seed) the graph for an arXiv id, pasted URL, or S2 paperId. */
export const loadGraph = createAsyncThunk('workspace/loadGraph', (seed: string) =>
  fetchGraph(seed),
)

/**
 * Reopen a saved session: rebuild its graph directly (no S2 fetch, so no
 * rate-limit cost and the exact discovered papers are preserved). The
 * transcript slice restores itself from this thunk's payload.
 */
export const restoreSession = createAsyncThunk(
  'workspace/restoreSession',
  async (id: string) => {
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
      layout: data.layout ?? ('force' as const),
      transcript: {
        chat: data.chat ?? [],
        beats: data.beats ?? [],
        histTrace: data.hist_trace ?? [],
      },
    }
  },
)

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
    nodes: [...graph.nodes, ...workspace.discoveredNodes].map((n) => cleanNode(n as VNode)),
    edges: [...graph.edges, ...workspace.discoveredEdges],
    chat: transcript.chat,
    beats: transcript.beats,
    hist_trace: transcript.histTrace,
  })
})

const workspaceSlice = createSlice({
  name: 'workspace',
  initialState,
  reducers: {
    /** Merge a discovery event, deduped against the graph and prior finds. */
    discoveryMerged(
      state,
      action: PayloadAction<{ nodes: GraphNode[]; edges: GraphEdge[] }>,
    ) {
      if (!state.graph) return
      const knownIds = new Set([
        ...state.graph.nodes.map((n) => n.id),
        ...state.discoveredNodes.map((n) => n.id),
      ])
      for (const node of action.payload.nodes) {
        if (knownIds.has(node.id)) continue
        knownIds.add(node.id)
        state.discoveredNodes.push(node)
      }
      const edgeKey = (e: GraphEdge) => `${e.source}|${e.target}|${e.type}`
      const knownEdges = new Set(
        [...state.graph.edges, ...state.discoveredEdges].map(edgeKey),
      )
      for (const edge of action.payload.edges) {
        if (knownEdges.has(edgeKey(edge))) continue
        knownEdges.add(edgeKey(edge))
        state.discoveredEdges.push(edge)
      }
    },
    layoutSet(state, action: PayloadAction<'force' | 'timeline'>) {
      state.layout = action.payload
    },
    /** Home: back to the default no-graph state (the page-load look). The
     * epoch bump remounts the teacher panel for fresh run state; the
     * transcript and highlights clear themselves via extraReducers. */
    workspaceCleared(state) {
      state.graph = null
      state.discoveredNodes = []
      state.discoveredEdges = []
      state.layout = 'force'
      state.error = null
      state.epoch += 1
    },
    /** The shared search/graph error overlay (null clears it). */
    errorSet(state, action: PayloadAction<string | null>) {
      state.error = action.payload
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadGraph.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(loadGraph.fulfilled, (state, action) => {
        state.graph = action.payload
        state.discoveredNodes = []
        state.discoveredEdges = []
        state.epoch += 1
        state.loading = false
      })
      .addCase(loadGraph.rejected, (state, action) => {
        state.loading = false
        state.error = action.error.message ?? 'Failed to load graph'
      })
      .addCase(restoreSession.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(restoreSession.fulfilled, (state, action) => {
        state.graph = action.payload.graph
        state.discoveredNodes = []
        state.discoveredEdges = []
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

export const { discoveryMerged, layoutSet, errorSet, workspaceCleared } =
  workspaceSlice.actions
export default workspaceSlice.reducer

// --- Selectors ---------------------------------------------------------------

type StateWithWorkspace = { workspace: WorkspaceState }

export const selectWorkspace = (state: StateWithWorkspace) => state.workspace

/** The full seed node (the stream bodies need every Node field, not the
 * GraphResponse's compact seed header). */
export const selectSeedNode = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (graph) => graph?.nodes.find((n) => n.is_seed) ?? null,
)

/**
 * The teacher's grounding scope: the graph plus everything discovered this
 * session, deduped (a restored session carries its discovered papers inside
 * graph.nodes already).
 */
export const selectGroundingNodes = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered): GraphNode[] => {
    if (!graph) return []
    const seen = new Set<string>()
    const merged: GraphNode[] = []
    for (const node of [...graph.nodes, ...discovered]) {
      if (seen.has(node.id)) continue
      seen.add(node.id)
      merged.push(node)
    }
    return merged
  },
)

/** Legend flags: any agent-discovered papers on the canvas (dashed ring),
 * incl. a restored session's; any from ungrounded topic search (pink). */
export const selectHasDiscovered = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    discovered.length > 0 || (graph?.nodes.some((n) => n.discovered) ?? false),
)

export const selectHasSearchHits = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    discovered.some((n) => n.rels.includes('search')) ||
    (graph?.nodes.some((n) => n.discovered && n.rels.includes('search')) ?? false),
)
