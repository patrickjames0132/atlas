/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Turn an answer's observed provenance counts into the one line the
 * transcript shows under it — "grounded in your sources", "from background
 * knowledge", and the honest cases in between.
 *
 * The backend deliberately ships facts rather than a verdict (it watched the
 * searches happen and counted the citations; it does not label them), so the
 * wording lives here, where it can change without touching the agent. The
 * rule it encodes: say what the answer *drew on*, and never imply grounding
 * that isn't there — an answer citing nothing is background knowledge, and
 * saying so plainly is the whole point of the feature.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { ProvenanceEvent } from '../../api'

/**
 * The grounding line for one answer, or null when there's nothing worth
 * saying (a conversational turn — a greeting cites nothing and drew on
 * nothing, and labelling it "background knowledge" would be noise).
 *
 * @param provenance The answer's observed provenance counts.
 * @returns The line to render, or null to render nothing.
 */
export function provenanceLine(provenance: ProvenanceEvent): string | null {
  const { had_library, searches, passages, cited_sources, cited_papers } = provenance

  // Nothing was consulted and nothing cited: either a conversational turn or
  // a pure-recall answer with no library to check against. Say nothing for
  // the former (searches === 0 && !had_library covers "no library at all").
  if (cited_sources === 0 && cited_papers === 0 && searches === 0) return null

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

  // It looked and cited nothing. Distinguish "your library had nothing on
  // this" from "it found passages but the answer leans on background
  // knowledge" — those are very different things to tell a student.
  if (had_library && searches > 0 && passages === 0) {
    return 'nothing in your library matched — answered from background knowledge'
  }
  return 'answered from background knowledge'
}
