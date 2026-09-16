/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Turn a routed message's lecture scope into papers: which nodes "the
 * references", "the seed" or the papers a message named actually are on this
 * graph, and which of them the view filters currently hide.
 *
 * Pure functions, so the rule that decides what a lecture is about can be
 * read and tested without a store or a canvas. `useConversation`'s `send` is
 * the one caller: it applies the result to the canvas (`lectureScopeApplied`)
 * and hands the same nodes to the lecturer, so what the reader sees lit and
 * what gets narrated cannot drift apart.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { GraphNode, GraphResponse, LectureScope, RoutePaper } from '../api'

/** A scope resolved against the graph — see {@link scopeLecture}. */
export interface ScopedLecture {
  /** The papers the lecture is about, in scope order. Empty means the message
   *  pointed at papers this graph does not have. */
  nodes: GraphNode[]
  /** The subset of `nodes` the view filters currently hide — what has to be
   *  forced on screen for the lecture to narrate only visible papers. */
  hidden: string[]
}

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
  const seen = new Set<string>()
  const papers: RoutePaper[] = []
  for (const node of [...(graph?.nodes ?? []), ...discovered]) {
    if (seen.has(node.id)) continue
    seen.add(node.id)
    papers.push({ id: node.id, title: node.title, year: node.year, authors: node.authors })
  }
  return papers
}

/** A period a message limited the lecture to — see {@link scopeLecture}. */
export interface YearWindow {
  from: number | null
  to: number | null
}

/**
 * The papers a lecture scope names on this graph.
 *
 * `screen` with no year window returns null — the message said nothing about
 * which papers, so the scope is the reader's own (visible after their
 * filters, narrowed to their selection) and nothing on the canvas changes.
 * Every other request is read off the graph:
 *
 * - `references` / `citations` — every paper tagged with that relation, by
 *   the node's own `rels`. That is the tag the paper is *coloured* by and the
 *   set its chip toggles, so "the references" means the same thing said as it
 *   does clicked. (A satellite's references count, as they do for the chip;
 *   the v7.17.0 rule is that what the reader put on screen is narrated.)
 * - `seed` — the seed alone: the solo lecture, by name.
 * - `named` — the ids the resolver returned, in the order the message named
 *   them; an id the graph doesn't have is dropped.
 * - `screen` **with a year window** — "the papers between 2016 and 2017":
 *   the reader's hand-picked selection when they have one (an explicit
 *   choice the period narrows within), otherwise the whole graph — not the
 *   visible part of it, because a year the sliders currently exclude is
 *   exactly the case the message should reach past, like a hidden relation.
 *
 * A year window then filters whichever set that produced. An undated paper
 * never satisfies one: placing it in a period would be a claim we cannot
 * make (the same reason Timeline hides undated papers).
 *
 * The result's `nodes` can be empty — a graph with no citations yet, a named
 * paper that isn't here, a period nothing falls in — and the caller treats
 * that as a failed request rather than quietly lecturing on everything
 * instead.
 *
 * @param scope       The routed scope.
 * @param ids         For `named`, the resolved ids; ignored otherwise.
 * @param years       The period, if the message gave one.
 * @param graph       The current graph.
 * @param discovered  Papers the agent pulled in this session.
 * @param visibleIds  The ids surviving the view filter right now.
 * @param selectedIds The reader's hand-picked selection right now.
 * @returns The scoped papers and which of them are hidden, or null when the
 *          message left the scope to the reader.
 */
export function scopeLecture(
  scope: LectureScope,
  ids: string[],
  years: YearWindow,
  graph: GraphResponse | null,
  discovered: GraphNode[],
  visibleIds: string[],
  selectedIds: string[],
): ScopedLecture | null {
  const windowed = years.from !== null || years.to !== null
  if (!graph || (scope === 'screen' && !windowed)) return null
  const pool = new Map<string, GraphNode>()
  for (const node of [...graph.nodes, ...discovered]) {
    if (!pool.has(node.id)) pool.set(node.id, node)
  }
  let nodes: GraphNode[]
  if (scope === 'named') {
    nodes = [...new Set(ids)].flatMap((id) => {
      const node = pool.get(id)
      return node ? [node] : []
    })
  } else if (scope === 'seed') {
    nodes = [...pool.values()].filter((node) => node.is_seed)
  } else if (scope === 'screen') {
    const selected = new Set(selectedIds)
    nodes = [...pool.values()].filter((node) => selected.size === 0 || selected.has(node.id))
  } else {
    const relation = scope === 'references' ? 'reference' : 'citation'
    nodes = [...pool.values()].filter((node) => !node.is_seed && node.rels.includes(relation))
  }
  if (windowed) {
    nodes = nodes.filter(
      (node) =>
        typeof node.year === 'number' &&
        (years.from === null || node.year >= years.from) &&
        (years.to === null || node.year <= years.to),
    )
  }
  const visible = new Set(visibleIds)
  return { nodes, hidden: nodes.filter((node) => !visible.has(node.id)).map((node) => node.id) }
}
