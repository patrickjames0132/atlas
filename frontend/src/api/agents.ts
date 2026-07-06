/**
 * The AI teacher: streaming lecture, agentic Q&A, and offline library chat.
 * Each is a `text/event-stream` POST decoded through the shared readSSE.
 *
 * (Named `agents` to match the backend's `routes/agents.py` and the `agents`
 * package behind it — every stream here is a workflow of the agents
 * orchestrator.)
 */

import { readSSE } from './sse'
import type { GraphNode, GraphEdge } from './graph'

/**
 * One beat of a lecture: a paragraph of narration bound to the graph nodes
 * it's about, so they light up in sync as the beat is revealed.
 */
export interface Beat {
  /** 3–6 word signpost shown above the paragraph. */
  heading: string
  /** The narration paragraph itself. */
  text: string
  /** Ids of the graph nodes to highlight while this beat is on screen. */
  node_ids: string[]
}

/**
 * What story the lecture tells: the field's history, the seed paper's
 * intuition, or a conceptual bridge from the seed to a target paper.
 */
export type LectureMode = 'history' | 'intuition' | 'bridge'

/**
 * A backward-in-time hop the history lecture took before narrating: how many
 * foundational ancestors it pulled in and the oldest year it reached.
 * (`action`/`error` are optional only for sessions saved by the pre-rewrite
 * app; live frames always carry them.)
 */
export interface BackfillTrace {
  action?: 'backfill'
  hop: number
  found: number
  oldest: number | null
  /** True when a hop hit an S2 error — "couldn't look" vs "found nothing". */
  error?: boolean
}

/**
 * New papers (+ the edges connecting them) a workflow pulled in — the
 * lecture's backward walk, or the tutor's expand_node / search_papers tools
 * — to be merged into the live graph.
 */
export interface Discovery {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

/** Callbacks for {@link streamLecture}. Optional ones may be omitted. */
export interface LectureHandlers {
  /** A new beat arrived — append it to the lecture panel. */
  onBeat: (beat: Beat) => void
  /** History-mode backward hop progress (precedes the beats). */
  onTrace?: (t: BackfillTrace) => void
  /** Ancestors pulled in by the backward walk, to merge into the graph. */
  onDiscovery?: (d: Discovery) => void
  onDone?: () => void
  onError?: (message: string) => void
  /** Abort to cancel the stream (e.g. when the user closes the panel). */
  signal?: AbortSignal
}

/**
 * Stream a lecture over the visible graph. Beats arrive one at a time. In
 * history mode, trace + discovery events (the backward walk to the field's
 * roots) precede them.
 *
 * @param body The seed, the visible nodes, the lecture mode, and (bridge
 *             mode only) the target paper. Nodes are the FULL graph-node
 *             shapes — the backend's typed boundary rejects trimmed ones.
 * @param h    Event handlers; see {@link LectureHandlers}.
 */
export async function streamLecture(
  body: { seed: GraphNode; nodes: GraphNode[]; mode: LectureMode; target?: GraphNode },
  h: LectureHandlers,
): Promise<void> {
  const res = await fetch('/api/lecture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: h.signal,
  })
  await readSSE(res, (event, data) => {
    if (event === 'beat') h.onBeat(data as Beat)
    else if (event === 'trace') h.onTrace?.(data as BackfillTrace)
    else if (event === 'discovery') h.onDiscovery?.(data as Discovery)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { message: string }).message)
  })
}

/**
 * A step the tutor took — reading a paper, expanding the graph to one not
 * yet shown, or searching for off-graph papers. Surfaced live in the chat as
 * the agent works.
 */
export interface TraceEvent {
  action: 'read' | 'expand' | 'search' | 'search_sources' | 'figure'
  ok: boolean
  title?: string | null
  index?: number | null
  /** 'summary' | 'full' — read_paper. */
  detail?: string
  /** 'references' | 'citations' | 'similar' — expand_node. */
  relation?: string | null
  /** New papers discovered / passages found. */
  found?: number | null
  /** Free-text query — search_papers / search_sources. */
  query?: string
  /** Year filter — search_papers. */
  year_from?: number | null
  year_to?: number | null
  /** Figure number the agent showed — show_figure. */
  figure?: number | null
}

