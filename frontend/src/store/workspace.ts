/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The workspace slice: the loaded graph, the agent's discoveries, the layout
 * choice, and the load/restore/save thunks — the cross-cutting core that the
 * canvas renders, the teacher grounds in, and Save serializes.
 *
 * Serializability rule: this slice holds the RAW GraphResponse and discovery
 * arrays (plain JSON). The mutable sim dataset (`Base`) is derived FROM this
 * state canvas-side and never enters the store — react-force-graph mutates
 * its objects, the exact opposite of what Redux state may be.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { createAsyncThunk, createSelector, createSlice, nanoid } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import {
  fetchGraphStream,
  getSession,
  saveSession,
  type Beat,
  type ChatMsg,
  type BuildProgress,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
  type LectureMode,
  type Provider,
  type SaveSessionBody,
  type SavedSessionMeta,
} from '../api'
import { cleanNode, countRels } from '../graph/model'
import type { VNode } from '../graph/model'
import type { Conversation, TranscriptState } from './transcript'

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
  /**
   * The academic-data backend graphs are built from — the header dropdown's
   * choice. An app-wide setting (persists across Home, unlike the graph
   * itself); `loadGraph` sends it on every build, and it's carried into a
   * saved session so a restore's Refresh rebuilds under the same provider.
   */
  provider: Provider
  /**
   * Bumps on Home and session restore — the shell keys the teacher panel on it,
   * so a bump remounts the panel. A graph *load* deliberately doesn't bump:
   * the conversation survives a re-seed, and remounting would rebuild its
   * scroll container at the top (see the `loadGraph` reducer).
   */
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
  provider: 's2',
  epoch: 0,
  loading: false,
  buildProgress: null,
  error: null,
}

/**
 * Load (or re-seed) the graph for an arXiv id, pasted URL, or provider node id.
 * The build uses the workspace's currently-selected `provider` (the header
 * dropdown) unless the caller names one, so a re-seed and a Refresh stay on
 * the same backend.
 *
 * @param seed     The paper reference to build the neighborhood around.
 * @param refresh  Bypass the server's day-cached snapshot for this seed and
 *                 rebuild from the provider (the "Refresh" action) — useful when
 *                 the provider's data for a paper has visibly changed.
 * @param provider Build under this backend instead of the selected one, and
 *                 leave the workspace on it. Only a chat citation passes this:
 *                 its `node_id` came from whichever provider answered, and an
 *                 id means nothing anywhere else — so a dropdown switched
 *                 mid-conversation would otherwise turn a live chip into a
 *                 failed build. The switch is the honest outcome, not a side
 *                 effect: the graph on screen really is from that backend, and
 *                 every expand from here follows it.
 */
export const loadGraph = createAsyncThunk<
  GraphResponse,
  { seed: string; refresh?: boolean; provider?: Provider },
  { state: { workspace: WorkspaceState } }
>('workspace/loadGraph', ({ seed, refresh = false, provider }, { dispatch, getState }) =>
  fetchGraphStream(seed, provider ?? getState().workspace.provider, refresh, (progress) =>
    dispatch(buildProgressSet(progress)),
  ),
)

/**
 * Switch the academic-data backend, then rebuild the current graph (if any)
 * under it. The provider is an app-wide choice, but changing it re-seeds the
 * paper on screen so the switch is immediately visible.
 *
 * @param provider The backend to switch to ('s2' / 'openalex').
 */
export const switchProvider = createAsyncThunk<
  void,
  Provider,
  { state: { workspace: WorkspaceState } }
>('workspace/switchProvider', (provider, { dispatch, getState }) => {
  const { provider: current, seedRef } = getState().workspace
  if (provider === current) return
  dispatch(providerSet(provider))
  if (seedRef) dispatch(loadGraph({ seed: seedRef }))
})

/** A saved chat turn or lecture beat as it may appear on disk: `graphRefs` /
 *  `graph_refs` on anything saved from v6.12.0 on, the older bare `refs` on
 *  everything before. */
type LegacyRefs = { refs?: Record<string, string> }

/**
 * Carry a saved chat turn's `[n]` → node-id map onto the current field name.
 * Saves predating the `refs` → `graphRefs` rename are still out there, and a
 * silently dropped map is the worst outcome: the turn restores looking fine,
 * with every citation reduced to inert text.
 *
 * @param message The saved chat turn.
 * @returns The turn with `graphRefs` populated from whichever key it carries.
 */
function withGraphRefs<Message extends { graphRefs?: Record<string, string> }>(
  message: Message,
): Message {
  const legacy = (message as Message & LegacyRefs).refs
  return message.graphRefs || !legacy ? message : { ...message, graphRefs: legacy }
}

