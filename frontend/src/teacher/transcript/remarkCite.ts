/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * A remark plugin that turns inline citation markers in answer prose into
 * custom elements the Markdown renderer maps to chips. Two flavors, because
 * an answer can cite both worlds at once:
 *   • `[7]` — a graph paper → `citeref`, clickable when it resolves.
 *   • `[S2, p.460]` — a passage from the student's own library → `sourceref`,
 *     rendered as that source's real title and page.
 * It only rewrites the markers' shape; whether a given one resolves (and so
 * becomes a chip rather than bare text) is decided at render time from the
 * answer's `refs` / `sourceRefs` maps. Runs on mdast text nodes, so markers
 * inside inline code or math (which parse as other node types) are untouched.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { Root, Text } from 'mdast'
import type { Parent } from 'unist'
import { visit } from 'unist-util-visit'

/** Either flavor of inline citation marker, matched in one pass so neither can
 *  swallow the other. Alternative 1 is a library citation — `[S2, p.460]`, or
 *  `[S2]` for a source with no pages — putting its index in group 1 and its
 *  page (when cited) in group 2. Alternative 2 is a paper citation: a single
 *  index (`[12]`) or a combined list the model sometimes writes (`[14, 29]` /
 *  `[14 29]`), whose digits and separators land in group 3.
 *  Kept in step with the backend's `_SOURCE_MARKER` / `_REF_MARKER`. */
const MARKER = /\[S(\d+)(?:,?\s*p\.\s*(\d+))?\]|\[(\d+(?:[\s,]+\d+)*)\]/gi
/** The separator between indices inside a combined paper marker (comma and/or space). */
const SEPARATOR = /[\s,]+/

/**
 * A synthetic inline node. `data.hName` / `data.hProperties` make the
 * mdast→hast step emit `<citeref index="n">[n]</citeref>`, which the renderer's
 * `components.citeref` override then turns into a chip.
 */
interface CiteRefNode {
  type: 'citeref'
  data: { hName: 'citeref'; hProperties: { index: string } }
  children: Text[]
}

/**
 * The library-citation counterpart of {@link CiteRefNode}, emitting
 * `<sourceref index="n" page="460">`. The page rides on the element rather
 * than in the graphRefs map, so the map stays page-free and can arrive before the
 * prose does (see the backend's `prompts.source_refs`).
 */
interface SourceRefNode {
  type: 'sourceref'
  data: { hName: 'sourceref'; hProperties: { index: string; page?: string } }
  children: Text[]
}

/**
 * The remark plugin: rewrite `[n]` markers in text nodes into `citeref`
 * elements (see the module docstring).
 *
 * @returns The mdast transformer remark runs over each tree.
 */
export function remarkCite() {
  return (tree: Root): void => {
    visit(tree, 'text', (node: Text, index, parent: Parent | undefined) => {
      if (!parent || index === undefined) return
      const value = node.value
      MARKER.lastIndex = 0
      if (!MARKER.test(value)) return

      MARKER.lastIndex = 0
      const replacements: (Text | CiteRefNode | SourceRefNode)[] = []
      let cursor = 0
      let match: RegExpExecArray | null
      while ((match = MARKER.exec(value)) !== null) {
        if (match.index > cursor) {
          replacements.push({ type: 'text', value: value.slice(cursor, match.index) })
        }
        const [, sourceIndex, sourcePage, paperIndices] = match
        if (sourceIndex !== undefined) {
          // A library citation is always a single source, so no splitting —
          // the fallback text is the raw marker, matching how an unresolved
          // paper `[n]` degrades.
          replacements.push({
            type: 'sourceref',
            data: {
              hName: 'sourceref',
              hProperties: { index: sourceIndex, ...(sourcePage ? { page: sourcePage } : {}) },
            },
            children: [{ type: 'text', value: match[0] }],
          })
        } else {
          // A combined marker (`[14, 29]`) becomes one chip per index — each a
          // separate clickable `[n]`, so every paper it cites stays reachable.
          for (const number of paperIndices.split(SEPARATOR)) {
            replacements.push({
              type: 'citeref',
              data: { hName: 'citeref', hProperties: { index: number } },
              children: [{ type: 'text', value: `[${number}]` }],
            })
          }
        }
        cursor = match.index + match[0].length
      }
      if (cursor < value.length) {
        replacements.push({ type: 'text', value: value.slice(cursor) })
      }

      parent.children.splice(index, 1, ...(replacements as Parent['children']))
      // Resume after the nodes we just inserted (they hold no more markers).
      return index + replacements.length
    })
  }
}
