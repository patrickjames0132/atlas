/** The history lecture's backfill hops, shown above the beats as the story
 * traces a field back to its roots before narrating. */

import type { BackfillTrace } from '../../api'

export default function HistTrace({ trace }: { trace: BackfillTrace[] }) {
  if (trace.length === 0) return null
  return (
    <div className="chat-trace hist-trace">
      {trace.map((hop, index) => (
        <div key={index} className={`trace-line ${hop.found ? '' : 'fail'}`}>
          ⏳ Traced back{hop.oldest ? <> to <b>{hop.oldest}</b></> : null}
          <em>
            {hop.found
              ? `+${hop.found} paper${hop.found > 1 ? 's' : ''}`
              : hop.error
                ? 'rate-limited'
                : 'nothing older found'}
          </em>
        </div>
      ))}
    </div>
  )
}
