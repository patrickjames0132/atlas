/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Lazy migration and lossless exploration serialization.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { nanoid } from '@reduxjs/toolkit'
import type { SavedSession, SaveSessionBody, SessionData, ChatMsg } from '../api'
import type { ExplorationRecord, ExplorationsState, ThreadRecord } from './explorations'
import type { TranscriptState } from './transcript'
import { buildSaveBody, restoredLectureTurn, withGraphRefs } from './workspace'
import type { WorkspaceState } from './workspace'

/** Split legacy exchanges by the assistant stamp, retaining every unstamped turn.
 * @param saved The unchanged on-disk record.
 * @returns An in-memory exploration; reading never writes it back.
 */
export function migrateExploration(saved: SavedSession): ExplorationRecord {
  if (saved.data.exploration)
    return { id: saved.id, title: saved.name, ...saved.data.exploration, revision: 0 }
  const data = saved.data
  const seed = data.graph_ref?.seed ?? data.seed
  const provider = data.provider ?? 's2'
  const threads: ThreadRecord[] = [
    {
      id: nanoid(),
      title: 'General',
      identity: null,
      data: { chat: [], layout: 'timeline', provider },
    },
  ]
  const general = threads[0]
  const home: ThreadRecord = seed
    ? {
        id: nanoid(),
        title: seed.title,
        identity: `${provider}:${seed.id}`,
        data: { ...data, chat: [] },
      }
    : general
  if (seed) threads.push(home)
  else general.data = { ...data, chat: [] }
  let pending: ChatMsg[] = []
  for (const raw of data.chat ?? []) {
    const message = withGraphRefs(raw)
    if (message.role === 'user') {
      pending.push(message)
      continue
    }
    let target = home
    if (message.graph) {
      const stamp = message.graph
      const backend = stamp.provider ?? provider
      const identity = `${backend}:${stamp.seedId}`
      target = threads.find((item) => item.identity === identity) ?? {
        id: nanoid(),
        title: stamp.seedTitle,
        identity,
        data: {
          chat: [],
          layout: data.layout,
          provider: backend,
          graph_ref: { seed: { id: stamp.seedId, title: stamp.seedTitle }, seed_ref: stamp.seedId },
        },
      }
      if (!threads.includes(target)) threads.push(target)
    }
    target.data.chat.push(...pending, message)
    pending = []
  }
  home.data.chat.push(...pending)
  const lecture = restoredLectureTurn(data)
  if (lecture) home.data.chat.push(lecture)
  return { id: saved.id, title: saved.name, threads, activeThreadId: home.id, revision: 0 }
}

/** Save all threads from one immutable state snapshot, never from a later active canvas.
 * @param state Store snapshot taken before awaiting anything.
 * @param record Exploration to serialize.
 * @returns Versioned parent with the existing session payload in each thread.
 */
export function explorationBody(
  state: {
    workspace: WorkspaceState
    transcript: TranscriptState
    explorations: ExplorationsState
  },
  record: ExplorationRecord,
): SaveSessionBody {
  const threads = record.threads.map((thread) => {
    const conversation = state.transcript.byKey[thread.id]
    const active = state.transcript.activeKey === thread.id
    const workspace = active ? state.workspace : thread.workspace
    let data: SessionData = workspace
      ? buildSaveBody(
          { workspace, transcript: { ...state.transcript, activeKey: thread.id } },
          thread.title,
        )
      : { ...thread.data, chat: conversation?.chat ?? thread.data.chat }
    // A failed rebuild must never erase the only saved seed reference.
    if (!data.graph_ref && thread.data.graph_ref)
      data = { ...data, graph_ref: thread.data.graph_ref }
    const pending = conversation?.pendingDiscoveries
    if (pending?.nodes.length)
      data = {
        ...data,
        discovered_nodes: [...(data.discovered_nodes ?? []), ...pending.nodes],
        discovered_edges: [...(data.discovered_edges ?? []), ...pending.edges],
      }
    const { workspace: _workspace, ...metadata } = thread
    return { ...metadata, data }
  })
  return {
    id: record.id,
    name: record.title,
    layout: 'timeline',
    chat: [],
    exploration: {
      version: 1,
      activeThreadId: record.activeThreadId,
      threads,
      summary: threads
        .filter((thread) => thread.summary)
        .map((thread) => `${thread.title}: ${thread.summary}`)
        .join('\n\n'),
    },
  }
}
