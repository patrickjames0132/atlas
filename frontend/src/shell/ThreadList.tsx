/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Shared exploration and thread rows, with consistent rename/delete controls.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { useAppDispatch, useAppSelector } from '../store'
import { activateThread, deleteThread } from '../store/workspace'
import { threadRenamed } from '../store/explorations'
import SessionRow from './SessionRow'

/** Show only the active exploration's children using the shared rail controls.
 * @param explorationId Parent owning these threads.
 * @returns Thread navigation, or nothing for an inactive parent.
 */
export default function ThreadList({ explorationId }: { explorationId: string }) {
  const dispatch = useAppDispatch()
  const activeId = useAppSelector((state) => state.explorations.activeId)
  const record = useAppSelector((state) => state.explorations.byId[explorationId])
  const conversations = useAppSelector((state) => state.transcript.byKey)
  if (activeId !== explorationId || !record) return null
  return (
    <nav className="thread-list" aria-label={`Threads in ${record.title}`}>
      {record.threads.map((thread) => (
        <SessionRow
          key={thread.id}
          session={{ name: thread.title }}
          active={thread.id === record.activeThreadId}
          editable={!!thread.identity}
          working={!!conversations[thread.id]?.running.length}
          onOpen={() => void dispatch(activateThread(thread.id))}
          onRename={(title) => dispatch(threadRenamed({ id: thread.id, title }))}
          onDelete={() => void dispatch(deleteThread(thread.id))}
        />
      ))}
    </nav>
  )
}
