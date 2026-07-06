/** The lecture beats: click one to light its papers on the graph, click the
 * active one again to clear. */

import type { Beat } from '../../api'

export default function BeatList({
  beats,
  activeBeat,
  onBeatClick,
}: {
  beats: Beat[]
  activeBeat: number | null
  onBeatClick: (index: number, beat: Beat) => void
}) {
  if (beats.length === 0) return null
  return (
    <ol className="beats">
      {beats.map((b, i) => (
        <li
          key={i}
          className={`beat ${activeBeat === i ? 'active' : ''}`}
          onClick={() => onBeatClick(i, b)}
        >
          {b.heading && <div className="beat-heading">{b.heading}</div>}
          <p>{b.text}</p>
          {b.node_ids.length > 0 && (
            <div className="beat-nodes">
              {b.node_ids.length} paper{b.node_ids.length > 1 ? 's' : ''} ✦
            </div>
          )}
        </li>
      ))}
    </ol>
  )
}