/**
 * The lecture-beat twin of `withGraphRefs`. Beats are wire objects, so their
 * field is snake_case (`graph_refs`) — the older saves carry `refs` there too.
 *
 * @param beat The saved lecture beat.
 * @returns The beat with `graph_refs` populated from whichever key it carries.
 */
function withBeatGraphRefs(beat: Beat): Beat {
  const legacy = (beat as Beat & LegacyRefs).refs
  return beat.graph_refs || !legacy ? beat : { ...beat, graph_refs: legacy }
}

/**
 * Apply a per-beat migration across every cached lecture in a save.
 *
 * @param lectures The saved per-mode lecture cache.
 * @param migrate  The per-beat transform to apply.
 * @returns The cache with each mode's beats migrated.
 */
function mapLectures(
  lectures: Partial<Record<LectureMode, Beat[]>>,
  migrate: (beat: Beat) => Beat,
): Partial<Record<LectureMode, Beat[]>> {
  return Object.fromEntries(
    Object.entries(lectures).map(([mode, beats]) => [mode, (beats ?? []).map(migrate)]),
  )
}

/**
 * Reopen a saved exploration.
 *
 * Three shapes arrive here and each restores differently:
 *
 * - **Graphless** (no `graph_ref`, no `nodes`) — a conversation held before
 *   any graph existed. Restores to the landing chat with its transcript;
 *   `graph: null` is a valid resting state the store already expresses.
 * - **Reference** (the current shape) — the graph is rebuilt from
 *   `graph_ref.seed_ref`. Instant while the server's 1-day snapshot cache is
 *   warm; a real provider fetch when it is not, which is the cost Patrick
 *   accepted for keeping the conversation, not the graph, as the stored
 *   thing. A rebuild that **fails** (provider down, seed no longer
 *   resolvable) is not fatal: the conversation still restores, graphless,
 *   rather than losing the whole exploration to an unreachable API.
 * - **Legacy** (`nodes` inline, pre-2026-08-29) — used directly, no rebuild,
 *   so an old save keeps the exact papers it was stored with.
 *
 * The discovered papers are merged back over the rebuilt graph by the
 * reducer, since no rebuild can reproduce them.
 */
export const restoreSession = createAsyncThunk('workspace/restoreSession', async (id: string) => {
  // Minted here so the transcript slice and the shell agree on which
  // conversation this restore produced, without either having to guess.
  const conversationKey = nanoid()
  const saved = await getSession(id)
  const data = saved.data
  let graph: GraphResponse | null = null
  let seedRef: string | null = null

  if (data.nodes?.length && data.seed) {
    // Legacy: the whole graph is right here.
    graph = {
      seed: {
        id: data.seed.id,
        arxiv_id: data.seed.arxiv_id ?? null,
        title: data.seed.title,
      },
      nodes: data.nodes,
      edges: data.edges ?? [],
      counts: countRels(data.nodes),
    }
    seedRef = data.seed.arxiv_id || data.seed.id
  } else if (data.graph_ref) {
    seedRef = data.graph_ref.seed_ref
    try {
      // The stream API directly, NOT `loadGraph` — dispatching that thunk
      // would fire its own fulfilled reducer, which resets the discovery
      // arrays and the epoch, racing the restore's own reducer below.
      graph = await fetchGraphStream(data.graph_ref.seed_ref, data.provider ?? 's2')
    } catch {
      // The conversation is the durable half and it survives this.
      graph = null
    }
  }

  return {
    conversationKey,
    // The name it is already stored under. Without this the shell has no way
    // to tell the autosave that this conversation is an EXISTING exploration,
    // and its first save would re-title it — discarding a name the reader may
    // have set by hand.
    name: saved.name,
    graph,
    seedRef,
    discoveredNodes: data.discovered_nodes ?? [],
    discoveredEdges: data.discovered_edges ?? [],
    layout: data.layout ?? ('timeline' as const),
    // Pre-v5.0.0 saves have no provider; the app was S2-backed then, so default there.
    provider: data.provider ?? ('s2' as const),
    // (Old saves may carry a hist_trace field from the retired lecture
    // backfill — ignored; lectures no longer expand the graph.)
    transcript: {
      chat: (data.chat ?? []).map(withGraphRefs),
      // New saves carry the per-mode lecture cache directly. A pre-caching
      // save has only a flat `beats` array with no mode recorded — fold it in
      // under `history` (the primary "how we got here" mode) so the lecture
      // isn't lost, and show it.
      lectures: mapLectures(
        data.lectures ?? (data.beats?.length ? { history: data.beats } : {}),
        withBeatGraphRefs,
      ),
      // Saves from before structured library citations carry no source maps;
      // their beats' [Sn] markers (if any) degrade to raw text, as designed.
      lectureSources: data.lectureSources ?? {},
      activeMode: data.activeMode ?? (data.beats?.length ? ('history' as const) : null),
    },
  }
})

