/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * `@`-mention lookup: papers matching a partial title, for the composer's
 * as-you-type suggestions.
 *
 * The deliberate opposite of `search.ts` next door. That one runs the paper
 * scout — an agent that writes its own queries and reasons about what came
 * back — and takes seconds. This is a plain GET that runs on every few
 * keystrokes: no model, no streaming, no prose.
 *
 * **Two calls, not one**, because the two sources behind it cost wildly
 * different amounts. The cache-only call scans the reader's cached snapshots
 * and nothing else — free, offline, milliseconds, plain JSON — so the composer
 * fires it on every keystroke. The full call adds a day-cached provider search
 * and, for a nickname, a model resolve; it fires only when the reader pauses,
 * and it **streams**, so the dropdown can say which of those three phases it
 * is waiting on rather than "Searching…" for all of them. Asking one blocking
 * endpoint for both (as this did when it shipped) meant the free half bought
 * nothing: the response still waited on the provider. See `routes/search.py`'s
 * `api_mentions`.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { readSSE } from './sse'
import type { Provider } from './graph'

/**
 * One suggestion row: the paper, trimmed to what the row shows plus the ids
 * the composer needs to attach it.
 *
 * `venue` is the field the ordinary search list has no use for and this one
 * does — two papers with near-identical titles are told apart by where they
 * were published, and a reader picking from a dropdown has to make that call
 * before they can see anything else about either.
 */
export interface MentionPaper {
  id: string
  arxiv_id: string | null
  title: string
  authors?: string | null
  venue?: string | null
  year?: number | null
  citation_count?: number | null
  url?: string | null
}

/** The cache-only lookup's answer. `partial` marks it as provisional — a
 *  fuller, relevance-ranked list is still coming, so an empty one must not be
 *  read as "no such paper". */
export interface MentionResult {
  papers: MentionPaper[]
  partial: boolean
}

/**
 * Ask the cache what matches `query`. Free, offline, and fired on every
 * keystroke.
 *
 * Resolves to an empty list rather than throwing on a failed request: this is
 * called while the reader is mid-sentence, and a dropdown that reports a
 * transport error is worse than one that shows nothing — the fallback for a
 * name we can't resolve is already there, in sending the message.
 *
 * @param query    The partial title typed after `@`. The backend ignores
 *                 anything shorter than three characters.
 * @param provider Which backend the graph is on, so the cache scanned is the
 *                 one whose ids the graph uses.
 * @param signal   Abort signal, so a keystroke supersedes the request in
 *                 flight instead of racing it.
 * @returns The cached candidates, marked provisional.
 */
export async function fetchCachedMentions(
  query: string,
  provider: Provider,
  signal?: AbortSignal,
): Promise<MentionResult> {
  const params = new URLSearchParams({ q: query, provider, source: 'local' })
  try {
    const res = await fetch(`/api/mentions?${params}`, { signal })
    if (!res.ok) return { papers: [], partial: true }
    const data = (await res.json()) as { papers?: MentionPaper[]; partial?: boolean }
    return { papers: data.papers ?? [], partial: data.partial ?? true }
  } catch {
    // Includes the abort, which is the common case and not a failure.
    return { papers: [], partial: true }
  }
}

/** Live callbacks for the full lookup, which streams its phases. */
export interface MentionSearchHandlers {
  /** A phase just started, in reader-facing words. Each label **supersedes**
   *  the last: the dropdown shows one live line, not a phase history, because
   *  a lookup that finishes in a second or two turns a history into noise. */
  onStep?: (label: string) => void
  /** The finished, relevance-ranked list. */
  onResult: (papers: MentionPaper[]) => void
  signal?: AbortSignal
}

/**
 * Run the full lookup: cache, then provider, then — for a nickname — a model
 * resolve, reporting each phase as it starts.
 *
 * Swallows failures for the same reason the cached call does. There is no
 * error handler: every phase server-side degrades to fewer papers rather than
 * failing, so the stream always ends in a result, and a transport failure
 * simply means no result arrives and the provisional list stands.
 *
 * @param query    The partial title typed after `@`.
 * @param provider Which backend to search — the one the graph is on, so a
 *                 picked paper's id is in the graph's own id space.
 * @param handlers Event handlers; see {@link MentionSearchHandlers}.
 */
export async function streamMentions(
  query: string,
  provider: Provider,
  handlers: MentionSearchHandlers,
): Promise<void> {
  const params = new URLSearchParams({ q: query, provider })
  try {
    const res = await fetch(`/api/mentions?${params}`, { signal: handlers.signal })
    await readSSE(res, (event, data) => {
      if (event === 'step') handlers.onStep?.((data as { label: string }).label)
      else if (event === 'result') handlers.onResult((data as { papers: MentionPaper[] }).papers)
    })
  } catch {
    // Including the abort. The provisional list stays on screen.
  }
}
