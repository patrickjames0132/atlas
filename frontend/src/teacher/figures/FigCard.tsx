/** One attached figure: proxied image + caption, click to enlarge. */

import type { AnswerFigure } from '../../api'

export default function FigCard({
  f,
  onEnlarge,
}: {
  f: AnswerFigure
  onEnlarge: (f: AnswerFigure) => void
}) {
  return (
    <figure className="chat-fig">
      <button
        type="button"
        className="chat-fig-btn"
        onClick={() => onEnlarge(f)}
        title="Click to enlarge"
        aria-label="Enlarge figure"
      >
        <img src={f.image} alt={f.caption || 'Figure'} loading="lazy" />
      </button>
      <figcaption className="chat-fig-cap">
        <b>Figure {f.figure}</b>
        {f.title ? ` · ${f.title}` : ''}
        {f.caption ? ` — ${f.caption}` : ''}
      </figcaption>
    </figure>
  )
}
