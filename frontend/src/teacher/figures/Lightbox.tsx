/** The full-screen figure lightbox (click anywhere or Escape to close). */

import { useEffect } from 'react'
import type { AnswerFigure } from '../../api'

export default function Lightbox({
  figure,
  onClose,
}: {
  figure: AnswerFigure
  onClose: () => void
}) {
  // Close on Escape while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fig-lightbox" onClick={onClose} role="dialog" aria-label="Enlarged figure">
      <button className="fig-lightbox-close" aria-label="Close">
        ✕
      </button>
      <img
        src={figure.image}
        alt={figure.caption || 'Figure'}
        onClick={(e) => e.stopPropagation()}
      />
      {(figure.caption || figure.figure) && (
        <div className="fig-lightbox-cap" onClick={(e) => e.stopPropagation()}>
          <b>Figure {figure.figure}</b>
          {figure.title ? ` · ${figure.title}` : ''}
          {figure.caption ? ` — ${figure.caption}` : ''}
        </div>
      )}
    </div>
  )
}