/**
 * A figure the tutor pulled into its answer (via show_figure): a same-origin
 * proxied image URL, the paper's own caption, and which paper/figure it is.
 */
export interface AnswerFigure {
  /** Proxied image URL (`/api/figure_proxy?src=…`). */
  image: string
  caption: string
  /** The source paper's title. */
  title: string | null
  /** The paper's [n] index on the graph. */
  index?: number
  /** The figure's 1-based number in that paper. */
  figure?: number
  /**
   * The attachment's 1-based slot — pairs the figure with the `<<FIG n>>`
   * marker the agent places in its prose, so the image renders inline at
   * that point. Absent on pre-v1.22 saved sessions (those figures render
   * at the end of the bubble, the old behavior).
   */
  slot?: number
}

/** Callbacks for {@link streamAsk}. Optional ones may be omitted. */
export interface AskHandlers {
  /** A chunk of answer prose arrived — append it to the streaming bubble. */
  onToken: (text: string) => void
  /** The final citation list: ids of the papers the answer drew from. */
  onCited: (nodeIds: string[]) => void
  /** An agent step (read/expand/search) to render as a trace chip. */
  onTrace?: (t: TraceEvent) => void
  /** Papers the agent discovered, to merge into the live graph. */
  onDiscovery?: (d: Discovery) => void
  /** A figure the agent attached to its answer, to render inline. */
  onFigure?: (f: AnswerFigure) => void
  onDone?: () => void
  onError?: (message: string) => void
  /** Abort to cancel the stream mid-answer. */
  signal?: AbortSignal
}

/**
 * Stream a grounded answer: agent trace steps, discoveries, prose tokens,
 * then the papers it drew from. (The old `discard` frame is gone — the
 * agent's pre-answer narration is never streamed, so there's nothing to
 * disavow.)
 *
 * @param body The question, a session id for follow-up context, the seed,
 *             the visible nodes (full graph-node shapes — the grounding
 *             scope), and optional source_ids scoping the tutor's library
 *             search to a subset of uploaded sources.
 * @param h    Event handlers; see {@link AskHandlers}.
 */
export async function streamAsk(
  body: {
    question: string
    session_id: string
    seed: GraphNode
    nodes: GraphNode[]
    source_ids?: string[]
  },
  h: AskHandlers,
): Promise<void> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: h.signal,
  })
  await readSSE(res, (event, data) => {
    if (event === 'token') h.onToken((data as { text: string }).text)
    else if (event === 'trace') h.onTrace?.(data as TraceEvent)
    else if (event === 'discovery') h.onDiscovery?.(data as Discovery)
    else if (event === 'figure') h.onFigure?.(data as AnswerFigure)
    else if (event === 'cited') h.onCited((data as { node_ids: string[] }).node_ids)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { message: string }).message)
  })
}

/**
 * Offline library chat: the one trace it emits — which passages the
 * retrieval pulled, and from which sources — shown above the grounded
 * answer. (`action` is optional only for old saved sessions.)
 */
export interface RetrieveEvent {
  action?: 'retrieval'
  found: number
  sources: string[]
}

/** Callbacks for {@link streamAskSources}. Optional ones may be omitted. */
export interface AskSourcesHandlers {
  /** A chunk of answer prose arrived. */
  onToken: (text: string) => void
  /** The retrieval summary (emitted once, before any prose). */
  onRetrieve?: (r: RetrieveEvent) => void
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

/**
 * Stream an answer grounded purely in the user's local library — no graph.
 * A single retrieve event, then prose tokens.
 *
 * @param body The question, a session id for follow-up context, and optional
 *             source_ids to scope retrieval to a subset of sources.
 * @param h    Event handlers; see {@link AskSourcesHandlers}.
 */
export async function streamAskSources(
  body: { question: string; session_id: string; source_ids?: string[] },
  h: AskSourcesHandlers,
): Promise<void> {
  const res = await fetch('/api/ask_sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: h.signal,
  })
  await readSSE(res, (event, data) => {
    if (event === 'token') h.onToken((data as { text: string }).text)
    else if (event === 'trace') h.onRetrieve?.(data as RetrieveEvent)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { message: string }).message)
  })
}
