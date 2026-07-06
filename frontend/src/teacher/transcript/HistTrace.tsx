/** The history lecture's backfill hops, shown above the beats as the story
 * traces a field back to its roots before narrating. */

import type { BackfillTrace } from '../../api'

export default function HistTrace({ trace }: { trace: BackfillTrace[] }) {
  if (trace.length === 0) return null
  return (
    <div className="chat-trace hist-trace">
      {trace.map((t, i) => (
        <div key={i} className={`trace-line ${t.found ? '' : 'fail'}`}>
          ⏳ Traced back{t.oldest ? <> to <b>{t.oldest}</b></> : null}
          <em>
            {t.found
              ? `+${t.found} paper${t.found > 1 ? 's' : ''}`
              : t.error
                ? 'rate-limited'
                : 'nothing older found'}
          </em>
        </div>
      ))}
    </div>
  )
}
