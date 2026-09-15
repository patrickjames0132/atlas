/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Exploration navigation and serialized autosaves across background threads.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { useCallback, useEffect, useRef } from 'react'
import { getSession, saveSession, titleForConversation } from '../api'
import { useAppDispatch, useAppSelector, useAppStore } from '../store'
import {
  explorationOpened,
  explorationRemoved,
  explorationRenamed,
  newExploration,
  threadSummarized,
} from '../store/explorations'
import { explorationBody, migrateExploration } from '../store/threadPersistence'
import { loadGraph, errorSet, discoveryMerged } from '../store/workspace'
import { conversationHistory } from '../teacher/history'
import { conversationDropped, pendingDiscoveriesDrained } from '../store/transcript'
import { ExplorationWrites } from './saveQueue'
import { useSessions } from './useSessions'

/** Own exploration navigation, keeping writes ordered per parent record.
 * @returns Exploration list and navigation actions for the shell.
 */
export function useExplorations() {
  const store = useAppStore()
  const dispatch = useAppDispatch()
  const records = useAppSelector((state) => state.explorations)
  const transcript = useAppSelector((state) => state.transcript)
  const workspace = useAppSelector((state) => state.workspace)
  const { sessions, refresh, remove: removeRow, rename: renameRow } = useSessions()
  const baselines = useRef(new Map<string, string>())
  const writes = useRef<ExplorationWrites | null>(null)
  writes.current ??= new ExplorationWrites((body, unloading) =>
    saveSession(body, { keepalive: unloading }),
  )
  const naming = useRef(new Set<string>())
  const navigation = useRef(0)
  const summaryAttempts = useRef(new Map<string, string>())
  const contentBaselines = useRef(new Map<string, string>())

  useEffect(() => {
    for (const body of writes.current!.recover()) {
      void writes
        .current!.enqueue(body)
        .then(() => refresh())
        .catch(() => {})
    }
  }, [refresh])

  const flush = useCallback(
    (unloading = false) => {
      const state = store.getState()
      for (const record of Object.values(state.explorations.byId)) {
        let body = explorationBody(state, record)
        if (
          !body.exploration?.threads.some((thread) => thread.data.chat.length || thread.identity) &&
          record.revision === 0 &&
          !baselines.current.has(record.id)
        )
          continue
        const content = JSON.stringify([
          record.revision,
          body.exploration?.threads.map((thread) => [
            thread.id,
            thread.data.chat,
            thread.data.discovered_nodes,
            thread.data.discovered_edges,
            thread.data.selectedNodeIds,
          ]),
        ])
        if (contentBaselines.current.get(record.id) === content) continue
        contentBaselines.current.set(record.id, content)
        const serialized = JSON.stringify(body)
        if (baselines.current.get(record.id) === serialized) continue
        baselines.current.set(record.id, serialized)
        // Naming is independent of saving: a slow model must never hold the
        // only copy of a completed answer in a pending Promise.
        if (body.name === 'Untitled exploration') {
          const turns = body.exploration!.threads.flatMap((thread) => thread.data.chat)
          const first =
            turns.find((turn) => turn.role === 'user')?.text ||
            record.threads.find((thread) => thread.identity)?.title ||
            'Untitled exploration'
          body = { ...body, name: first.slice(0, 80) }
          if (!unloading && !naming.current.has(record.id)) {
            naming.current.add(record.id)
            void titleForConversation(turns.slice(0, 4).map((turn) => turn.text))
              .then((title) => {
                if (
                  store.getState().explorations.byId[record.id]?.title === 'Untitled exploration'
                ) {
                  dispatch(
                    explorationRenamed({ id: record.id, title: title || first.slice(0, 80) }),
                  )
                }
              })
              .catch(() => {})
          }
        }
        void writes
          .current!.enqueue(body, unloading)
          .then(() => refresh())
          .catch(() => {
            baselines.current.delete(record.id)
            contentBaselines.current.delete(record.id)
          })
      }
    },
    [refresh, dispatch, store],
  )

  useEffect(() => {
    const timer = window.setTimeout(() => flush(), 1500)
    return () => window.clearTimeout(timer)
  }, [
    records,
    transcript,
    workspace.graph,
    workspace.discoveredNodes,
    workspace.layout,
    workspace.selectedNodeIds,
    flush,
  ])
  useEffect(() => {
    const hide = () => flush(true)
    const visibility = () => {
      if (document.visibilityState === 'hidden') hide()
    }
    window.addEventListener('pagehide', hide)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      window.removeEventListener('pagehide', hide)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [flush])

  useEffect(() => {
    for (const record of Object.values(records.byId))
      for (const thread of record.threads) {
        const conversation = transcript.byKey[thread.id]
        if (!conversation?.chat.length) {
          summaryAttempts.current.delete(thread.id)
          continue
        }
        if (conversation.running.length) continue
        const through = conversation.chat.length
        if (
          (thread.summarizedThrough ?? 0) >= through ||
          summaryAttempts.current.get(thread.id) === JSON.stringify(conversation.chat)
        )
          continue
        summaryAttempts.current.set(thread.id, JSON.stringify(conversation.chat))
        const turns = conversationHistory(conversation.chat).map(
          (turn) => `${turn.role}: ${turn.content}`,
        )
        if (!turns.length) continue
        void fetch('/api/sessions/summary', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ previous: thread.summary ?? '', turns }),
        })
          .then((response) => (response.ok ? response.json() : null))
          .then((result: { summary?: string } | null) => {
            if (
              result?.summary &&
              store.getState().transcript.byKey[thread.id]?.chat === conversation.chat
            ) {
              dispatch(
                threadSummarized({
                  explorationId: record.id,
                  id: thread.id,
                  summary: result.summary,
                  through,
                }),
              )
            }
          })
          .catch(() => {})
      }
  }, [records, transcript, dispatch, store])

  const open = useCallback(
    async (id: string) => {
      if (store.getState().explorations.activeId === id) return
      try {
        flush()
        const request = ++navigation.current
        const state = store.getState()
        const existing = state.explorations.byId[id]
        if (!existing) await writes.current!.idle(id)
        const record = existing ?? migrateExploration(await getSession(id))
        if (request !== navigation.current) return
        // Park the active canvas before replacing the parent exploration.
        const latest = store.getState()
        const current = latest.explorations.byId[latest.explorations.activeId]
        const parked = {
          ...current,
          threads: current.threads.map((thread) =>
            thread.id === latest.transcript.activeKey
              ? { ...thread, workspace: latest.workspace }
              : thread,
          ),
        }
        dispatch(explorationOpened(parked))
        dispatch(explorationOpened(record))
        if (!existing) {
          const body = explorationBody(store.getState(), record)
          baselines.current.set(id, JSON.stringify(body))
          contentBaselines.current.set(
            id,
            JSON.stringify([
              record.revision,
              body.exploration?.threads.map((thread) => [
                thread.id,
                thread.data.chat,
                thread.data.discovered_nodes,
                thread.data.discovered_edges,
                thread.data.selectedNodeIds,
              ]),
            ]),
          )
          for (const thread of record.threads)
            summaryAttempts.current.set(thread.id, JSON.stringify(thread.data.chat))
        }
        const thread = record.threads.find((item) => item.id === record.activeThreadId)!
        const pending = store.getState().transcript.byKey[thread.id]?.pendingDiscoveries
        if (pending?.nodes.length && store.getState().workspace.graph) {
          dispatch(discoveryMerged(pending))
          dispatch(pendingDiscoveriesDrained(thread.id))
        }
        if (thread.identity && !thread.workspace?.graph && thread.data.graph_ref) {
          await dispatch(
            loadGraph({ seed: thread.data.graph_ref.seed_ref, provider: thread.data.provider }),
          )
        }
      } catch (error) {
        dispatch(errorSet(error instanceof Error ? error.message : 'Could not open exploration'))
      }
    },
    [dispatch, flush, store],
  )
  const create = useCallback(() => {
    flush()
    ++navigation.current
    const state = store.getState()
    const current = state.explorations.byId[state.explorations.activeId]
    dispatch(
      explorationOpened({
        ...current,
        threads: current.threads.map((thread) =>
          thread.id === state.transcript.activeKey
            ? { ...thread, workspace: state.workspace }
            : thread,
        ),
      }),
    )
    dispatch(explorationOpened(newExploration()))
  }, [dispatch, flush, store])
  const remove = useCallback(
    async (id: string) => {
      const state = store.getState()
      const record = state.explorations.byId[id]
      dispatch(explorationRemoved(id))
      for (const thread of record?.threads ?? []) dispatch(conversationDropped(thread.id))
      if (state.explorations.activeId === id) dispatch(explorationOpened(newExploration()))
      await writes.current!.remove(id)
      await removeRow(id)
    },
    [removeRow, dispatch, store],
  )
  const rename = useCallback(
    async (id: string, title: string) => {
      dispatch(explorationRenamed({ id, title }))
      await writes.current!.idle(id)
      await renameRow(id, title)
    },
    [renameRow, dispatch],
  )
  const working = Object.values(records.byId)
    .filter((record) =>
      record.threads.some((thread) => transcript.byKey[thread.id]?.running.length),
    )
    .map((record) => record.id)
  return {
    sessions,
    activeId: records.activeId,
    open,
    create,
    remove,
    rename,
    working,
  }
}