/**
 * Save the current exploration. The store IS the source of truth.
 *
 * **A graphless exploration is a normal save.** This used to throw
 * `No graph to save yet.`, which — once the landing chat became the front
 * door — meant a long conversation held before any graph existed could not
 * be stored at all. That refusal was the data loss the autosave exists to
 * end, so it is gone.
 *
 * What goes on the wire is the *conversation* plus a `graph_ref`, not the
 * graph: reopening rebuilds it (see `restoreSession`). The discovery arrays
 * are the deliberate exception — no rebuild can reproduce a paper the agent
 * found mid-chat, so those travel with the conversation that produced them.
 */
export const saveWorkspace = createAsyncThunk<
  SavedSessionMeta,
  { name: string; id?: string },
  { state: { workspace: WorkspaceState; transcript: TranscriptState } }
>('workspace/save', ({ name, id }, { getState }) =>
  saveSession(buildSaveBody(getState(), name, id)),
)

/**
 * Build the save body from a store snapshot — **synchronously, and from the
 * state you hand it**, not from whatever the store holds later.
 *
 * That distinction is the whole reason this is a separate function. Leaving
 * an exploration flushes a save and then immediately clears the workspace;
 * because the autosave has to await a name before it can POST, a body built
 * inside the request would be assembled *after* the clear and would write an
 * empty blob over the conversation being left. The caller snapshots first,
 * awaits second.
 *
 * @param state The two slices to save, read at the moment of the call.
 * @param name  The exploration's name.
 * @param id    The row to overwrite; omit to create one.
 * @returns The POST body for `saveSession`.
 */
/**
 * Settle anything still in flight on a turn before it is written to disk.
 *
 * **A saved turn is never mid-stream**, because nothing that reads a saved
 * blob can resume the request that was running when it was written. Leaving
 * an exploration flushes a save and then aborts its streams, so without this
 * a turn interrupted mid-answer is persisted with `pending: true` traces —
 * and reopening it shows a chip that says "Searching the web…", with a live
 * spinner, forever.
 *
 * The partial answer itself is kept: it is real work the reader may still
 * want. Only the *claim that something is still happening* is corrected — a
 * pending step becomes an unfinished one, which the transcript already
 * renders honestly ("Tried the web").
 *
 * @param chat The conversation as it stands in the store.
 * @returns The same turns, with no step left claiming to be in progress.
 */
export function settleInFlight(chat: ChatMsg[]): ChatMsg[] {
  const last = chat.length - 1
  return chat.map((turn, index) => {
    const settled = turn.trace?.some((step) => step.pending)
      ? {
          ...turn,
          trace: turn.trace.map((step) =>
            step.pending ? { ...step, pending: false, ok: false } : step,
          ),
        }
      : turn
    // **The commonest failure of all is recorded here**, not by the stream:
    // the reader closed the tab (or the exploration) mid-answer, so the client
    // never reached the end of the run to mark it. This save IS that moment —
    // the flush on `pagehide` — and a turn being written with a trace, no
    // prose, and nothing left to produce it has plainly not finished. Only the
    // last turn qualifies: an empty assistant turn earlier in the transcript
    // would already carry its own marker.
    if (index === last && settled.role === 'assistant' && !settled.text && !settled.failed) {
      return { ...settled, failed: 'This answer stopped before it finished.' }
    }
    return settled
  })
}

