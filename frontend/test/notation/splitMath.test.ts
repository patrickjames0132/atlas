/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The math splitter: delimited LaTeX becomes math segments, prose (including
 * currency dollar signs and mid-stream unclosed delimiters) stays text.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { splitMath } from '../../src/notation/splitMath'

describe('splitMath', () => {
  it('returns one text segment when there is no math at all', () => {
    expect(splitMath('plain prose')).toEqual([{ kind: 'text', value: 'plain prose' }])
  })

  it('splits inline $…$ out of surrounding text', () => {
    expect(splitMath('loss $L_2$ here')).toEqual([
      { kind: 'text', value: 'loss ' },
      { kind: 'math', value: 'L_2', display: false },
      { kind: 'text', value: ' here' },
    ])
  })

  it('recognises display $$…$$ before inline $…$', () => {
    expect(splitMath('$$E = mc^2$$')).toEqual([{ kind: 'math', value: 'E = mc^2', display: true }])
  })

  it('recognises \\(…\\) inline and \\[…\\] display runs', () => {
    expect(splitMath('a \\(x\\) b \\[y\\] c')).toEqual([
      { kind: 'text', value: 'a ' },
      { kind: 'math', value: 'x', display: false },
      { kind: 'text', value: ' b ' },
      { kind: 'math', value: 'y', display: true },
      { kind: 'text', value: ' c' },
    ])
  })

  it('leaves currency alone — "costs $5 and $10" is prose, not math', () => {
    expect(splitMath('costs $5 and $10 today')).toEqual([
      { kind: 'text', value: 'costs $5 and $10 today' },
    ])
  })

  it('leaves an unclosed delimiter as text (mid-stream tolerance)', () => {
    expect(splitMath('so $x + y')).toEqual([{ kind: 'text', value: 'so $x + y' }])
  })

  it('does not auto-mathify bare plain text like CO2 or GPT4', () => {
    expect(splitMath('GPT4 beats CO2 in Section 2')).toEqual([
      { kind: 'text', value: 'GPT4 beats CO2 in Section 2' },
    ])
  })

  it('skips escaped \\$ inside a run instead of closing on it', () => {
    expect(splitMath('$a\\$b$')).toEqual([{ kind: 'math', value: 'a\\$b', display: false }])
  })
})
