/**
 * The color legend under the graph. The two teacher-related entries only
 * appear once the agent has actually discovered papers mid-conversation.
 */

import { REL_COLOR } from './theme'
import './graph.css'

/** Props for {@link Legend}. */
export interface LegendProps {
  /** The teacher has pulled in at least one off-graph paper (dashed ring). */
  hasDiscovered: boolean
  /** At least one discovered paper came from an ungrounded topic search (pink). */
  hasSearchHits: boolean
}

/** Render the graph's color legend. */
export default function Legend({ hasDiscovered, hasSearchHits }: LegendProps) {
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
      <span>
        <i style={{ background: REL_COLOR.similar }} />
        Similar
      </span>
      {hasDiscovered && (
        <span>
          <i className="ring" />
          Discovered by teacher
        </span>
      )}
      {hasSearchHits && (
        <span>
          <i style={{ background: REL_COLOR.search }} />
          Found by search
        </span>
      )}
    </div>
  )
}
