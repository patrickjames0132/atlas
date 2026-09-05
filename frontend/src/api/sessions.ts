/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Saved sessions & workspaces (Phase 4): persist the current graph + teacher
 * transcript, then reopen it later without a Semantic Scholar rebuild.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { GraphNode, GraphEdge, Provider } from './graph'
import type {
  AnswerFigure,
  Beat,
  LectureMode,
  PaperRef,
  ProvenanceEvent,
  RetrieveEvent,
  SourceRef,
  TraceEvent,
} from './agents'

/**
 * One chat turn in the teacher transcript. Hoisted here (shared by
 * Teacher.tsx and the saved-session payload) so a restored session rehydrates
 * the exact messages — text, the papers an answer cited, and the agent's
 * trace steps.
 */
export interface ChatMsg {
  role: 'user' | 'assistant'
  text: string
  /** Ids of the papers this answer cited (assistant turns only). */
  cited?: string[]
  /**
   * Map from an inline `[n]` reference marker (the key, stringified) to the
   * node id it points at — the position `n` had in the numbered grounding list
   * for THIS answer. Lets the renderer make each `[n]` clickable (glowing that
   * one paper). Only referenced-and-resolvable indices are kept, so it stays
   * small and survives a saved-session reload. Assistant/researcher turns only.
   */
  graphRefs?: Record<string, string>
  /**
   * Map from an inline `[Sn]` library-citation index (the key, stringified) to
   * the source it names. Resolved server-side and streamed *before* the prose
   * — unlike `graphRefs`, which the frontend resolves itself from the numbered
   * grounding list it already holds; only the backend knows which of the
   * user's sources a given turn retrieved. Page-free on purpose: the page
   * lives in the marker (`[S2, p.460]`), so this map is complete up front.
   */
  sourceRefs?: Record<string, SourceRef>
  /**
   * What grounded this answer — whether the library was searched, what it
   * returned, what the prose cites. Absent on turns from before v6.7.0 and on
   * user turns; the transcript then shows no grounding line at all.
   */
  provenance?: ProvenanceEvent
  /**
   * `[n]` index → the paper it names, with title and URL. Only needed when
   * the frontend can't resolve the marker itself (graph-free turns, where
   * `graphRefs` is empty because no numbered list was ever held). Absent on turns
   * from before v6.7.0.
   */
  paperRefs?: Record<string, PaperRef>
  /** The agent steps that produced this answer (assistant turns only). */
  trace?: TraceEvent[]
  /**
   * Why this answer never arrived — an assistant turn that ended without
   * producing any prose.
   *
   * Persisted, because the reason it is most often seen is a run the reader
   * *left*: they closed the tab or deleted the exploration mid-answer, and
   * came back to a turn that shows a trace and then simply stops. Without a
   * durable marker the transcript gives no account of itself at all.
   */
  failed?: string
  /** Figures the agent pulled into this answer (assistant turns only). */
  figures?: AnswerFigure[]
  /** Library-retrieval summary — set only on the graph-free library-chat path
   *  (which retrieves passages instead of running the agent). */
  retrieve?: RetrieveEvent
}

/** The seed a session was explored from (enough to re-open without a rebuild). */
export interface SessionSeed {
  id: string
  arxiv_id?: string | null
  title: string
}

/**
 * What it takes to put an exploration's graph back, without storing the graph.
 *
 * The `seed_ref` is the exact reference the graph was loaded with (arXiv id,
 * pasted URL or S2 paperId) — the same string `Refresh` keys on — so a reopen
 * rebuilds under the identical cache key rather than a merely equivalent one.
 */
export interface SessionGraphRef {
  seed: SessionSeed
  seed_ref: string
  /** How big the graph was when saved — a list-view hint, not a guarantee. */
  n_nodes?: number
}

/**
 * The payload of a saved exploration: the **conversation**, plus a reference
 * to whichever graph was open while it was held.
 *
 * The graph itself is deliberately not stored (Patrick, 2026-08-29). A reopen
 * rebuilds it from `graph_ref` — instantly while the 1-day snapshot cache is
 * warm, from the provider when it is not, which costs rate-limited calls and
 * can come back a slightly different graph as citation data moves.
 *
 * `discovered_nodes`/`discovered_edges` are the exception, and are stored:
 * the papers the *agent* pulled in mid-conversation exist in no cache and no
 * rebuild reproduces them, because they are a product of the conversation
 * rather than of the seed. They are merged back over the rebuilt graph.
 */
