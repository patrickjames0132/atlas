// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExplorationWrites } from '../../src/shell/saveQueue'
import type { SaveSessionBody } from '../../src/api'

function body(name: string): SaveSessionBody {
  return {
    id: 'explore',
    name,
    layout: 'timeline',
    chat: [],
    exploration: { version: 1, activeThreadId: 'general', threads: [] },
  }
}
beforeEach(() => localStorage.clear())

describe('ordered durable outbox', () => {
  it('captures teardown immediately and keeps the newest body until it is acknowledged', async () => {
    let finish: (() => void) | undefined
    const written: string[] = []
    const write = vi.fn(async (snapshot: SaveSessionBody) => {
      written.push(snapshot.name)
      if (snapshot.name === 'old')
        await new Promise<void>((resolve) => {
          finish = resolve
        })
    })
    const queue = new ExplorationWrites(write)
    const old = queue.enqueue(body('old'))
    await Promise.resolve()
    await Promise.resolve()
    const latest = queue.enqueue(body('new'), true)
    expect(queue.recover()[0].name).toBe('new')
    finish!()
    await old
    await latest
    expect(written).toEqual(['old', 'new'])
    expect(queue.recover()).toEqual([])
  })
  it('does not resurrect an exploration deleted during a save', async () => {
    const write = vi.fn(async () => {})
    const queue = new ExplorationWrites(write)
    const pending = queue.enqueue(body('deleted'))
    await queue.remove('explore')
    await pending
    expect(write).not.toHaveBeenCalled()
    expect(queue.recover()).toEqual([])
  })
  it('retains failed writes for recovery on next launch', async () => {
    const queue = new ExplorationWrites(async () => {
      throw new Error('offline')
    })
    await expect(queue.enqueue(body('keep me'))).rejects.toThrow('offline')
    expect(queue.recover()[0].name).toBe('keep me')
  })
})
