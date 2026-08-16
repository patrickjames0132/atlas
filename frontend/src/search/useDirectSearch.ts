/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Direct search from the chat bar: run the paper scout on its own and land
 * its result in the transcript as an ordinary answer turn.
 *
 * The shaping here is the whole module. The scout hands back raw node dicts,
 * a summary and the lookups it made; a transcript answer wants prose with
 * `[n]` markers, a `paperRefs` map behind them, and trace chips. Turning one
 * into the other is what buys the rest for free — `AnswerMarkdown` renders
 * it, a click reseeds the graph, and a saved session keeps it — with no
 * bespoke rendering anywhere.
 *
 * It drives the **same reducers a streamed answer does** (`turnStarted` →
 * `traceAdded` → `tokenAppended` → `paperRefsSet`) rather than landing
 * complete in one action. That is what makes it feel like the rest of the
 * app: the turn appears the instant you hit send, the transcript snaps to the
 * bottom, and the scout's lookups arrive as chips while it works. The first
 * build pushed the finished result in a single dispatch, and a search read as
 * a frozen screen for the several seconds it took.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useRef, useState } from 'react'
import { searchLive } from '../api'
import type { GraphNode, PaperRef, Provider, SearchOptions } from '../api'
import { useAppDispatch } from '../store'
import { answerSet, paperRefsSet, traceAdded, turnStarted } from '../store/transcript'

/** What {@link useDirectSearch} hands back to the chat bar. */
export interface DirectSearchApi {
  /** A direct search is in flight (the send button shows the same hopping
   *  dots an answer does — one bar, one busy state). */
  searching: boolean
  /** Run a direct search and push its result into the transcript. */
  runSearch: (query: string) => Promise<void>
}

/**
 * Render one found paper as a numbered markdown line.
 *
 * The `[n]` marker is what makes it clickable: `AnswerMarkdown` resolves the
 * marker against `paperRefs` and wires the click to reseeding the graph, so
 * the list is a picker without being written as one.
 *
 * @param paper   The found paper.
 * @param index   Its 1-based position in the result list.
 * @param instant This paper's own graph is already cached, so opening it
 *                costs no provider call — worth saying, since the whole
 *                point of the cached list is that you can act on it now.
 * @returns The markdown line.
 */
function paperLine(paper: GraphNode, index: number, instant: boolean): string {
  const year = paper.year ?? 'n.d.'
  const authors = paper.authors ? ` · ${paper.authors}` : ''
  const citations =
    paper.citation_count != null ? ` · ${paper.citation_count.toLocaleString()} citations` : ''
  // A truthful, specific promise: this paper's own graph is already on disk
  // and unexpired, so opening it costs no provider call at all. Not "we've
  // seen this paper" — that would be true of every cached hit and useful
  // about none of them.
  const badge = instant ? ' · ⚡ opens instantly' : ''
  return `[${index}] **${paper.title}**  \n${year}${authors}${citations}${badge}`
}

/**
 * The `[n]` → paper map behind the markers, so each one is clickable.
 *
 * @param papers   The papers the scout found, in its order.
 * @param provider The backend that minted these ids — carried onto every ref
 *                 so a click builds under the provider that found the paper,
 *                 not whatever the dropdown has since been switched to.
 * @returns The refs map, keyed by 1-based position.
 */
function buildRefs(papers: GraphNode[], provider: Provider): Record<string, PaperRef> {
  const paperRefs: Record<string, PaperRef> = {}
  papers.forEach((paper, position) => {
    paperRefs[String(position + 1)] = {
      node_id: paper.id,
      title: paper.title,
      url: paper.url ?? '',
      provider,
    }
  })
  return paperRefs
}

/**
 * The answer prose for a search: a lead line, then the numbered list.
 *
 * The lead comes first because a negative result ("nothing indexed after
 * 2021") is the most useful thing on screen when the list is short — it
 * explains the short list rather than leaving the reader to wonder.
 *
 * @param papers  The papers found, in order.
 * @param lead    The line above the list — the scout's own summary once it has
 *                one, or the provisional note over the cached hits.
 * @param instant Ids whose graph is already cached, so they open with no
 *                provider call. Carried across the swap: the scout's list
 *                usually contains the same papers, and the badge shouldn't
 *                blink out just because a different code path rendered them.
 * @returns The markdown body.
 */
