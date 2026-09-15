/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Ordered exploration writes with a synchronous browser-close outbox.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import type { SaveSessionBody } from '../api'

/** Local outbox prefix. Only unacknowledged saves live here. */
const PREFIX = 'atlas.pending-exploration.'

/** A writer preserves per-exploration order and replays unacknowledged saves.
 * The backend still owns durable storage; this small outbox covers page teardown
 * while an earlier write or title request is unresolved.
 */
export class ExplorationWrites {
  private queues = new Map<string, Promise<void>>()
  private removed = new Set<string>()
  private write: (body: SaveSessionBody, unloading: boolean) => Promise<unknown>

  /** Create a queue around the session API.
   * @param write The network operation to serialize.
   */
  constructor(write: (body: SaveSessionBody, unloading: boolean) => Promise<unknown>) {
    this.write = write
  }

  /** Queue an immutable body; persist synchronously before any await.
   * @param body Complete exploration snapshot.
   * @param unloading Whether this is a browser teardown flush.
   * @returns Completion of this write, ordered after prior writes to its id.
   */
  enqueue(body: SaveSessionBody, unloading = false): Promise<void> {
    const id = body.id!
    if (this.removed.has(id)) return Promise.resolve()
    const encoded = JSON.stringify(body)
    try {
      localStorage.setItem(PREFIX + id, encoded)
    } catch {
      /* Storage may be full or disabled. */
    }
    const previous = this.queues.get(id) ?? Promise.resolve()
    const pending = previous
      .catch(() => {})
      .then(async () => {
        if (this.removed.has(id)) return
        await this.write(body, unloading)
        try {
          if (localStorage.getItem(PREFIX + id) === encoded) localStorage.removeItem(PREFIX + id)
        } catch {
          /* The network write succeeded even if local storage is disabled. */
        }
      })
    this.queues.set(id, pending)
    return pending
  }

  /** Stop queued writes and await the one that already reached the server.
   * @param id Exploration being deleted.
   * @returns Completion of any existing write, before the caller issues DELETE.
   */
  async remove(id: string): Promise<void> {
    this.removed.add(id)
    try {
      localStorage.removeItem(PREFIX + id)
    } catch {
      /* Optional outbox. */
    }
    await this.queues.get(id)?.catch(() => {})
  }

  /** Wait until the known writes finish before reading or renaming the row.
   * @param id Exploration to synchronize.
   * @returns Completion of its most recently queued write.
   */
  async idle(id: string): Promise<void> {
    await this.queues.get(id)?.catch(() => {})
  }

  /** Recover snapshots whose requests were interrupted by browser shutdown.
   * @returns Parsed exploration snapshots without mutating their content.
   */
  recover(): SaveSessionBody[] {
    const bodies: SaveSessionBody[] = []
    try {
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index)
        if (!key?.startsWith(PREFIX)) continue
        try {
          const body = JSON.parse(localStorage.getItem(key) ?? 'null') as SaveSessionBody | null
          if (
            body?.id &&
            body.exploration?.version === 1 &&
            Array.isArray(body.exploration.threads)
          )
            bodies.push(body)
        } catch {
          /* One malformed local item must not hide the other recoverable saves. */
        }
      }
    } catch {
      /* Local storage can be disabled without disabling server persistence. */
    }
    return bodies
  }
}
