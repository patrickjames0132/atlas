/**
 * Bind Escape to one "unhighlight everything" gesture.
 *
 * Highlights arrive from many places — a lecture beat, a chat answer, an
 * inline `[n]` ref, an alt-drag pick — and each historically cleared only its
 * own way. This hook gives the graph a single reset key. It deliberately does
 * NOT fire when a form control has focus (typing Esc in the search box means
 * "leave the box", not "darken the graph" — the Tour sets the precedent), and
 * the caller is expected to skip overlay states it owns (the figure lightbox
 * and the tour both bind their own Esc-to-close).
 */

import { useEffect } from 'react'

/**
 * Call `onClear` whenever Escape is pressed outside a form control.
 *
 * @param onClear  The reset to run — stable or memoized; the listener rebinds
 *                 when it changes.
 */
export function useEscapeClear(onClear: () => void) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const target = event.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return
      }
      onClear()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClear])
}
