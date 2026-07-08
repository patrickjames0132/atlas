/** One attached figure: proxied image + caption, click to enlarge. */

import type { AnswerFigure } from '../../api'
import MathText from '../../notation/MathText'

export default function FigCard({
  figure,
  onEnlarge,
}: {
  figure: AnswerFigure
  onEnlarge: (figure: AnswerFigure) => void
}) {
  return (
    <figure className="chat-fig">
      <button
        type="button"
        className="chat-fig-btn"
        onClick={() => onEnlarge(figure)}
        title="Click to enlarge"
        aria-label="Enlarge figure"
      >
        <img src={figure.image} alt={figure.caption || 'Figure'} loading="lazy" />
      </button>
      <figcaption className="chat-fig-cap">
        <b>Figure {figure.figure}</b>
        {figure.title ? (
          <>
            {' · '}
            <MathText>{figure.title}</MathText>
          </>
        ) : null}
        {figure.caption ? (
          <>
            {' — '}
            <MathText>{figure.caption}</MathText>
          </>
        ) : null}
      </figcaption>
    </figure>
  )
}
