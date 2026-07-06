/**
 * Saved sessions & workspaces (Phase 4): persist the current graph + teacher
 * transcript, then reopen it later without a Semantic Scholar rebuild.
 */

import type { GraphNode, GraphEdge } from './graph'
import type { AnswerFigure, Beat, BackfillTrace, RetrieveEvent, TraceEvent } from './agents'

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
  /** The agent steps that produced this answer (assistant turns only). */
  trace?: TraceEvent[]
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
 * The heavy payload of a saved session: the full graph as it stood (every
 * node and edge, including agent-discovered ones, with their flags) plus the
 * teacher transcript. Restored straight into the explorer — no Semantic
 * Scholar rebuild.
 */
export interface SessionData {
  seed: SessionSeed
  layout: 'force' | 'timeline'
  nodes: GraphNode[]
  edges: GraphEdge[]
  chat: ChatMsg[]
  beats: Beat[]
  hist_trace: BackfillTrace[]
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
 * @returns The stored metadata row (with the new/updated id and timestamps).
 * @throws With the server's error message when the save fails.
 */
export async function saveSession(body: SaveSessionBody): Promise<SavedSessionMeta> {
  const res = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((data as { error?: string }).error || `Save failed (${res.status})`)
  return data as SavedSessionMeta
}

/**
 * Delete a saved session.
 *
 * Never throws — returns false on any failure.
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