function buildText(papers: GraphNode[], lead: string, instant: Set<string>): string {
  const body = papers
    .map((paper, position) => paperLine(paper, position + 1, instant.has(paper.id)))
    .join('\n\n')
  return [lead, body].filter(Boolean).join('\n\n')
}

/** What sits above the cache's instant list, until the scout supersedes it.
 *  Says plainly that these came from disk and that the real search is still
 *  running — a list that looked final would make the swap read as a glitch. */
const CACHED_LEAD =
  '*From graphs you have already loaded \u2014 click any of these now, or wait for the full search\u2026*'

/** What sits above the list while the scout is still adding to it. */
const SEARCHING_LEAD = '*Searching\u2026*'

/**
 * Own the direct-search path: request, shape, dispatch.
 *
 * @param provider The selected backend — searched, and stamped onto each ref.
 * @param options  The chat bar's filters (binding server-side).
 * @param onError  Surface a failure message (or clear one with null).
 * @returns The in-flight flag and the runner (see {@link DirectSearchApi}).
 */
export function useDirectSearch(
  provider: Provider,
  options: SearchOptions,
  onError: (message: string | null) => void,
): DirectSearchApi {
  const dispatch = useAppDispatch()
  const [searching, setSearching] = useState(false)
  const ctrl = useRef<AbortController | null>(null)

  const runSearch = useCallback(
    async (query: string) => {
      ctrl.current?.abort() // a new search supersedes one still running
      const controller = new AbortController()
      ctrl.current = controller
      setSearching(true)
      onError(null)
      // Which papers open with no provider call, learned from the cached frame
      // and kept for the final render.
      const instant = new Set<string>()
      // The list as it grows, cached hits first, then each lookup's finds.
      // Deduped by id: the cache and the live search overlap constantly.
      const found: GraphNode[] = []
      // Open the turn FIRST: the question appears the moment you hit send and
      // the transcript scrolls to it, exactly as asking does. The assistant
      // bubble it opens is what the chips and the list then fill.
      dispatch(turnStarted(query))
      try {
        const result = await searchLive(query, 12, options, provider, {
          signal: controller.signal,
          // The cache answers in milliseconds. Painting it immediately means
          // the reader has something real to look at (and can click straight
          // through) while the scout is still on its first provider call.
          onCached: (papers) => {
            for (const paper of papers) {
              if (paper.has_graph) instant.add(paper.id)
              found.push(paper)
            }
            dispatch(answerSet(buildText(found, CACHED_LEAD, instant)))
            dispatch(paperRefsSet(buildRefs(found, provider)))
          },
          onTrace: (trace) => dispatch(traceAdded(trace)),
          // Each productive lookup appends. The scout works in batches, so
          // this is what makes the list grow as it goes instead of landing
          // whole at the end — the difference between watching a search and
          // watching a blank panel.
          onPapers: (papers) => {
            for (const paper of papers) {
              if (!found.some((seen) => seen.id === paper.id)) found.push(paper)
            }
            dispatch(answerSet(buildText(found, SEARCHING_LEAD, instant)))
            dispatch(paperRefsSet(buildRefs(found, provider)))
          },
        })
        // answerSet, not tokenAppended: this REPLACES the provisional list
        // rather than continuing it, or the cached papers would appear twice.
        dispatch(answerSet(buildText(result.papers, result.summary, instant)))
        dispatch(paperRefsSet(buildRefs(result.papers, provider)))
      } catch (error) {
        if (controller.signal.aborted) return // superseded: stay quiet
        // Only a genuine break reaches here — the scout degrades internally,
        // so a rate-limited provider arrives as a normal result whose summary
        // says so and renders like any other.
        onError(error instanceof Error ? error.message : String(error))
      } finally {
        if (!controller.signal.aborted) setSearching(false)
      }
    },
    [dispatch, onError, options, provider],
  )

  return { searching, runSearch }
}
