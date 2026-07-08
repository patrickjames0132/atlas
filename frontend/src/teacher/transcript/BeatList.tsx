/** The lecture beats: click one to light its papers on the graph, click the
 * active one again to clear. A beat may carry a real paper figure (the
 * seed's own in intuition mode, a story paper's in history/evolution) —
 * rendered inline, click to enlarge. */

import type { AnswerFigure, Beat } from '../../api'
import FigCard from '../figures/FigCard'

/** Adapt a beat's figure to the shape FigCard/Lightbox render. */
const asAnswerFigure = (figure: NonNullable<Beat['figure']>): AnswerFigure => ({
  image: figure.image,
  caption: figure.caption,
  title: figure.title ?? null,
  figure: figure.number,
})

export default function BeatList({
  beats,
  activeBeat,
  onBeatClick,
  onEnlarge,
}: {
  beats: Beat[]
  activeBeat: number | null
  onBeatClick: (index: number, beat: Beat) => void
  onEnlarge: (figure: AnswerFigure) => void
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
          {beat.figure && (
            // Enlarging the figure must not toggle the beat's highlight.
            <div onClick={(event) => event.stopPropagation()}>
              <FigCard figure={asAnswerFigure(beat.figure)} onEnlarge={onEnlarge} />
            </div>
          )}
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
