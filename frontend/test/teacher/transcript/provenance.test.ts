/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The grounding line: turning observed provenance counts into what the
 * transcript tells the student. The cases that matter are the honest ones —
 * "it looked and found nothing" must not read the same as "it never looked",
 * and an ungrounded answer must say so rather than stay silent.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { provenanceLine } from '../../../src/teacher/transcript/provenance'
import type { ProvenanceEvent } from '../../../src/api'

/** A provenance record with everything zeroed, for per-case overrides. */
function provenance(overrides: Partial<ProvenanceEvent> = {}): ProvenanceEvent {
  return {
    had_library: true,
    searches: 0,
    passages: 0,
    cited_sources: 0,
    cited_papers: 0,
    ...overrides,
  }
}

describe('provenanceLine', () => {
  it('names both worlds when an answer cites sources and papers', () => {
    expect(provenanceLine(provenance({ searches: 1, cited_sources: 2, cited_papers: 3 }))).toBe(
      'grounded in 2 of your sources + 3 papers',
    )
  })

  it('singularizes a lone source and a lone paper', () => {
    expect(provenanceLine(provenance({ searches: 1, cited_sources: 1 }))).toBe(
      'grounded in 1 of your sources',
    )
    expect(provenanceLine(provenance({ cited_papers: 1 }))).toBe('grounded in 1 paper')
  })

  it('distinguishes "looked and found nothing" from plain recall', () => {
    // These are very different things to tell a student, and the counts are
    // the only way to tell them apart.
    expect(provenanceLine(provenance({ searches: 1, passages: 0 }))).toBe(
      'nothing in your library matched — answered from background knowledge',
    )
    expect(provenanceLine(provenance({ searches: 1, passages: 4 }))).toBe(
      'answered from background knowledge',
    )
  })

  it('says nothing for a conversational turn', () => {
    // A greeting cited nothing and drew on nothing; labelling it would be noise.
    expect(provenanceLine(provenance({ had_library: true }))).toBeNull()
    expect(provenanceLine(provenance({ had_library: false }))).toBeNull()
  })

  it('still reports grounding when there was no library at all', () => {
    expect(provenanceLine(provenance({ had_library: false, cited_papers: 2 }))).toBe(
      'grounded in 2 papers',
    )
  })
})
