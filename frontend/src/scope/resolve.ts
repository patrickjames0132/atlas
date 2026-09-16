/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Which papers a turn is about. One resolver, one priority list, shared by
 * the lecturer and the researcher:
 *
 *   1. what the **message** asked for — "the references", "the seed", named
 *      papers, a period ("between 2016 and 2017");
 *   2. else the reader's **hand-picked selection** on the canvas;
 *   3. else what is **visible** — the papers passing the view filters.
 *
 * Until v7.24.0 that order existed only as the emergent behaviour of three
 * pieces of code, and two of them overlapped destructively: a message scope
 * replaced the selection and then released it to *nothing*, and the filters
 * silently beat the selection (a selected paper a later slider change hid
 * dropped out of scope with no signal). Now the list is this function, a
 * message scope *becomes* the selection and stays, like a pick made by hand
 * (`send` dispatches `nodeSelectionSet`), a selected paper stays in scope
 * whatever the filters do (the canvas draws it anyway, marked), and the
 * filters decide only the default. Resolved **once per turn**, by
 * `useConversation.send`, and the same snapshot goes to whichever agent
 * answers — so what the reader sees ringed and what the agent is handed
 * cannot drift apart.
 *
 * Pure functions, so the rule can be read and tested without a store.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { GraphNode, GraphResponse, LectureScope, RoutePaper } from '../api'

/** A period a message limited the turn to. Either end alone is open-ended. */
export interface YearWindow {
  from: number | null
  to: number | null
}

/** What the message asked for, as the router read it and the resolver
 *  finished it (ids for a `named` scope). */
export interface ScopeRequest {
  kind: LectureScope
  /** For `named`, the ids the name resolver found; ignored otherwise. */
  ids: string[]
  years: YearWindow
}

/** Where a turn's scope came from — the rung of the priority list that
 *  answered. */
export type ScopeSource = 'message' | 'selection' | 'visible'

/** A turn's scope, resolved against the graph as it stood when the turn
 *  started. */
export interface ResolvedScope {
  source: ScopeSource
  /** The papers in scope, in scope order. Empty with `source: 'message'` is
   *  the **empty-scope signal**: the message asked for papers this graph does
   *  not have, and the caller fails the turn rather than falling through to
   *  the next rung — an explicit scope that matches nothing must never
   *  quietly become "everything". */
  nodes: GraphNode[]
  /** The request, kept so a correction or retry can re-resolve the same
   *  ask against the graph as it stands then. Null when the message said
   *  nothing about which papers. */
  request: ScopeRequest | null
}

/** An empty period, for a message that named none. */
export const ANY_TIME: YearWindow = { from: null, to: null }

/**
 * Every paper on the graph, cut down to what a reader names a paper *by* — the
 * list the name resolver is shown. No abstracts: they would multiply the
 * prompt without adding a way to match.
 *
 * @param graph      The current graph.
 * @param discovered Papers the agent pulled in this session.
 * @returns The thin paper list, graph nodes first.
 */
export function routePapers(graph: GraphResponse | null, discovered: GraphNode[]): RoutePaper[] {
  return pool(graph, discovered).map((node) => ({
    id: node.id,
    title: node.title,
    year: node.year,
    authors: node.authors,
  }))
}

/**
 * Whether a request asks for anything at all — a kind other than the
 * reader's own scope, or a period.
 *
 * @param request The message's request, or null.
 * @returns True when the message chose the scope.
 */
export function requestsScope(request: ScopeRequest | null): request is ScopeRequest {
  return (
    request !== null &&
    (request.kind !== 'screen' || request.years.from !== null || request.years.to !== null)
  )
}

/**
 * The graph's papers plus the session's discoveries, deduped, graph first.
 *
 * @param graph      The current graph.
 * @param discovered Papers the agent pulled in this session.
 * @returns Every paper the workspace holds.
 */
function pool(graph: GraphResponse | null, discovered: GraphNode[]): GraphNode[] {
  const seen = new Set<string>()
  const papers: GraphNode[] = []
  for (const node of [...(graph?.nodes ?? []), ...discovered]) {
    if (seen.has(node.id)) continue
    seen.add(node.id)
    papers.push(node)
  }
  return papers
}

/**
 * Keep the papers inside a period. An undated paper never satisfies one:
 * placing it in a period would be a claim we cannot make (the same reason
 * Timeline hides undated papers).
 *
 * @param nodes The papers to filter.
 * @param years The period.
 * @returns The dated papers inside it.
 */
function inWindow(nodes: GraphNode[], years: YearWindow): GraphNode[] {
  if (years.from === null && years.to === null) return nodes
  return nodes.filter(
    (node) =>
      typeof node.year === 'number' &&
      (years.from === null || node.year >= years.from) &&
      (years.to === null || node.year <= years.to),
  )
}

