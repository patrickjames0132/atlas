/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The color legend under the graph. The two teacher-related entries only
 * appear once the agent has actually discovered papers mid-conversation.
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
}

/**
 * Render the graph's color legend.
 *
 * @returns The legend row.
 */
export default function Legend({ hasDiscovered }: LegendProps) {
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
        Field Landmarks
      </span>
      <span>
        <i style={{ background: REL_COLOR.latest }} />
        Latest Publications
      </span>
      {hasDiscovered && (
        <span>
          <i className="ring" />
          Discovered by teacher
        </span>
      )}
    </div>
  )
}
