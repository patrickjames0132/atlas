/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The AI teacher: streaming lecture, and agentic Q&A with a graph or without.
 * Each is a `text/event-stream` POST decoded through the shared readSSE.
 *
 * (Named `agents` to match the backend's `routes/agents.py` and the `agents`
 * package behind it — every stream here is a workflow of the agents
 * orchestrator.)
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { readSSE } from './sse'
import type { GraphNode, GraphEdge, Provider } from './graph'

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
  /**
   * Map from an inline `[n]` marker in `text` (key, stringified) to the node
   * id it points at — resolved frontend-side against the lecture's fixed
   * numbered grounding list (lectures never discover, so the numbering can't
   * shift). Not sent by the backend; attached before the beat is stored so the
   * renderer can make each `[n]` clickable. Absent on older saved sessions.
   */
  refs?: Record<string, string>
  /**
   * A real paper figure attached to this beat (proxied image + the paper's
   * caption + the figure's number in the lecture's pool). `title` names the
   * source paper when the lecture drew from several (history/evolution);
   * null when every figure is the seed's own (intuition). Absent on bridge
   * lectures and older saved sessions.
   */
  figure?: { image: string; caption: string; number: number; title?: string | null } | null
}

/**
 * What story the lecture tells, each pinned to one kind of graph node: the
 * seed's references (`history`), the seed paper itself read in chapters
 * (`intuition`), the landmark papers that cite it (`evolution`), the latest
 * publications (`frontier`), or a conceptual bridge from the seed to a target
 * paper (`bridge`).
 */
export type LectureMode = 'history' | 'intuition' | 'evolution' | 'frontier' | 'bridge'

/**
 * The display name of each lecture mode — the single source of the copy shown
 * on the mode buttons, in the "Now playing" header, and sent to the researcher
 * as a played lecture's title. Kept here (not in a component) so the panel and
 * the ask-payload builder can't drift.
 */
export const LECTURE_TITLES: Record<LectureMode, string> = {
  history: 'How we got here',
  intuition: "This paper's intuition",
  evolution: "What's evolved since",
  frontier: 'The current frontier',
  bridge: 'Bridging two topics',
}

/**
 * A lecture already played this session, trimmed to what the researcher needs
 * as context (its title + each beat's heading/text) — sent on {@link streamAsk}
 * so a Q&A answer can build on the narrative instead of re-deriving it.
 */
export interface PlayedLecture {
  title: string
  beats: { heading: string; text: string }[]
}

/**
 * New papers (+ the edges connecting them) the researcher pulled in via its
 * expand_node / search_papers tools — to be merged into the live graph.
 * (Lectures never emit these: a lecture narrates the visible graph as-is.)
 */
export interface Discovery {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

/** Callbacks for {@link streamLecture}. Optional ones may be omitted. */
export interface LectureHandlers {
  /** A new beat arrived — append it to the lecture panel. */
  onBeat: (beat: Beat) => void
  /** The library index for the lecture's `[Sn]` markers (before any beat).
   *  Intuition mode only — the other modes retrieve no passages. */
  onSourceRefs?: (refs: Record<string, SourceRef>) => void
  onDone?: () => void
  onError?: (message: string) => void
  /** Abort to cancel the stream (e.g. when the user closes the panel). */
  signal?: AbortSignal
}

/**
 * Stream a lecture over the visible graph. Beats arrive one at a time; a
 * lecture never expands the graph, so beats and the up-front library index
 * are the only payload frames.
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
    else if (event === 'source_refs')
      h.onSourceRefs?.((data as { refs: Record<string, SourceRef> }).refs)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { message: string }).message)
  })
}

/**
 * A step the researcher took — reading a paper, expanding the graph to one not
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
  /** The shown float's own designation ("Figure 12.4", "Table 2") for the
   *  chip text; null/absent on failures, label-less captions, and pre-v5.28
   *  sessions (the chip then falls back to the number in `figure`). */
  label?: string | null
  /**
   * Why a failed search never turned anything up — search_papers only, and
   * only when `ok` is false. Undefined on success, and on saved sessions
   * from before this field existed (renders as a generic "Tried" then).
   */
  reason?: 'empty_query' | 'steps_exhausted' | 'budget_exhausted' | 'error'
}

