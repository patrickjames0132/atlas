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
import type { AnswerFigure, Beat, LectureMode, RetrieveEvent, TraceEvent } from './agents'

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
  refs?: Record<string, string>
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
  /**
   * The academic-data backend this graph was built from — restored so a later
   * Refresh / re-seed rebuilds under the same provider. Absent on pre-v5.0.0
   * saves (they default to 's2' on restore).
   */
  provider?: Provider
  nodes: GraphNode[]
  edges: GraphEdge[]
  chat: ChatMsg[]
  /**
   * The per-mode lecture cache (mode → its beats) as it stood when saved —
   * every lecture the user had played this session, so a restore brings them
   * all back, not just the visible one.
   */
  lectures?: Partial<Record<LectureMode, Beat[]>>
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
 * @param body The workspace payload to store (see {@link SaveSessionBody}).
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
