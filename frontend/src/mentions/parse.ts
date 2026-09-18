/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention grammar, as pure functions: finding the mention being typed,
 * inserting a pick (a paper or a sibling thread), and reading a finished
 * message's mentions back out.
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

/** The shortest query worth a *paper* lookup — matches the backend's own
 *  floor, so the composer never fires a request the server will refuse to
 *  serve. Threads are matched from the first character: they are a local
 *  list of a handful of titles, and cost nothing to filter. */
export const MENTION_MIN_CHARS = 3

/** A sibling discussion in the current exploration, as the dropdown offers it. */
export interface MentionThread {
  /** The thread's stable id — what the sent turn's `Context from` link navigates to. */
  id: string
  /** Its title, which is also the text the mention carries. */
  title: string
}

/** What a dropdown row stands for: a paper the assistant can read, or another
 *  discussion whose history the message should carry along. */
export type MentionChoice =
  | { kind: 'paper'; paper: MentionPaper }
  | { kind: 'thread'; thread: MentionThread }

/**
 * The sibling threads whose title contains the query, case-insensitively.
 *
 * A substring match rather than a fuzzy one: thread titles are short, the
 * reader named or watched them being named, and a list of five needs no
 * ranking. An empty query matches every thread, so `@` alone shows what can
 * be attached — the way the reader discovers that threads are mentionable
 * at all.
 *
 * @param threads The other threads in the current exploration.
 * @param query   The text typed after the `@`.
 * @returns The matching threads, in their exploration order.
 */
export function threadMatches(threads: MentionThread[], query: string): MentionThread[] {
  const needle = query.trim().toLowerCase()
  return threads.filter((thread) => thread.title.toLowerCase().includes(needle))
}

/** The mention the caret is currently inside, as found by {@link activeMention}. */
export interface ActiveMention {
  /** The text between the `@` and the caret. */
  query: string
  /** Index of the `@` itself, for splicing a pick in. */
  start: number
  /** Index just past the caret — where the replacement ends. */
  end: number
  /** Whether the mention is the whole message: nothing but whitespace before
   *  the `@` or after the caret. A bare mention is a statement of intent
   *  (see {@link readMessage}), so picking a paper into one can send it in
   *  the same keystroke. */
  whole: boolean
}

/** A closed thread reference: `@thread[` … `]`. The bracket is the delimiter
 *  a paper mention doesn't have, so a thread mention ends itself. */
const CLOSED_THREAD_RE = /^@thread\[[^\]\n]*\]/

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
 * What DOES end a mention is its completion. Once `@Attention Is All You
 * Need ` has been picked into the text, the sentence typed after it is a
 * sentence, not a longer query — without this rule the lookup kept running
 * on "Attention Is All You Need what does it say about" for every keystroke
 * of the question. So an `@` that opens a mention the draft has already
 * resolved (`completed`, the inserted texts) is not an active one, and
 * neither is a closed `@thread[…]`, whose bracket is its own delimiter.
 * Editing *inside* a completed mention reopens it, since the text before the
 * caret is then only a prefix of the completed one.
 *
 * @param text      The full composer text.
 * @param caret     The caret position (selectionStart).
 * @param completed The mention texts already picked into this draft.
 * @returns The active mention, or null.
 */
export function activeMention(
  text: string,
  caret: number,
  completed: Iterable<string> = [],
): ActiveMention | null {
  const before = text.slice(0, caret)
  const at = before.lastIndexOf('@')
  if (at === -1) return null
  // `@` must open a word: start of message, or preceded by whitespace.
  if (at > 0 && !/\s/.test(before[at - 1])) return null
  const fromAt = before.slice(at)
  if (CLOSED_THREAD_RE.test(fromAt)) return null
  for (const done of completed) {
    if (fromAt.startsWith(done)) return null
  }
  const query = fromAt.slice(1)
  if (query.includes('\n')) return null
  const whole = text.slice(0, at).trim() === '' && text.slice(caret).trim() === ''
  return { query, start: at, end: caret, whole }
}

/**
 * The text a pick puts in the message.
 *
 * A paper is `@<title>`: its **full title**, not a truncation and not its id.
 * A title is what the reader recognises, and it is also the key
 * {@link mentionsIn} matches on, so shortening it would either lose the paper
 * or need a second, hidden identifier to survive.
 *
 * A thread is `@thread[<title>]` — bracketed because a thread title is
 * arbitrary text ("PPO", "General") and the brackets are what tells the send
 * path (`teacher/history.ts`, `useConversation`'s `turnContextSet`) that the
 * words name a discussion to attach rather than a paper to look up.
 *
 * @param choice The pick.
 * @returns The mention text, without the trailing space.
 */
export function mentionText(choice: MentionChoice): string {
  return choice.kind === 'paper' ? `@${choice.paper.title}` : `@thread[${choice.thread.title}]`
}

/**
 * Splice a pick into the composer text, replacing the mention being typed
 * with its {@link mentionText}.
 *
 * A trailing space is added so the reader can keep typing the sentence without
 * re-opening the dropdown on the mention they just resolved.
 *
 * @param text   The full composer text.
 * @param active The mention being replaced.
 * @param choice The picked paper or thread.
 * @returns The new text and where to put the caret.
 */
export function insertMention(
  text: string,
  active: ActiveMention,
  choice: MentionChoice,
): { text: string; caret: number } {
  const inserted = `${mentionText(choice)} `
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
 *   search and will use it if the answer needs one. A thread mention
 *   (`@thread[…]`) always lands here too, even alone: it names a discussion
 *   to carry along, not a paper to find, so it must never reach the scout.
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
  if (mentioned.length === 0 && message.startsWith('@') && !message.includes('@thread[')) {
    const query = message.slice(1).trim()
    if (query.length >= MENTION_MIN_CHARS && !query.includes('\n')) {
      return { kind: 'find', query }
    }
  }
  return { kind: 'ask', mentioned }
}