export interface SessionData {
  /**
   * Present only on **legacy** saves (before 2026-08-29), which stored the
   * whole graph inline. New saves carry `graph_ref` instead; a graphless
   * exploration carries neither.
   */
  seed?: SessionSeed
  /** How to rebuild the graph. Absent on legacy saves and graphless ones. */
  graph_ref?: SessionGraphRef
  layout: 'force' | 'timeline'
  /**
   * The academic-data backend this graph was built from — restored so a later
   * Refresh / re-seed rebuilds under the same provider. Absent on pre-v5.0.0
   * saves (they default to 's2' on restore).
   */
  provider?: Provider
  /**
   * Legacy: the full graph as it stood. Only on saves predating the reference
   * shape — when present, restore uses it directly and skips the rebuild, so
   * an old save keeps the exact papers it was saved with.
   */
  nodes?: GraphNode[]
  edges?: GraphEdge[]
  /** Papers the agent found mid-conversation — stored, never rebuildable. */
  discovered_nodes?: GraphNode[]
  discovered_edges?: GraphEdge[]
  chat: ChatMsg[]
  /**
   * The per-mode lecture cache (mode → its beats) as it stood when saved —
   * every lecture the user had played this session, so a restore brings them
   * all back, not just the visible one.
   */
  lectures?: Partial<Record<LectureMode, Beat[]>>
  /**
   * Per-mode library index for the `[Sn]` markers each cached lecture's beats
   * cite. Absent on saves predating structured library citations — those
   * beats' markers (if any) degrade to raw text on restore.
   */
  lectureSources?: Partial<Record<LectureMode, Record<string, SourceRef>>>
  /** Which cached lecture was on screen when saved (null/absent = none). */
  activeMode?: LectureMode | null
  /**
   * Legacy: a single un-attributed lecture's beats, from saves made before
   * per-mode caching. New saves omit it; restore folds it into `lectures`
   * (see `restoreSession`).
   */
  beats?: Beat[]
  /**
   * Legacy field from the retired lecture backfill — old saves carry it;
   * new saves omit it and restore ignores it.
   */
  hist_trace?: unknown[]
}

/** A lightweight saved-session row for the list view (no graph/chat payload). */
export interface SavedSessionMeta {
  id: string
  name: string
  seed_id: string | null
  seed_title: string | null
  n_nodes: number
  /** Unix epoch seconds. */
  created_at: number
  updated_at: number
}

/** A full saved session, as returned by `GET /api/sessions/<id>`. */
export interface SavedSession extends SavedSessionMeta {
  data: SessionData
}

/**
 * The body POSTed to save a workspace. An `id` overwrites that session in
 * place; omit it to create a new one.
 */
export interface SaveSessionBody extends SessionData {
  id?: string
  name: string
}

/**
 * List the user's saved sessions (metadata only).
 *
 * Never throws — failures degrade to an empty list so the drawer still opens.
 *
 * @returns The saved sessions' metadata rows, newest first.
 */
export async function listSessions(): Promise<SavedSessionMeta[]> {
  try {
    const res = await fetch('/api/sessions')
    if (!res.ok) return []
    return ((await res.json()) as { sessions: SavedSessionMeta[] }).sessions ?? []
  } catch {
    return []
  }
}

/**
 * Fetch the full saved session (graph + transcript) to restore into the
 * explorer.
 *
 * @param id The saved session's id.
 * @returns The full session payload (graph + transcript).
 * @throws With the server's error message when the session doesn't exist or
 *         can't be loaded.
 */
export async function getSession(id: string): Promise<SavedSession> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(id)}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error((data as { error?: string }).error || `Failed to load session (${res.status})`)
  }
  return (await res.json()) as SavedSession
}

/**
 * Save the current workspace. A body with an `id` overwrites that saved
 * session; without one, a new session is created.
 *
 * @param body    The workspace payload to store (see {@link SaveSessionBody}).
 * @param options `keepalive` lets the request survive the page unloading.
 * @returns The stored metadata row (with the new/updated id and timestamps).
 * @throws With the server's error message when the save fails.
 */
export async function saveSession(
  body: SaveSessionBody,
  options: { keepalive?: boolean } = {},
): Promise<SavedSessionMeta> {
  const res = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    // The tab is going away. A normal fetch is cancelled with the page, so
    // the last save — the one that matters most — simply never lands;
    // `keepalive` lets the request outlive the document. Its 64KB body cap is
    // why this is not the default: an ordinary save carries whatever the
    // conversation has grown to, while the unload path would rather send a
    // large exploration on a best-effort basis than not send it at all.
    keepalive: options.keepalive,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((data as { error?: string }).error || `Save failed (${res.status})`)
  return data as SavedSessionMeta
}

/**
 * Delete a saved session.
 *
 * Never throws — returns false on any failure.
 *
 * @param id The saved session's id.
 * @returns True when the session existed and is now gone.
 */
export async function deleteSession(id: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!res.ok) return false
    return ((await res.json()) as { deleted: boolean }).deleted
  } catch {
    return false
  }
}

/**
 * Rename a saved session, leaving its snapshot alone.
 *
 * Never throws — returns false on any failure, like `deleteSession`. The
 * sidebar renames optimistically and reverts on false, so a dead backend
 * costs a flicker rather than an error dialog over a list.
 *
 * @param id   The saved session's id.
 * @param name The new name; blank falls back to "Untitled exploration".
 * @returns True when the session existed and is now renamed.
 */
export async function renameSession(id: string, name: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) return false
    return ((await res.json()) as { renamed: boolean }).renamed
  } catch {
    return false
  }
}

/**
 * Ask the server to name an exploration after the conversation held in it.
 *
 * Never throws, and a null title is a normal answer, not a failure — the
 * model may be unreachable (no key, provider down) or the conversation may
 * not say enough yet. The caller always has a free fallback in the reader's
 * own first message, and an exploration must never fail to save because a
 * nicety was unavailable.
 *
 * @param turns The conversation's opening turns, oldest first, as plain text.
 * @returns The generated title, or null when one can't be written.
 */
export async function titleForConversation(turns: string[]): Promise<string | null> {
  try {
    const res = await fetch('/api/sessions/title', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turns }),
    })
    if (!res.ok) return null
    return ((await res.json()) as { title: string | null }).title ?? null
  } catch {
    return null
  }
}