export function buildSaveBody(
  state: { workspace: WorkspaceState; transcript: TranscriptState },
  name: string,
  id?: string,
): SaveSessionBody {
  const { workspace, transcript } = state
  // Read directly rather than through `selectConversation`: transcript.ts
  // imports this module's actions at slice-creation time, so a value import
  // back would close a cycle. The type import above is erased and safe.
  const conversation: Conversation | undefined = transcript.byKey[transcript.activeKey]
  const graph = workspace.graph
  return {
    id,
    name,
    // A graph on screen but no seedRef would be unrebuildable, so the
    // reference is what gates `graph_ref` — not the graph's presence.
    graph_ref:
      graph && workspace.seedRef
        ? { seed: graph.seed, seed_ref: workspace.seedRef, n_nodes: graph.nodes.length }
        : undefined,
    layout: workspace.layout,
    provider: workspace.provider,
    // cleanNode strips the researcher's per-conversation idx from discovered nodes.
    discovered_nodes: workspace.discoveredNodes.map((node) => cleanNode(node as VNode)),
    discovered_edges: workspace.discoveredEdges,
    chat: settleInFlight(conversation?.chat ?? []),
    lectures: conversation?.lectures ?? {},
    lectureSources: conversation?.lectureSources ?? {},
    activeMode: conversation?.activeMode ?? null,
  }
}

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
     * Set the academic-data backend (the header dropdown). Prefer the
     * `switchProvider` thunk, which also re-seeds the current graph.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the provider.
     */
    providerSet(state, action: PayloadAction<Provider>) {
      state.provider = action.payload
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
     * New Exploration: back to the default no-graph state (the page-load
     * look). The epoch bump remounts the teacher panel for fresh run state.
     *
     * Carries the key of the conversation to open, so the transcript slice
     * can start a *new* one rather than wiping what is there — an exploration
     * left behind may still be streaming, and it stays in the rail.
     *
     * @param state   The slice state (mutated via immer).
     * @param _action Carries the new conversation's key, for the transcript
     *   slice — this reducer only needs to know that it happened.
     */
    workspaceCleared(state, _action: PayloadAction<{ conversationKey: string }>) {
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
        // Loading a graph deliberately does NOT bump the epoch. The shell
        // keys the teacher panel on it, so a bump remounts the panel and
        // rebuilds the transcript's scroll container at the top — and since
        // the conversation now survives a graph change, that would throw the
        // reader back to the start of an answer they were mid-way through.
        // Only Home and a session restore remount now; `useConversation`
        // aborts in-flight streams on the seed change instead of relying on
        // an unmount that no longer happens.
        //
        // An override built under a different backend; the dropdown has to
        // follow, or the header would claim one provider while the graph and
        // every expand off it run on another.
        if (action.meta.arg.provider) state.provider = action.meta.arg.provider
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
        // The saved reference, so a later Refresh busts the same cache key the
        // rebuild just used. Null on a graphless exploration.
        state.seedRef = action.payload.seedRef
        // Merged back over the rebuilt graph: the agent's finds are stored
        // precisely because no rebuild reproduces them. Dropped when the
        // rebuild failed — they hang off a graph that isn't there.
        state.discoveredNodes = action.payload.graph ? action.payload.discoveredNodes : []
        state.discoveredEdges = action.payload.graph ? action.payload.discoveredEdges : []
        state.visibleNodeIds = []
        state.selectedNodeIds = []
        state.layout = action.payload.layout
        state.provider = action.payload.provider
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
  providerSet,
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
/**
 * Every paper id the workspace currently holds — the built graph plus whatever
 * the agent has pulled in since. What a transcript's `[n]` citation is checked
 * against before it renders as a live control: since a chat-seeded jump keeps
 * the conversation across a graph change, an older answer can cite papers that
 * are no longer anywhere on screen, and a chip that silently highlights nothing
 * is worse than one that says so.
 *
 * Deliberately the *loaded* set, not the *visible* one (`visibleNodeIds`): the
 * question is "does this paper exist here", not "is it past the year slider" —
 * keying on the filters would flicker chips grey and blue as a slider is
 * dragged.
 */
export const selectWorkspaceNodeIds = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    new Set([...(graph?.nodes ?? []).map((node) => node.id), ...discovered.map((node) => node.id)]),
)

/**
 * Every edge on the graph — the built snapshot's plus anything the agent has
 * discovered since.
 *
 * Sent with a lecture request, because edges are the only thing that can
 * answer "is this paper a neighbour **of the seed**". A node's `rels` records
 * what its relation *is*, never what it is *to*, so once `expand_node` could
 * grow the graph past its seed, a paper hanging off a reference was
 * indistinguishable from one the seed actually cites — and the history
 * lecture narrated both. See the backend's `_story_nodes`.
 *
 * Deliberately NOT filtered to the visible/selected set: the backend only
 * looks at edges touching the seed, and the node filter is applied to `nodes`
 * anyway. Filtering here would just be a second place to get it wrong.
 */
export const selectGraphEdges = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredEdges,
  (graph, discovered) => [...(graph?.edges ?? []), ...discovered],
)

/**
 * How many papers a lecture will leave out because they hang off *another*
 * paper rather than the seed.
 *
 * The same predicate the backend scopes by (`_story_nodes` → `_seed_neighbors`),
 * computed here so the panel can say so instead of leaving a reader wondering
 * why the papers they just expanded went unmentioned. Both sides ask one
 * question — is this joined to the seed by an edge? — so the sentence and the
 * lecture can't disagree.
 *
 * Counted over the GROUNDING nodes, not the whole graph: a satellite the
 * reader has already filtered out isn't being left out of anything, so
 * mentioning it would be noise.
 */
export const selectSatelliteCount = createSelector(
  selectGroundingNodes,
  selectGraphEdges,
  selectSeedNode,
  (nodes, edges, seed) => {
    if (!seed) return 0
    const adjacent = new Set<string>()
    for (const edge of edges) {
      if (edge.source === seed.id) adjacent.add(edge.target)
      else if (edge.target === seed.id) adjacent.add(edge.source)
    }
    return nodes.filter((node) => !node.is_seed && node.id !== seed.id && !adjacent.has(node.id))
      .length
  },
)

export const selectHasDiscovered = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    discovered.length > 0 || (graph?.nodes.some((node) => node.discovered) ?? false),
)
