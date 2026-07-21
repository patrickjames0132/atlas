/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The citation remark plugin: `[n]` markers in mdast text nodes become
 * `citeref` elements; everything that isn't a plain-text marker is left
 * untouched (resolvability is the renderer's job, not the plugin's).
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { Paragraph, Root } from 'mdast'
import { remarkCite } from '../../../src/teacher/transcript/remarkCite'

/** A one-paragraph mdast tree around the given inline children. */
function makeTree(children: Paragraph['children']): Root {
  return { type: 'root', children: [{ type: 'paragraph', children }] }
}

/** Run the plugin's transformer over a tree and hand back its paragraph. */
function transform(tree: Root): Paragraph {
  remarkCite()(tree)
  return tree.children[0] as Paragraph
}

describe('remarkCite', () => {
  it('splits a text node around each [n] marker', () => {
    const paragraph = transform(makeTree([{ type: 'text', value: 'see [7] and [12].' }]))
    expect(paragraph.children.map((child) => child.type)).toEqual([
      'text',
      'citeref',
      'text',
      'citeref',
      'text',
    ])
    const [, first, , second] = paragraph.children as Array<{
      type: string
      data?: { hName?: string; hProperties?: { index?: string } }
      children?: Array<{ value?: string }>
    }>
    expect(first.data?.hName).toBe('citeref')
    expect(first.data?.hProperties?.index).toBe('7')
    expect(first.children?.[0]?.value).toBe('[7]')
    expect(second.data?.hProperties?.index).toBe('12')
  })

  it('splits a combined marker into one chip per index', () => {
    const paragraph = transform(makeTree([{ type: 'text', value: 'both [14, 29] agree' }]))
    expect(paragraph.children.map((child) => child.type)).toEqual([
      'text',
      'citeref',
      'citeref',
      'text',
    ])
    const [, first, second] = paragraph.children as Array<{
      data?: { hProperties?: { index?: string } }
      children?: Array<{ value?: string }>
    }>
    expect(first.data?.hProperties?.index).toBe('14')
    expect(first.children?.[0]?.value).toBe('[14]')
    expect(second.data?.hProperties?.index).toBe('29')
    expect(second.children?.[0]?.value).toBe('[29]')
  })

  it('leaves a marker-free text node exactly as it was', () => {
    const original = { type: 'text', value: 'no citations here' } as const
    const paragraph = transform(makeTree([{ ...original }]))
    expect(paragraph.children).toEqual([original])
  })

  it('ignores non-numeric brackets like [sic] or [a]', () => {
    const paragraph = transform(makeTree([{ type: 'text', value: 'quoted [sic] and [a]' }]))
    expect(paragraph.children).toEqual([{ type: 'text', value: 'quoted [sic] and [a]' }])
  })

  it('leaves markers inside inline code untouched (not a text node)', () => {
    const paragraph = transform(makeTree([{ type: 'inlineCode', value: 'array[1]' }]))
    expect(paragraph.children).toEqual([{ type: 'inlineCode', value: 'array[1]' }])
  })
})
