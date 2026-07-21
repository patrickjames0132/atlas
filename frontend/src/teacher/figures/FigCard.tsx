/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * One attached figure: proxied image + caption, click to enlarge.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { AnswerFigure } from '../../api'
import MathText from '../../notation/MathText'

/**
 * Render one inline figure card.
 *
 * @returns The figure with its numbered caption.
 */
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
        {/* The float's own designation when its caption carried one
            ("Figure 12.4"); else number attachments in answer order. */}
        <b>{figure.label ?? `Figure ${figure.slot ?? figure.figure ?? 1}`}</b>
        {figure.title ? (
          <>
            {' · '}
            {/* The source stands out like the label; only the caption stays muted. */}
            <b>
              <MathText>{figure.title}</MathText>
            </b>
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
