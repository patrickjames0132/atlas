/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention grammar, as pure functions: finding the mention being typed,
 * inserting a picked paper, and reading a finished message's mentions back out.
 *
 * All of it lives here rather than in the composer because these are the rules
 * that decide what a message *means* — whether it seeds the graph, grounds a
 * question, or goes to the scout — and rules that consequential should be
 * readable and testable without rendering a textarea.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { MentionPaper } from '../api'

/** The shortest query worth looking up — matches the backend's own floor, so
 *  the composer never fires a request the server will refuse to serve. */
export const MENTION_MIN_CHARS = 3

/** The mention the caret is currently inside, as found by {@link activeMention}. */
export interface ActiveMention {
  /** The text between the `@` and the caret. */
  query: string
  /** Index of the `@` itself, for splicing a pick in. */
  start: number
  /** Index just past the caret — where the replacement ends. */
  end: number
}

/**
 * The `@`-mention the caret sits inside, or null when it doesn't.
 *
 * A mention starts at an `@` that follows whitespace or begins the message —
 * so an email address or a handle mid-word never opens the dropdown — and runs
 * to the caret. A newline ends it: a mention is a phrase, not a paragraph.
 *
 * Note what is deliberately NOT bounded: the query may contain spaces. Paper
 * titles have spaces in them, and `@attention is all you need` has to be one
 * mention rather than five. The cost is that a mention has no closing
 * delimiter, so its end is wherever the caret is — which is exactly why this
 * is only used while typing, and {@link mentionsIn} reads a finished message a
 * different way.
 *
 * @param text  The full composer text.
 * @param caret The caret position (selectionStart).
 * @returns The active mention, or null.
 */
export function activeMention(text: string, caret: number): ActiveMention | null {
  const before = text.slice(0, caret)
  const at = before.lastIndexOf('@')
  if (at === -1) return null
  // `@` must open a word: start of message, or preceded by whitespace.
  if (at > 0 && !/\s/.test(before[at - 1])) return null
  const query = before.slice(at + 1)
  if (query.includes('\n')) return null
  return { query, start: at, end: caret }
}

/**
 * Splice a picked paper into the composer text, replacing the mention being
 * typed with `@<title>`.
 *
 * The inserted text is the paper's **full title**, not a truncation and not
 * its id. A title is what the reader recognises, and it is also the key
 * {@link mentionsIn} matches on, so shortening it would either lose the paper
 * or need a second, hidden identifier to survive.
 *
 * A trailing space is added so the reader can keep typing the sentence without
 * re-opening the dropdown on the mention they just resolved.
 *
 * @param text   The full composer text.
 * @param active The mention being replaced.
 * @param paper  The picked paper.
 * @returns The new text and where to put the caret.
 */
export function insertMention(
  text: string,
  active: ActiveMention,
  paper: MentionPaper,
): { text: string; caret: number } {
  const inserted = `@${paper.title} `
  return {
    text: text.slice(0, active.start) + inserted + text.slice(active.end),
    caret: active.start + inserted.length,
  }
}

/**
 * The resolved mentions still present in a message, in the order they appear.
 *
 * Resolution is by **exact substring**: a paper counts as mentioned when
 * `@<its title>` literally appears in the text. That is the whole mechanism,
 * and its failure mode is deliberate — edit the inserted title and the paper
 * quietly stops being a resolved mention, so the message is treated as if the
 * reader had typed those words themselves. The alternative (tracking offsets
 * through every edit) buys precision the composer doesn't need and breaks in
 * ways that are much harder to explain.
 *
 * @param text     The full composer text.
 * @param resolved Papers picked from the dropdown this draft, keyed by the
 *                 text that was inserted for them.
 * @returns The papers whose mention text survives in the message.
 */
export function mentionsIn(text: string, resolved: Map<string, MentionPaper>): MentionPaper[] {
  const found: { index: number; paper: MentionPaper }[] = []
  for (const [inserted, paper] of resolved) {
    const index = text.indexOf(inserted)
    if (index !== -1) found.push({ index, paper })
  }
  return found.sort((one, other) => one.index - other.index).map((entry) => entry.paper)
}

/** What a sent message turns out to be — see {@link readMessage}. */
export type MessageIntent =
  /** One resolved mention and nothing else: land on that exact paper. */
  | { kind: 'seed'; paper: MentionPaper }
  /** One unresolved `@phrase` and nothing else: find papers matching it. */
  | { kind: 'find'; query: string }
  /** A question. Any resolved mentions ride along as grounding. */
  | { kind: 'ask'; mentioned: MentionPaper[] }

/**
 * What a finished message is asking for.
 *
 * Three outcomes, and the rule between them is the one already shipped for a
 * pasted arXiv id: **a bare mention is a statement of intent, a mention inside
 * a sentence is context.**
 *
 * - `@<a paper you picked>` alone → `seed`. You named one paper and nothing
 *   else; land on it. (The `ID_RE` path does the same for a pasted id, and
 *   still runs first — it needs no lookup at all.)
 * - `@<words that resolved to nothing>` alone → `find`. You asked for papers
 *   matching a phrase, which is what the scout is for. This is the fallback
 *   that makes the dropdown safe to keep cheap: a paper the cache has never
 *   seen is still reachable, just after sending rather than before.
 * - anything else → `ask`. The researcher answers, and any resolved mentions
 *   are attached as grounding so it can read and cite them without the graph
 *   you're looking at being thrown away. An *unresolved* `@phrase` inside a
 *   question is simply part of the question — the researcher has its own paper
 *   search and will use it if the answer needs one.
 *
 * @param text     The trimmed composer text.
 * @param resolved Papers picked from the dropdown this draft.
 * @returns What to do with the message.
 */
export function readMessage(text: string, resolved: Map<string, MentionPaper>): MessageIntent {
  const message = text.trim()
  const mentioned = mentionsIn(message, resolved)
  // A bare resolved mention: the message is nothing but `@<title>`.
  for (const paper of mentioned) {
    if (message === `@${paper.title}`) return { kind: 'seed', paper }
  }
  if (mentioned.length === 0 && message.startsWith('@')) {
    const query = message.slice(1).trim()
    if (query.length >= MENTION_MIN_CHARS && !query.includes('\n')) {
      return { kind: 'find', query }
    }
  }
  return { kind: 'ask', mentioned }
}
