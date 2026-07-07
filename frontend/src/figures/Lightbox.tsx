/**
 * The full-screen figure lightbox (click anywhere or Escape to close).
 *
 * Shared by two unrelated callers — the teacher's agent-cited answer figures
 * (`figure`/`index` always set) and the detail panel's own paper figures
 * (neither is), hence promoted out of `teacher/figures/` to this root-level
 * folder per the frontend's hybrid structure rule (multi-consumer components
 * live at the root, not nested in whichever feature built them first).
 */

import { useEffect } from 'react'
import type { AnswerFigure } from '../api'

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
      {(figure.title || figure.caption || typeof figure.figure === 'number') && (
        <div className="fig-lightbox-cap" onClick={(e) => e.stopPropagation()}>
          {typeof figure.figure === 'number' && <b>Figure {figure.figure}</b>}
          {figure.title && (
            <span>{typeof figure.figure === 'number' ? ' · ' : ''}{figure.title}</span>
          )}
          {figure.caption && (
            <span>{typeof figure.figure === 'number' || figure.title ? ' — ' : ''}{figure.caption}</span>
          )}
        </div>
      )}
    </div>
  )
}
