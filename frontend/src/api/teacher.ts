/**
 * The AI teacher: streaming lecture, grounded/agentic Q&A, and offline library
 * chat. Each is a `text/event-stream` POST decoded through the shared readSSE.
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
 * A trimmed node the teacher needs — the visible graph is its grounding
 * scope, so only the fields that feed the prompt are sent.
 */
export interface TeacherNode {
  id: string
  title: string
  year: number | null
  citation_count?: number | null
  authors?: string | null
  tldr?: string | null
  abstract?: string | null
  rels: string[]
}

/**
 * What story the lecture tells: the field's history, the seed paper's
 * intuition, or a conceptual bridge from the seed to a target paper.
 */
export type LectureMode = 'history' | 'intuition' | 'bridge'

/**
 * A backward-in-time hop the history lecture took before narrating
 * (Phase 3e): how many foundational ancestors it pulled in and the oldest
 * year it reached.
 */
export interface LectureTrace {
  hop: number
  found: number
  oldest: number | null
  /** The hop hit an S2 error / rate limit rather than empty results. */
  error?: boolean
}

/** Callbacks for {@link streamLecture}. Optional ones may be omitted. */
export interface LectureHandlers {
  /** A new beat arrived — append it to the lecture panel. */
  onBeat: (beat: Beat) => void
  /** History-mode backward hop progress (precedes the beats). */
  onTrace?: (t: LectureTrace) => void
  /** Ancestors pulled in by the backward walk, to merge into the graph. */
  onNodes?: (d: Discovery) => void
  onDone?: () => void
  onError?: (message: string) => void
  /** Abort to cancel the stream (e.g. when the user closes the panel). */
  signal?: AbortSignal
}

/**
 * Stream a lecture over the visible graph. Beats arrive one at a time. In
 * history mode, trace + nodes events (the backward walk to the field's
 * roots) precede them.
 *
 * @param body The seed, the visible nodes, the lecture mode, and (bridge
 *             mode only) the target paper.
 * @param h    Event handlers; see {@link LectureHandlers}.
 */
export async function streamLecture(
  body: { seed: { title: string; id?: string }; nodes: TeacherNode[]; mode: LectureMode; target?: { title: string } },
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
    else if (event === 'trace') h.onTrace?.(data as LectureTrace)
    else if (event === 'nodes') h.onNodes?.(data as Discovery)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

/**
 * A step the agent took — reading a paper, expanding the graph to one not
 * yet shown, or searching for off-graph papers. Surfaced live in the chat as
 * the agent works.
 */
export interface TraceEvent {
  action: 'read' | 'expand' | 'search' | 'search_sources'
  ok: boolean
  title?: string | null
  index?: number
  /** 'summary' | 'full' — read_paper. */
  detail?: string
  /** 'references' | 'citations' | 'similar' — expand_node. */
  relation?: string
  /** New papers discovered / passages found. */
  found?: number
  /** Free-text query — search_papers / search_sources. */
  query?: string
  /** Year filter — search_papers. */
  year_from?: number | null
  year_to?: number | null
}

/**
 * New papers (+ the edges connecting them) the agent pulled in via
 * expand_node / search_papers, to be merged into the live graph.
 */
export interface Discovery {
  nodes: GraphNode[]
  edges: GraphEdge[]
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
  onNodes?: (d: Discovery) => void
  /** Drop streamed preamble that turned out to precede a tool call. */
  onDiscard?: () => void
  onDone?: () => void
  onError?: (message: string) => void
  /** Abort to cancel the stream mid-answer. */
  signal?: AbortSignal
}

/**
 * Stream a grounded answer: agent trace steps, prose tokens, then the nodes
 * it drew from. (Non-agentic backends just emit tokens + cited.)
 *
 * @param body The question, a session id for follow-up context, the seed,
 *             the visible nodes (the grounding scope), and an optional
 *             source_id scoping the agent's library search to one uploaded
 *             source (agentic backend only).
 * @param h    Event handlers; see {@link AskHandlers}.
 */
export async function streamAsk(
  body: {
    question: string
    session_id: string
    seed: { title: string; id?: string }
    nodes: TeacherNode[]
    source_id?: string
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
    else if (event === 'nodes') h.onNodes?.(data as Discovery)
    else if (event === 'discard') h.onDiscard?.()
    else if (event === 'cited') h.onCited((data as { node_ids: string[] }).node_ids)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

/**
 * Offline library chat (Phase 3d): the one trace it emits — which passages
 * the retrieval pulled, and from which sources — shown above the grounded
 * answer.
 */
export interface RetrieveEvent {
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
 * @param body The question, a session id for follow-up context, and an
 *             optional source_id to scope retrieval to one source.
 * @param h    Event handlers; see {@link AskSourcesHandlers}.
 */
export async function streamAskSources(
  body: { question: string; session_id: string; source_id?: string },
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
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}
