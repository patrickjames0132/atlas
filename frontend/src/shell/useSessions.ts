/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The saved-session list behind the left rail: load it, save into it, rename
 * and delete rows.
 *
 * This lived inside the Sessions drawer until v7.8.0, where it was fine —
 * one component owned the list and was the only thing that showed it. Once
 * the list moved into the rail (always mounted, always visible) it needed to
 * survive independently of any one surface, so it became a hook the shell
 * owns and passes down.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useState } from 'react'
import { deleteSession, listSessions, renameSession } from '../api'
import type { SavedSessionMeta } from '../api'

/** What {@link useSessions} hands the rail. */
export interface SessionsApi {
  /** The saved sessions, newest-updated first. */
  sessions: SavedSessionMeta[]
  /** Re-read the list from the backend (after a save elsewhere). */
  refresh: () => Promise<void>
  /** Rename a row, optimistically. */
  rename: (id: string, name: string) => Promise<void>
  /** Delete a row, optimistically. */
  remove: (id: string) => Promise<void>
}

/**
 * Own the saved-session list.
 *
 * Both mutations are **optimistic**: the row changes in place immediately and
 * the list is re-read from the backend afterwards, so a failure corrects
 * itself on the next read rather than blocking the interaction. That trade is
 * right here specifically because neither action is destructive to anything
 * unrecoverable — a rename is a label, and a delete is already confirmed by
 * the menu it lives behind.
 *
 * @returns The list and its operations (see {@link SessionsApi}).
 */
export function useSessions(): SessionsApi {
  const [sessions, setSessions] = useState<SavedSessionMeta[]>([])

  const refresh = useCallback(async () => {
    setSessions(await listSessions())
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const rename = useCallback(
    async (id: string, name: string) => {
      setSessions((prev) => prev.map((row) => (row.id === id ? { ...row, name } : row)))
      await renameSession(id, name)
      await refresh()
    },
    [refresh],
  )

  const remove = useCallback(
    async (id: string) => {
      setSessions((prev) => prev.filter((row) => row.id !== id))
      await deleteSession(id)
      await refresh()
    },
    [refresh],
  )

  return { sessions, refresh, rename, remove }
}
