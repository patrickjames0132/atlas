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
      {beats.map((beat, index) => (
        <li
          key={index}
          className={`beat ${activeBeat === index ? 'active' : ''}`}
          onClick={() => onBeatClick(index, beat)}
        >
          {beat.heading && <div className="beat-heading">{beat.heading}</div>}
          <p>{beat.text}</p>
          {beat.node_ids.length > 0 && (
            <div className="beat-nodes">
              {beat.node_ids.length} paper{beat.node_ids.length > 1 ? 's' : ''} ✦
            </div>
          )}
        </li>
      ))}
    </ol>
  )
}
