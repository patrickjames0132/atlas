/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Money is not math. `prepareMath` makes `splitMath`'s verdict binding on
 * remark-math, which pairs dollars far more eagerly than the CommonMark
 * boundary rules do — the bug being pinned here is an answer whose "$3.77
 * billion … $1.8 billion" became one inline formula spanning the prose, the
 * URL and the punctuation between them.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { prepareMath } from '../../src/notation/prepareMath'

describe('prepareMath', () => {
  it('escapes the currency dollars that turned a paragraph into a formula', () => {
    const answer =
      'Quantum companies raised $3.77 billion in equity in the first nine months of 2025, ' +
      'up from $1.8 billion in 2024.'
    const prepared = prepareMath(answer)

    expect(prepared).toContain('\\$3.77 billion')
    expect(prepared).toContain('\\$1.8 billion')
    // No live dollar is left to open a run.
    expect(prepared.match(/(^|[^\\])\$/)).toBeNull()
  })

  it('leaves genuine inline and display math in its delimiters', () => {
    expect(prepareMath('The loss $L = \\sum_i x_i$ falls.')).toBe(
      'The loss $L = \\sum_i x_i$ falls.',
    )
    expect(prepareMath('$$e^{i\\pi} + 1 = 0$$')).toBe('$$e^{i\\pi} + 1 = 0$$')
  })

  it('rewrites the LaTeX forms remark-math ignores into dollars', () => {
    expect(prepareMath('with \\(d = 7\\) rounds')).toBe('with $d = 7$ rounds')
    expect(prepareMath('\\[x = y\\]')).toBe('$$x = y$$')
  })

  it('keeps its hands off code, where a dollar is a dollar', () => {
    expect(prepareMath('Run `echo $HOME` first.')).toBe('Run `echo $HOME` first.')
    expect(prepareMath('```sh\nexport PATH=$HOME/bin\n```')).toBe(
      '```sh\nexport PATH=$HOME/bin\n```',
    )
    // An unterminated fence mid-stream must not leak its body into the prose
    // path either.
    expect(prepareMath('```sh\ncost=$5')).toBe('```sh\ncost=$5')
  })

  it('does not double-escape a dollar the agent escaped itself', () => {
    expect(prepareMath('costs \\$5')).toBe('costs \\$5')
  })

  it('tolerates a half-written formula mid-stream', () => {
    // Still typing: no closer yet, so it is text — and text gets escaped,
    // which the next token's arrival simply re-decides.
    expect(prepareMath('the loss $L = ')).toBe('the loss \\$L = ')
  })
})
