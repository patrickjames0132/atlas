/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 * Description: Convert the durable transcript into completed model history.
 * Authors: Charles Patrick James <charles.patrick.james@gmail.com>
 */
import type { ChatMsg, HistoryTurn } from '../api'

/** Render one completed turn, including lecture prose.
 * @param message The saved or live transcript turn.
 * @returns Model history, or null for incomplete or empty turns.
 */
export function toHistoryTurn(message: ChatMsg): HistoryTurn | null {
  if (message.failed || message.unfinished) return null
  const content = (
    message.beats?.length
      ? message.beats.map((beat) => `${beat.heading}\n${beat.text}`).join('\n\n')
      : message.text
  )
    .replace(/[ \t]*<<FIG \d+>>\n?/g, '')
    .trim()
  return content ? { role: message.role, content } : null
}

/** Keep completed exchanges together so an abandoned question cannot leak in.
 * @param chat The thread transcript before the new request.
 * @returns Completed conversational history.
 */
export function conversationHistory(chat: ChatMsg[]): HistoryTurn[] {
  const history: HistoryTurn[] = []
  let question: HistoryTurn | null = null
  for (const message of chat) {
    const turn = toHistoryTurn(message)
    if (message.role === 'user') {
      question = turn
      continue
    }
    if (turn) {
      if (question) history.push(question)
      history.push(turn)
    }
    question = null
  }
  return history
}

/** Build a sibling index and attach only explicitly mentioned discussions.
 * @param state Current store, read before starting the turn.
 * @param question User message with optional @thread references.
 * @returns Labelled sibling context for the request.
 */
export function siblingContext(
  state: import('../store').RootState,
  question: string,
): import('../api').ThreadContext[] {
  const record = state.explorations.byId[state.explorations.activeId]
  return record.threads
    .filter((thread) => thread.id !== record.activeThreadId)
    .map((thread) => {
      const mentioned = question.includes(`@thread[${thread.title}]`)
      return {
        title: thread.title,
        summary: thread.summary ?? 'No summary available yet.',
        mentioned,
        history: mentioned
          ? conversationHistory(state.transcript.byKey[thread.id]?.chat ?? thread.data.chat).map(
              (turn) => ({ ...turn, content: turn.content.slice(0, 12000) }),
            )
          : undefined,
      }
    })
    .sort((left, right) => Number(right.mentioned) - Number(left.mentioned))
    .slice(0, 40)
}
