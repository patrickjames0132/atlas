/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Turn an answer's observed provenance counts into the one line the
 * transcript shows under it — what the answer drew on, or the plain
 * admission that nothing grounded it.
 *
 * The backend ships facts rather than a verdict (it watched the searches
 * happen and counted the citations; it does not label them), so the wording
 * lives here, where it can change without touching the agent. The rule it
 * encodes: say what the answer *drew on*, and never imply grounding that
 * isn't there. Atlas grounds answers; when it can't, the honest thing is to
 * say so and let the student take the question elsewhere.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { ProvenanceEvent } from '../../api'

/**
 * The grounding line for one answer, or null for a turn with nothing to
 * attribute (a greeting asserts nothing, so labelling it would be noise).
 *
 * @param provenance The answer's observed provenance counts.
 * @returns The line to render, or null to render nothing.
 */
export function provenanceLine(provenance: ProvenanceEvent): string | null {
  const { kind, had_library, searches, passages, paper_searches, cited_sources, cited_papers } =
    provenance

  const drew: string[] = []
  if (cited_sources > 0) {
    // No singularization here: the plural belongs to "your sources" (the
    // collection being drawn from), not to the count — "1 of your source"
    // would be wrong.
    drew.push(`${cited_sources} of your sources`)
  }
  if (cited_papers > 0) {
    drew.push(`${cited_papers} paper${cited_papers > 1 ? 's' : ''}`)
  }
  if (drew.length > 0) return `grounded in ${drew.join(' + ')}`

  if (kind === 'conversational') return null

  // Everything past here is a real answer that cited nothing, and every one
  // of those says where it came from. What varies is how much looking went
  // into establishing there was nothing to cite — which is the part a student
  // needs to judge the answer.
  const looked: string[] = []
  if (had_library && searches > 0)
    looked.push(passages > 0 ? 'your library' : 'your library (no matches)')
  if (paper_searches > 0) looked.push('the literature')
  if (looked.length === 0) return 'answered from background knowledge — nothing was searched'
  return `searched ${looked.join(' and ')}, cited nothing — answered from background knowledge`
}
