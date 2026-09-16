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
  type SessionData,
  type SourceRef,
  type Provider,
  type SaveSessionBody,
  type SavedSessionMeta,
} from '../api'
import { cleanNode, countRels, foldRetiredEdgeTypes, foldRetiredNodeRels } from '../graph/model'
import type { VNode } from '../graph/model'
import { explorationOpened, threadActivated } from './explorations'
import { resolveScope } from '../scope/resolve'
import type { ResolvedScope } from '../scope/resolve'
import type { ExplorationsState, ThreadRecord } from './explorations'
import type { Conversation, TranscriptState } from './transcript'

export interface WorkspaceState {
  viewFilters?: {
    enabled: string[]
    yearLo: number
    yearHi: number
    citeLo: number
    citeHi: number
    relCaps: Record<string, number>
  }
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
   * Ids of the nodes PASSING THE VIEW FILTERS (relation chips, year range,
   * citation window, per-chip caps) — published by GraphExplorer's filter,
   * independent of the viewport, of a collapsed panel, and of what else the
   * canvas draws on top. This is the **default scope**, the last rung of the
   * priority list in `scope/resolve.ts`: what the agents reason over when the
   * message and the selection say nothing. Deliberately the *eligible* set
   * rather than the *drawn* set — the canvas also draws selected and
   * message-scoped papers the filters would hide, and those must not leak
   * back into the default. Empty until the first render.
   */
  visibleNodeIds: string[]
  /**
   * Ids SELECTED on the canvas as the teacher's scope — the middle rung of
   * `scope/resolve.ts`'s list: when non-empty it is the scope, whatever the
   * filters say (a selected paper a later slider change would hide stays in
   * scope, and the canvas keeps drawing it, marked). Two things write it:
   * the reader's hand (alt-drag marquee / shift-click), and a message that
   * chose its own scope ("what do the references say?") — `send` makes that
   * scope the selection, and it *stays* after the turn, like one made by
   * hand (Patrick's call, 2026-09-15: a scope set by a request changes the
   * scope permanently rather than reverting to the previous pick). Empty
   * means "no pick". Saved with the thread, like the filters.
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
  loadRequestId?: string
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
 * @param provider Build under this backend instead of the selected one. Graph
 *                 identity includes the provider; explicit Explore actions
 *                 resume or create the matching thread.
 */
export const loadGraph = createAsyncThunk<
  GraphResponse,
  { seed: string; refresh?: boolean; provider?: Provider },
  {
    state: {
      workspace: WorkspaceState
      explorations?: ExplorationsState
      transcript?: TranscriptState
    }
  }
>(
  'workspace/loadGraph',
  async ({ seed, refresh = false, provider }, { dispatch, getState, requestId }) => {
    const before = getState()
    const backend = provider ?? before.workspace.provider
    const owner = before.explorations?.byId[before.explorations.activeId]
    const known = owner?.threads.find(
      (thread) =>
        thread.identity === `${backend}:${seed}` ||
        (thread.data.graph_ref?.seed_ref === seed && thread.data.provider === backend),
    )
    const graph =
      !refresh && known?.workspace?.graph
        ? known.workspace.graph
        : await fetchGraphStream(seed, backend, refresh, (progress) =>
            dispatch(buildProgressSet(progress)),
          )
    if (owner) {
      // Resolve aliases before creating: an arXiv URL and a provider id may name the same seed.
      const current = getState()
      if (
        current.explorations?.activeId !== owner.id ||
        current.transcript?.activeKey !== before.transcript?.activeKey ||
        current.workspace.loadRequestId !== requestId
      )
        throw new Error('Graph load superseded by exploration navigation')
      const record = current.explorations.byId[owner.id]
      const identity = `${backend}:${graph.seed.id}`
      const existing = record.threads.find((thread) => thread.identity === identity)
      const thread: ThreadRecord = existing ?? {
        id: nanoid(),
        title: graph.seed.title,
        identity,
        origin: record.activeThreadId,
        data: {
          chat: [],
          layout: 'timeline',
          provider: backend,
          graph_ref: { seed: graph.seed, seed_ref: seed, n_nodes: graph.nodes.length },
        },
      }
      const pending = current.transcript?.byKey[thread.id]?.pendingDiscoveries
      if (thread.id !== record.activeThreadId)
        dispatch(
          threadActivated({
            explorationId: owner.id,
            thread,
            outgoingId: record.activeThreadId,
            outgoing: current.workspace,
            requestId,
          }),
        )
      if (pending?.nodes.length) {
        dispatch(discoveryMerged(pending))
        dispatch({ type: 'transcript/pendingDiscoveriesDrained', payload: thread.id })
      }
    }
    return graph
  },
)

/** Delete a graph thread after moving its active canvas back to General.
 * @param threadId Thread to delete.
 */
export const deleteThread = createAsyncThunk<
  void,
  string,
  {
    state: {
      workspace: WorkspaceState
      explorations: ExplorationsState
      transcript: TranscriptState
    }
  }
>('workspace/deleteThread', async (threadId, { dispatch, getState }) => {
  const state = getState()
  const record = state.explorations.byId[state.explorations.activeId]
  const thread = record.threads.find((item) => item.id === threadId)
  if (!thread?.identity) return
  if (record.activeThreadId === threadId) {
    const general = record.threads.find((item) => !item.identity)!
    await dispatch(activateThread(general.id))
  }
  dispatch({ type: 'explorations/threadRemoved', payload: threadId })
  dispatch({ type: 'transcript/conversationDropped', payload: threadId })
})

/** Activate a sibling, rebuilding only when its graph is not in memory.
 * @param threadId The thread to show.
 */
export const activateThread = createAsyncThunk<
  void,
  string,
  {
    state: {
      workspace: WorkspaceState
      explorations: ExplorationsState
      transcript: TranscriptState
    }
  }
>('workspace/activateThread', async (threadId, { dispatch, getState }) => {
  const state = getState()
  const owner = state.explorations.byId[state.explorations.activeId]
  const thread = owner.threads.find((item) => item.id === threadId)
  if (!thread || threadId === owner.activeThreadId) return
  const pending = state.transcript.byKey[threadId]?.pendingDiscoveries
  dispatch(
    threadActivated({
      explorationId: owner.id,
      thread,
      outgoingId: owner.activeThreadId,
      outgoing: state.workspace,
    }),
  )
  if (pending?.nodes.length && getState().workspace.graph) {
    dispatch(discoveryMerged(pending))
    dispatch({ type: 'transcript/pendingDiscoveriesDrained', payload: threadId })
  }
  if (thread.identity && !thread.workspace?.graph && thread.data.graph_ref) {
    await dispatch(
      loadGraph({ seed: thread.data.graph_ref.seed_ref, provider: thread.data.provider }),
    ).unwrap()
  }
})

/**
 * Switch the academic-data backend, then rebuild the current graph (if any)
 * under it. The provider is an app-wide choice, but changing it re-seeds the
 * paper on screen so the switch is immediately visible.
 *
 * The re-seed goes by the seed's arXiv id when it has one — the one reference
 * both providers read natively. `seedRef` is whatever the current graph was
 * requested by, which after a search pick is a raw node id of the provider
 * being left (an S2 paperId, an OpenAlex `W…`); the backend translates those,
 * but at the cost of a round-trip to the old provider.
 *
 * @param provider The backend to switch to ('s2' / 'openalex').
 */
export const switchProvider = createAsyncThunk<
  void,
  Provider,
  { state: { workspace: WorkspaceState } }
>('workspace/switchProvider', (provider, { dispatch, getState }) => {
  const { provider: current, seedRef, graph } = getState().workspace
  if (provider === current) return
  const seed = graph?.seed.arxiv_id || seedRef
  if (seed) dispatch(loadGraph({ seed, provider }))
  else dispatch(providerSet(provider))
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
export function withGraphRefs<Message extends { graphRefs?: Record<string, string> }>(
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
 * The order a pre-v7.17.0 save's cached lectures are preferred in, when the
 * save doesn't say which one was on screen. `history` first because it was
 * the default mode and the one most saves hold.
 */
const LEGACY_MODE_ORDER = ['history', 'intuition', 'evolution', 'frontier', 'bridge'] as const

/**
 * Fold a save's lecture into the transcript as a turn, whatever era the save
 * is from.
 *
 * **Why this is a fold and not a load.** Every save written before v7.21.0
 * holds its lecture in a slot *beside* the conversation, because that is where
 * a lecture lived when a button produced it. There is no slot any more — a
 * lecture is a turn — so a restore either converts the old shape or silently
 * throws the reader's lecture away. It converts.
 *
 * Three source shapes exist. A **v7.17.0-era** save carries a single `lecture`
 * array. A **v6-era** save carries a per-mode cache (`lectures`) plus the mode
 * that was on screen (`activeMode`) — up to four lectures where one turn is
 * wanted, so the shown one wins, falling back to the first played mode in
 * `LEGACY_MODE_ORDER`. An **ancient** save carries a flat `beats` array from
 * before per-mode caching existed. Dropping a v6 save's extra modes is the
 * honest trade: they narrate a scope the reader no longer has, and the
 * alternative is restoring four lectures nobody asked for.
 *
 * The turn has **no preceding user turn**, deliberately. A button lecture was
 * never asked for in words, and inventing a `/lecture summary` the reader never
 * typed would put words in their mouth — and claim a framing the save does not
 * record. It also carries no `routedTo`, so the transcript offers no reroute:
 * there was no guess to undo.
 *
 * @param data    The saved session payload.
 * @param migrate The per-beat transform to apply (graph-ref backfill).
 * @returns The turn to append, or null when the save holds no lecture.
 */
export function restoredLectureTurn(
  data: SessionData,
  migrate: (beat: Beat) => Beat = withBeatGraphRefs,
): ChatMsg | null {
  /**
   * The turn a set of beats and their `[Sn]` index become.
   *
   * @param beats      The saved lecture's beats, in order.
   * @param sourceRefs Its `[Sn]` marker index, empty when the save has none.
   * @returns The assistant turn to append.
   */
  const turn = (beats: Beat[], sourceRefs: Record<string, SourceRef>): ChatMsg => ({
    role: 'assistant',
    // Empty because a lecture's prose lives in its beats. `ChatMessage`
    // renders the beat list where an answer's text would go.
    text: '',
    beats: beats.map(migrate),
    sourceRefs,
  })
  if (data.lecture?.length) {
    // v7.17.0 shape: `lectureSources` is the marker index itself.
    return turn(data.lecture, (data.lectureSources ?? {}) as Record<string, SourceRef>)
  }
  const cache = data.lectures ?? {}
  const played = LEGACY_MODE_ORDER.filter((mode) => cache[mode]?.length)
  const mode = (data.activeMode && cache[data.activeMode]?.length && data.activeMode) || played[0]
  if (mode) {
    // v6-era shape: `lectureSources` is keyed by mode, so index into it with
    // the mode whose lecture we just chose.
    const byMode = (data.lectureSources ?? {}) as Partial<Record<string, Record<string, SourceRef>>>
    return turn(cache[mode] ?? [], byMode[mode] ?? {})
  }
  // Ancient: a flat, un-attributed beats array. Saves from before structured
  // library citations carry no source maps at all; their beats' `[Sn]` markers
  // (if any) degrade to raw text, as designed.
  return data.beats?.length ? turn(data.beats, {}) : null
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
    // Legacy: the whole graph is right here. The folds rewrite relation tags
    // this build no longer has — a pre-v7.17.0 save carries `latest` nodes,
    // which belong to no filter chip and would come back invisible.
    const restoredNodes = foldRetiredNodeRels(data.nodes)
    graph = {
      seed: {
        id: data.seed.id,
        arxiv_id: data.seed.arxiv_id ?? null,
        title: data.seed.title,
      },
      nodes: restoredNodes,
      edges: foldRetiredEdgeTypes(data.edges ?? []),
      counts: countRels(restoredNodes),
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

  const lectureTurn = restoredLectureTurn(data, withBeatGraphRefs)

  return {
    conversationKey,
    // The name it is already stored under. Without this the shell has no way
    // to tell the autosave that this conversation is an EXISTING exploration,
    // and its first save would re-title it — discarding a name the reader may
    // have set by hand.
    name: saved.name,
    graph,
    seedRef,
    // Folded like the graph's own: a discovery merged onto the old `latest`
    // relation would otherwise belong to no chip either.
    discoveredNodes: foldRetiredNodeRels(data.discovered_nodes ?? []),
    discoveredEdges: foldRetiredEdgeTypes(data.discovered_edges ?? []),
    layout: data.layout ?? ('timeline' as const),
    // Pre-v5.0.0 saves have no provider; the app was S2-backed then, so default there.
    provider: data.provider ?? ('s2' as const),
    // (Old saves may carry a hist_trace field from the retired lecture
    // backfill — ignored; lectures no longer expand the graph.)
    transcript: {
      // A pre-v7.21.0 save's lecture is appended as the last turn (see
      // `restoredLectureTurn`). Last rather than first because the save does
      // not record *when* it was played, and the slot's `lectureShown` was
      // true — it was the thing the reader had on screen, so the end of the
      // transcript is the least wrong place for it.
      chat: [...(data.chat ?? []).map(withGraphRefs), ...(lectureTurn ? [lectureTurn] : [])],
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
    if (
      index === last &&
      settled.role === 'assistant' &&
      !settled.text &&
      !settled.beats?.length &&
      !settled.failed
    ) {
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
    viewFilters: workspace.viewFilters,
    selectedNodeIds: workspace.selectedNodeIds,
    layout: workspace.layout,
    provider: workspace.provider,
    // cleanNode strips the researcher's per-conversation idx from discovered nodes.
    discovered_nodes: workspace.discoveredNodes.map((node) => cleanNode(node as VNode)),
    discovered_edges: workspace.discoveredEdges,
    // Lectures ride along inside the turns that hold them. The `lecture` /
    // `lectureSources` slot fields, and the older `lectures` per-mode cache
    // and `activeMode`, are **read on restore and never written** since
    // v7.21.0 — see `restoredLectureTurn`.
    chat: settleInFlight(conversation?.chat ?? []),
  }
}

/** Restore a thread's own workspace, including its retained discoveries.
 * @param thread Thread being displayed.
 * @param epoch Remount generation for local component state.
 * @returns Workspace belonging only to this thread.
 */
function workspaceForThread(thread: ThreadRecord, epoch: number): WorkspaceState {
  if (thread.workspace) return { ...thread.workspace, epoch, loading: false, error: null }
  const data = thread.data
  const graph =
    data.nodes?.length && data.seed
      ? {
          seed: { ...data.seed, arxiv_id: data.seed.arxiv_id ?? null },
          nodes: foldRetiredNodeRels(data.nodes),
          edges: foldRetiredEdgeTypes(data.edges ?? []),
          counts: countRels(data.nodes),
        }
      : null
  return {
    ...initialState,
    epoch,
    graph,
    seedRef: data.graph_ref?.seed_ref ?? data.seed?.id ?? null,
    discoveredNodes: data.discovered_nodes ?? [],
    discoveredEdges: data.discovered_edges ?? [],
    provider: data.provider ?? 's2',
    layout: data.layout ?? 'timeline',
    viewFilters: data.viewFilters,
    selectedNodeIds: data.selectedNodeIds ?? [],
  }
}

const workspaceSlice = createSlice({
  name: 'workspace',
  initialState,
  reducers: {
    /** Keep each thread's declutter choices when its canvas is unmounted.
     * @param state Workspace state.
     * @param action Current filter values.
     */
    viewFiltersSet(state, action: PayloadAction<WorkspaceState['viewFilters']>) {
      state.viewFilters = action.payload
    },

    /**
     * Merge a discovery event, deduped against the graph and prior finds.
     *
     * @param state  The slice state (mutated via immer).
     * @param action Carries the discovered nodes and edges.
     */
    discoveryMerged(state, action: PayloadAction<{ nodes: GraphNode[]; edges: GraphEdge[] }>) {
      const knownIds = new Set([
        ...(state.graph?.nodes ?? []).map((node) => node.id),
        ...state.discoveredNodes.map((node) => node.id),
      ])
      for (const node of action.payload.nodes) {
        if (knownIds.has(node.id)) continue
        knownIds.add(node.id)
        state.discoveredNodes.push(node)
      }
      const edgeKey = (edge: GraphEdge) => `${edge.source}|${edge.target}|${edge.type}`
      const knownEdges = new Set(
        [...(state.graph?.edges ?? []), ...state.discoveredEdges].map(edgeKey),
      )
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
      .addCase(explorationOpened, (state, action) => {
        const thread = action.payload.threads.find(
          (item) => item.id === action.payload.activeThreadId,
        )!
        return workspaceForThread(thread, state.epoch + 1)
      })
      .addCase(threadActivated, (state, action) => ({
        ...workspaceForThread(action.payload.thread, state.epoch + 1),
        loadRequestId: action.payload.requestId,
      }))
      .addCase(loadGraph.pending, (state, action) => {
        state.loadRequestId = action.meta.requestId
        state.loading = true
        state.buildProgress = null
        state.error = null
      })
      .addCase(loadGraph.fulfilled, (state, action) => {
        if (state.loadRequestId !== action.meta.requestId) return
        state.loadRequestId = undefined
        state.graph = action.payload
        state.buildProgress = null
        // The reference actually requested — refresh must re-fetch with this
        // same string to bust the exact snapshot the server keyed.
        state.seedRef = action.meta.arg.seed

        // Cleared until GraphExplorer republishes this graph's visible set —
        // never carry the previous graph's ids into the new one's grounding.
        state.visibleNodeIds = []
        // Thread activation already restored its selection and remounted the
        // canvas. Refreshing this same graph keeps that thread's view intact.
        if (action.meta.arg.provider) state.provider = action.meta.arg.provider
        state.loading = false
      })
      .addCase(loadGraph.rejected, (state, action) => {
        if (state.loadRequestId !== action.meta.requestId) return
        state.loadRequestId = undefined
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
  viewFiltersSet,
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
 * The **default scope** — the priority list of `scope/resolve.ts` with no
 * message in play: the hand-picked selection when there is one, else the
 * papers passing the view filters. What the teacher panel's readouts show,
 * and what `useConversation.send` resolves *from* when the router reads
 * nothing off the message. The v7.17.0 selectors this replaced
 * (`selectGroundingNodes`, `selectLectureNodes`) intersected the selection
 * with the visible set and kept hidden discoveries for the researcher only;
 * both rules are gone — the selection stands whatever the filters do, and a
 * discovery is in scope on the same terms as any other paper.
 */
export const selectScope = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (state: StateWithWorkspace) => state.workspace.visibleNodeIds,
  (state: StateWithWorkspace) => state.workspace.selectedNodeIds,
  (graph, discovered, visibleNodeIds, selectedNodeIds): ResolvedScope =>
    resolveScope(null, graph, discovered, visibleNodeIds, selectedNodeIds),
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

export const selectHasDiscovered = createSelector(
  (state: StateWithWorkspace) => state.workspace.graph,
  (state: StateWithWorkspace) => state.workspace.discoveredNodes,
  (graph, discovered) =>
    discovered.length > 0 || (graph?.nodes.some((node) => node.discovered) ?? false),
)
