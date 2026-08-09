/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The grounding line: turning observed provenance counts into what the
 * transcript tells the student. The cases that matter are the honest ones —
 * an answer that cited nothing must say so, and "it looked and found nothing"
 * must not read the same as "it never looked".
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
    kind: 'answered',
    had_library: true,
    searches: 0,
    passages: 0,
    paper_searches: 0,
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

  it('singularizes a lone paper but not the sources collection', () => {
    expect(provenanceLine(provenance({ searches: 1, cited_sources: 1 }))).toBe(
      'grounded in 1 of your sources',
    )
    expect(provenanceLine(provenance({ cited_papers: 1 }))).toBe('grounded in 1 paper')
  })

  it('says nothing for a pleasantry', () => {
    expect(provenanceLine(provenance({ kind: 'conversational' }))).toBeNull()
  })

  it('admits an answer that nothing was searched for', () => {
    // No library in scope and no literature search: pure recall, and the
    // student should be told rather than left to assume it was grounded.
    expect(provenanceLine(provenance({ had_library: false }))).toBe(
      'answered from background knowledge — nothing was searched',
    )
  })

  it('reports a library search that came up empty', () => {
    expect(provenanceLine(provenance({ searches: 1, passages: 0 }))).toBe(
      'searched your library (no matches), cited nothing — answered from background knowledge',
    )
  })

  it('reports a literature search that produced no citation', () => {
    // The case that was previously indistinguishable from pure recall: it
    // went to Semantic Scholar, then cited none of what it found.
    expect(provenanceLine(provenance({ had_library: false, paper_searches: 2 }))).toBe(
      'searched the literature, cited nothing — answered from background knowledge',
    )
  })

  it('reports both when it looked in both and cited neither', () => {
    expect(provenanceLine(provenance({ searches: 1, passages: 4, paper_searches: 1 }))).toBe(
      'searched your library and the literature, cited nothing — answered from background knowledge',
    )
  })
})