/**
 * A figure the researcher pulled into its answer (via show_figure): a same-origin
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
  /**
   * The float's own designation parsed off its caption ("Figure 12.4",
   * "Table 2") — the card heading, with `caption` holding the remaining
   * text. Null/absent when the caption carries no designation (and on
   * pre-v5.28 sessions); the card then numbers attachments by slot.
   */
  label?: string | null
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
  /** The library index for this answer's `[Sn]` markers (before any prose). */
  onSourceRefs?: (refs: Record<string, SourceRef>) => void
  /** What grounded the answer, once it's finished. */
  onProvenance?: (provenance: ProvenanceEvent) => void
  /** The papers the finished prose cites, resolved to title + URL. */
  onPaperRefs?: (refs: Record<string, PaperRef>) => void
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
 *             scope), the graph's provider (so the researcher's expand/search/
 *             hydrate use the same backend), optional source_ids scoping the
 *             researcher's library search to a subset of uploaded sources, and
 *             optional lectures already played this session (extra context the
 *             answer may build on).
 * @param h    Event handlers; see {@link AskHandlers}.
 */
export async function streamAsk(
  body: {
    question: string
    session_id: string
    seed: GraphNode
    nodes: GraphNode[]
    provider: Provider
    source_ids?: string[]
    lectures?: PlayedLecture[]
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
    else if (event === 'source_refs')
      h.onSourceRefs?.((data as { refs: Record<string, SourceRef> }).refs)
    else if (event === 'provenance') h.onProvenance?.(data as ProvenanceEvent)
    else if (event === 'paper_refs')
      h.onPaperRefs?.((data as { refs: Record<string, PaperRef> }).refs)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { message: string }).message)
  })
}

/**
 * One numbered library source an answer's `[Sn]` markers may point at,
 * resolved server-side (the model only ever writes the index).
 */
export interface SourceRef {
  /** The real source id — what a click will open once the viewer lands. */
  source_id: string
  /** The source's stored title, rendered in place of the marker. */
  title: string
}

/**
 * One paper an answer's `[n]` marker points at, resolved server-side.
 *
 * With a graph open the frontend resolves `[n]` itself against the numbered
 * list it holds, and a click spotlights the node. With no graph it holds
 * nothing — every paper arrived mid-answer and there is no canvas — so this
 * carries what a reader needs instead: the title, and somewhere to go.
 */
export interface PaperRef {
  node_id: string
  title: string
  /** The paper's landing page; may be empty. */
  url: string
}

/**
 * What actually grounded an answer — observed server-side, never the model's
 * own claim about where its knowledge came from. The transcript turns these
 * counts into one plain line; see `provenanceLine`.
 */
export interface ProvenanceEvent {
  /** Whether the student had a library to search at all. */
  had_library: boolean
  /** How many times the agent reached retrieval (0 = it never looked). */
  searches: number
  /** Passages retrieval handed back across those searches. */
  passages: number
  /** Distinct library sources the finished prose cites. */
  cited_sources: number
  /** Graph papers the finished prose cites. */
  cited_papers: number
}

/**
 * Legacy: the librarian's one-shot retrieval summary, from before v6.7.0 made
 * retrieval a tool. Nothing emits it any more — kept so saved sessions from
 * that era still render their turns.
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
  /** A tool step to render as a trace chip — a source search, or a library
   *  figure being shown (or failing to show). */
  onTrace?: (t: TraceEvent) => void
  /** A figure the agent attached from an uploaded PDF. */
  onFigure?: (f: AnswerFigure) => void
  /** The library index for this answer's `[Sn]` markers (before any prose). */
  onSourceRefs?: (refs: Record<string, SourceRef>) => void
  /** What grounded the answer, once it's finished. */
  onProvenance?: (provenance: ProvenanceEvent) => void
  /** The papers the finished prose cites, resolved to title + URL. */
  onPaperRefs?: (refs: Record<string, PaperRef>) => void
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

/**
 * Stream an answer grounded purely in the user's local library — no graph.
 * A single retrieve event, then prose tokens — interleaved with figure
 * traces/attachments when the agent pulls a figure from an uploaded PDF.
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
    // Every trace is a tool step now — the one-shot retrieval summary went
    // away with the librarian in v6.7.0.
    else if (event === 'trace') h.onTrace?.(data as TraceEvent)
    else if (event === 'figure') h.onFigure?.(data as AnswerFigure)
    else if (event === 'source_refs')
      h.onSourceRefs?.((data as { refs: Record<string, SourceRef> }).refs)
    else if (event === 'provenance') h.onProvenance?.(data as ProvenanceEvent)
    else if (event === 'paper_refs')
      h.onPaperRefs?.((data as { refs: Record<string, PaperRef> }).refs)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { message: string }).message)
  })
}