/**
 * Which papers a turn is about — the priority list, applied.
 *
 * **Message** (`request` asks for something): the scope is read off the
 * whole graph, not the visible part, because a paper the filters hide is
 * exactly what the message should reach past — "the references" with the
 * references chip off. `references` / `citations` are the papers tagged with
 * that relation (the tag a paper is *coloured* by and the set its chip
 * toggles, so the word means the same said as clicked); `seed` is the seed
 * alone; `named` is the resolved ids in the order they were named, dropping
 * any the graph lacks. A period filters whichever of those the message
 * named. A period **alone** ("the papers between 2016 and 2017") names no
 * set, so it narrows the reader's existing context — the selection if they
 * have one, else the visible papers — rather than reaching past the filters:
 * a bare period is ambiguous about what it is a period *of*, and an
 * ambiguous ask preserves the context the reader already established.
 *
 * **Selection**: every hand-picked paper, whether or not a filter currently
 * hides it. The reader chose it; a slider dragged afterwards is a view
 * choice, not a retraction.
 *
 * **Visible**: the papers passing the view filters — the graph's own and any
 * discoveries the filters admit. A discovery the filters hide is out, like
 * any other paper: it stays in the workspace, it just isn't evidence for
 * this turn unless the reader selects or names it.
 *
 * @param request     What the message asked for, or null.
 * @param graph       The current graph.
 * @param discovered  Papers the agent pulled in this session.
 * @param visibleIds  The ids passing the view filters right now.
 * @param selectedIds The reader's hand-picked selection right now.
 * @returns The turn's scope.
 */
export function resolveScope(
  request: ScopeRequest | null,
  graph: GraphResponse | null,
  discovered: GraphNode[],
  visibleIds: string[],
  selectedIds: string[],
): ResolvedScope {
  const papers = pool(graph, discovered)
  const byId = new Map(papers.map((node) => [node.id, node]))
  const selected = [...new Set(selectedIds)].flatMap((id) => {
    const node = byId.get(id)
    return node ? [node] : []
  })
  const visible = new Set(visibleIds)
  const context = selected.length > 0 ? selected : papers.filter((node) => visible.has(node.id))
  if (!requestsScope(request)) {
    return {
      source: selected.length > 0 ? 'selection' : 'visible',
      nodes: context,
      request: null,
    }
  }
  let nodes: GraphNode[]
  switch (request.kind) {
    case 'named':
      nodes = [...new Set(request.ids)].flatMap((id) => {
        const node = byId.get(id)
        return node ? [node] : []
      })
      break
    case 'seed':
      nodes = papers.filter((node) => node.is_seed)
      break
    case 'references':
    case 'citations': {
      const relation = request.kind === 'references' ? 'reference' : 'citation'
      nodes = papers.filter((node) => !node.is_seed && node.rels.includes(relation))
      break
    }
    default:
      nodes = context
  }
  return { source: 'message', nodes: inWindow(nodes, request.years), request }
}

/**
 * What a turn whose message reached for papers the graph lacks is told.
 *
 * @param request The request that came up empty.
 * @returns The failure line for the turn.
 */
export function emptyScopeMessage(request: ScopeRequest): string {
  const { years } = request
  const period =
    years.from !== null && years.to !== null
      ? years.from === years.to
        ? `from ${years.from}`
        : `from ${years.from}–${years.to}`
      : years.from !== null
        ? `from ${years.from} on`
        : years.to !== null
          ? `up to ${years.to}`
          : ''
  if (period) {
    const subject = {
      screen: 'papers in your current scope',
      references: 'references',
      citations: 'citations',
      seed: 'seed paper',
      named: 'papers',
    }[request.kind]
    const hint = request.kind === 'screen' ? ' — widen the year filter, or say which papers.' : '.'
    return `This graph has no ${subject} ${period}${hint}`
  }
  switch (request.kind) {
    case 'references':
      return 'This graph has no references to lecture on.'
    case 'citations':
      return 'This graph has no citations to lecture on.'
    case 'seed':
      return 'This graph has no seed paper.'
    default:
      return 'None of the papers you named are on this graph — @-mention one to open it, or expand the graph to bring it in.'
  }
}

/**
 * How a turn's scope reads in the transcript — "the references, 2010–2019"
 * — for the line that says what a turn was scoped to. Null for the visible
 * default, which is not worth a line: the reader is looking at it.
 *
 * @param scope The turn's scope, as stamped on it.
 * @returns The phrase, or null when nothing needs saying.
 */
export function describeScope(scope: {
  source: ScopeSource
  kind?: LectureScope
  years?: YearWindow
  nodes: number
}): string | null {
  const count = `${scope.nodes} paper${scope.nodes === 1 ? '' : 's'}`
  if (scope.source === 'selection')
    return `your ${scope.nodes} selected paper${scope.nodes === 1 ? '' : 's'}`
  if (scope.source !== 'message') return null
  const subject = {
    screen: null,
    references: 'the references',
    citations: 'the citations',
    seed: 'the seed paper',
    named: scope.nodes === 1 ? 'the paper you named' : 'the papers you named',
  }[scope.kind ?? 'screen']
  const years = scope.years ?? ANY_TIME
  const period =
    years.from !== null && years.to !== null
      ? years.from === years.to
        ? `${years.from}`
        : `${years.from}–${years.to}`
      : years.from !== null
        ? `${years.from} on`
        : years.to !== null
          ? `up to ${years.to}`
          : null
  const parts = [subject, period].filter((part): part is string => part !== null)
  if (parts.length === 0) return null
  return `${parts.join(', ')} · ${count}`
}
