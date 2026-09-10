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
 * different amounts. `source: 'local'` scans the reader's cached snapshots and
 * nothing else — free, offline, milliseconds — so the composer fires it on
 * every keystroke. The full call adds a day-cached provider search and is the
 * one that waits, so it fires only when the reader pauses. Asking one blocking
 * endpoint for both (as this did when it shipped) meant the free half bought
 * nothing: the response still waited on the provider. See `routes/search.py`'s
 * `api_mentions`.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

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

/** One lookup's answer. `partial` marks the cache-only pass, whose list is
 *  provisional — a fuller, relevance-ranked one is still coming. */
export interface MentionResult {
  papers: MentionPaper[]
  partial: boolean
}

/**
 * Look up papers whose title matches `query`.
 *
 * Resolves to an empty list rather than throwing on a failed request: this is
 * called while the reader is mid-sentence, and a dropdown that reports a
 * transport error is worse than one that shows nothing — the fallback for a
 * name we can't resolve is already there, in sending the message.
 *
 * @param query    The partial title typed after `@`. The backend ignores
 *                 anything shorter than three characters.
 * @param provider Which backend to search — the one the graph is on, so a
 *                 picked paper's id is in the graph's own id space.
 * @param localOnly Ask only the cache: no provider call, no wait. What the
 *                 composer fires on every keystroke.
 * @param signal   Abort signal, so a keystroke supersedes the request in
 *                 flight instead of racing it.
 * @returns The candidates and whether the list is provisional.
 */
export async function fetchMentions(
  query: string,
  provider: Provider,
  localOnly = false,
  signal?: AbortSignal,
): Promise<MentionResult> {
  const params = new URLSearchParams({ q: query, provider })
  if (localOnly) params.set('source', 'local')
  try {
    const res = await fetch(`/api/mentions?${params}`, { signal })
    if (!res.ok) return { papers: [], partial: localOnly }
    const data = (await res.json()) as { papers?: MentionPaper[]; partial?: boolean }
    return { papers: data.papers ?? [], partial: data.partial ?? localOnly }
  } catch {
    // Includes the abort, which is the common case and not a failure.
    return { papers: [], partial: localOnly }
  }
}
