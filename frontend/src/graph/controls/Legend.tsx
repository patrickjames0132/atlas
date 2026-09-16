/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The color legend under the graph. The teacher-related entries only appear
 * when they apply: the dashed ring once the agent has discovered papers
 * mid-conversation, the dotted ring while a scoped paper is on screen that
 * the view filters would otherwise hide.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { REL_COLOR } from '../theme'
import '../graph.css'

/** Props for {@link Legend}. */
export interface LegendProps {
  /** The teacher has pulled in at least one off-graph paper (dashed ring). */
  hasDiscovered: boolean
  /** At least one scoped paper is drawn past the view filters (dotted ring). */
  hasGhosts: boolean
}

/**
 * Render the graph's color legend.
 *
 * @returns The legend row.
 */
export default function Legend({ hasDiscovered, hasGhosts }: LegendProps) {
  return (
    <div className="legend">
      <span>
        <i style={{ background: REL_COLOR.seed }} />
        Seed
      </span>
      <span>
        <i style={{ background: REL_COLOR.reference }} />
        References
      </span>
      <span>
        <i style={{ background: REL_COLOR.citation }} />
        Citations
      </span>
      {hasDiscovered && (
        <span>
          <i className="ring" />
          Discovered by teacher
        </span>
      )}
      {hasGhosts && (
        <span>
          <i className="ring ghost" />
          In scope, hidden by your filters
        </span>
      )}
    </div>
  )
}
