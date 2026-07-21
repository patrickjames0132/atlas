/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * A remark plugin that turns inline citation markers — `[7]` — in answer prose
 * into a custom `citeref` element the Markdown renderer maps to a clickable
 * chip. It only rewrites the marker's shape; whether a given `[n]` actually
 * resolves to a paper (and so becomes clickable) is decided at render time from
 * the answer's `refs` map. Runs on mdast text nodes, so markers inside inline
 * code or math (which parse as other node types) are left untouched.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { Root, Text } from 'mdast'
import type { Parent } from 'unist'
import { visit } from 'unist-util-visit'

/** A complete inline citation marker: a single index (`[12]`) or a combined
 *  list the model sometimes writes (`[14, 29]` / `[14 29]`). Group 1 holds the
 *  digits and separators; split it on `SEPARATOR` for the individual indices. */
const MARKER = /\[(\d+(?:[\s,]+\d+)*)\]/g
/** The separator between indices inside a combined marker (comma and/or space). */
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
      const replacements: (Text | CiteRefNode)[] = []
      let cursor = 0
      let match: RegExpExecArray | null
      while ((match = MARKER.exec(value)) !== null) {
        if (match.index > cursor) {
          replacements.push({ type: 'text', value: value.slice(cursor, match.index) })
        }
        // A combined marker (`[14, 29]`) becomes one chip per index — each a
        // separate clickable `[n]`, so every paper it cites stays reachable.
        for (const number of match[1].split(SEPARATOR)) {
          replacements.push({
            type: 'citeref',
            data: { hName: 'citeref', hProperties: { index: number } },
            children: [{ type: 'text', value: `[${number}]` }],
          })
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
