/**
 * A reusable, data-driven coach-mark tour: dims the screen, spotlights one
 * target element at a time, and anchors an explainer bubble beside it, with
 * Back / Next, a step counter, a title that doubles as a jump-to-any-stop
 * select, a Skip link, and a ✕ — the Yotpo-style product tour. Purely
 * presentational over a `steps` array; the caller owns when it mounts
 * (mounting starts the tour) and what "seen" means (`onClose`).
 *
 * Steps whose target selector matches nothing — or matches an element that is
 * currently hidden — are skipped, so one step list can describe optional UI
 * (a slider that only renders on multi-year graphs, a panel that may be
 * collapsed) without the tour ever pointing at a blank spot.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import './tour.css'

/** One stop on a tour. */
export interface TourStep {
  /** CSS selector of the element this step spotlights; no match = skipped. */
  target: string
  /** The bubble's heading. */
  title: string
  /** The bubble's body text. */
  body: string
  /** What this step needs the caller to stage first (open a drawer/panel) —
   *  passed to `onStage` on entry. A staged step's target is allowed to be
   *  absent at mount; the tour polls for it briefly after staging. */
  stage?: string
  /** Selector that must match at mount for a *staged* step to join the walk —
   *  its own target only exists after staging, so presence is judged by this
   *  proxy instead (e.g. the panel's own toggle button). */
  presentIf?: string
}

/** Props for {@link Tour}. */
export interface TourProps {
  /** The stops, in order; absent/hidden targets are skipped at mount. */
  steps: TourStep[]
  /** Close the tour. `completed` is true when the user walked to the end
   *  (Done), false for Skip / ✕ / Esc — callers usually persist "seen"
   *  either way, so re-runs stay a deliberate "?" click. */
  onClose: (completed: boolean) => void
  /** Called with the entering step's `stage` on every step change —
   *  `undefined` when the step needs nothing, so the caller can put staged
   *  UI away again. */
  onStage?: (stage: string | undefined) => void
}

/** How far the spotlight halo extends past the target's box, px. */
const SPOTLIGHT_PAD = 6
/** Gap between the spotlight edge and the bubble, px. */
const BUBBLE_GAP = 14
/** The bubble's CSS width (kept in sync with .tour-bubble), for placement. */
const BUBBLE_WIDTH = 300
/** Fallback bubble height for placement until the real one is measured, px. */
const BUBBLE_EST_HEIGHT = 210
/** Target polling: a staged panel needs a beat to mount before its target
 *  can be measured; a step whose target never shows within the window is
 *  dropped from the walk. Staged steps get a longer window — their content
 *  can be lazy-loaded (the detail panel's sections hydrate after selection),
 *  not just waiting on a mount. */
const MEASURE_RETRY_MS = 60
const MEASURE_TRIES = 8
const STAGED_MEASURE_TRIES = 25

/**
 * Whether a matched element can actually be pointed at right now.
 *
 * `checkVisibility` catches `display: none` ancestors (a collapsed panel's
 * lecture grid) and `visibility: hidden`; jsdom doesn't implement it, so its
 * absence counts as visible — the tests build presence, not pixels.
 *
 * @param element The step's resolved target.
 * @returns True when the element is safe to spotlight.
 */
function isVisible(element: Element): boolean {
  return element.checkVisibility?.() ?? true
}

/**
 * Render the coach-mark overlay for the steps whose targets exist.
 *
 * @returns The tour overlay, or null when no step has a visible target.
 */
export default function Tour({ steps, onClose, onStage }: TourProps) {
  // Resolve once, AFTER the mount commit (an effect, not render-time memo —
  // when the tour mounts in the same commit as its targets, querySelector
  // during render sees none of them). null = not resolved yet. A tour is
  // short-lived, so mid-run DOM churn is handled per-step (below), not by
  // re-resolving the whole list. A staged step's own target may not exist
  // until its panel opens, so its presence is judged by its `presentIf`
  // proxy (or assumed, when it has none).
  const [stops, setStops] = useState<TourStep[] | null>(null)
  const [index, setIndex] = useState(0)
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  // The bubble's real height, measured after paint — placement needs it to
  // decide above-vs-below and to clamp without pinching off at the viewport
  // bottom (bodies vary in length per step).
  const bubbleRef = useRef<HTMLDivElement | null>(null)
  const [bubbleHeight, setBubbleHeight] = useState(BUBBLE_EST_HEIGHT)
  useLayoutEffect(() => {
    if (bubbleRef.current) setBubbleHeight(bubbleRef.current.offsetHeight)
  }, [index, targetRect])
  useEffect(() => {
    setStops(
      steps.filter((step) => {
        // presentIf tests EXISTENCE, not visibility — it gates on the data
        // condition (a picker only renders once there's something to pick),
        // while staging is what makes the element visible when reached.
        if (step.presentIf) return document.querySelector(step.presentIf) !== null
        if (step.stage !== undefined) return true // staged, no proxy: assume stageable
        const element = document.querySelector(step.target)
        return element !== null && isVisible(element)
      }),
    )
    // A new list is a new tour (the caller swapped phases) — start it over.
    setIndex(0)
  }, [steps])

  const step = stops?.[index]

  // Nothing to point at (no graph tools on screen) — close immediately rather
  // than rendering an empty dimmer.
  useEffect(() => {
    if (stops !== null && stops.length === 0) onClose(false)
  }, [stops, onClose])

  // Tell the caller what the entering step needs staged (its drawer/panel
  // opened) — undefined for steps that need nothing, so staged UI gets put
  // away again as the walk moves on.
  useEffect(() => {
    onStage?.(step?.stage)
  }, [step, onStage])

  // Measure the active step's target, polling briefly: a staged panel mounts
  // a beat after `onStage` asks for it, and a target that vanished mid-tour
  // gets the same grace window before its stop is dropped from the walk.
  useEffect(() => {
    if (!stops || !step) return undefined
    let tries = 0
    let timer: number | undefined
    const maxTries = step.stage !== undefined ? STAGED_MEASURE_TRIES : MEASURE_TRIES
    const attempt = () => {
      const element = document.querySelector(step.target)
      if (element && isVisible(element)) {
        // Bring a below-the-fold section (deep in a scrollable panel) into
        // view first — the scroll fires this listener again, re-measuring.
        element.scrollIntoView?.({ block: 'nearest' })
        setTargetRect(element.getBoundingClientRect())
        return
      }
      setTargetRect(null)
      if (tries < maxTries) {
        tries += 1
        timer = window.setTimeout(attempt, MEASURE_RETRY_MS)
        return
      }
      // Never appeared (or vanished for good): drop the stop, stay in bounds.
      setStops((current) => current && current.filter((other) => other !== step))
      setIndex((current) => Math.min(current, Math.max(stops.length - 2, 0)))
    }
    attempt()
    window.addEventListener('resize', attempt)
    // Capture-phase so scrolls inside panels (the teacher transcript) re-anchor too.
    window.addEventListener('scroll', attempt, true)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('resize', attempt)
      window.removeEventListener('scroll', attempt, true)
    }
  }, [stops, step])

  const isLast = stops !== null && index === stops.length - 1
  const next = useCallback(() => {
    if (isLast) onClose(true)
    else setIndex((current) => current + 1)
  }, [isLast, onClose])
  const back = useCallback(() => setIndex((current) => Math.max(current - 1, 0)), [])

  // Keyboard: Esc quits, arrows navigate — the same contract as the lightbox.
  // Except while the jump select has focus: there the arrows belong to the
  // select's own option-walking, and stepping the tour under it too would
  // fight the user.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLSelectElement && event.key !== 'Escape') return
      if (event.key === 'Escape') onClose(false)
      else if (event.key === 'ArrowRight') next()
      else if (event.key === 'ArrowLeft') back()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, next, back])

  if (!stops || !step) return null

  // Spotlight box: the target's rect plus a halo pad.
  const spot = targetRect && {
    top: targetRect.top - SPOTLIGHT_PAD,
    left: targetRect.left - SPOTLIGHT_PAD,
    width: targetRect.width + SPOTLIGHT_PAD * 2,
    height: targetRect.height + SPOTLIGHT_PAD * 2,
  }

  // Bubble placement: beside the spotlight on whichever horizontal side has
  // room (right first — the controls live top-left), else beneath it — or
  // above it when the target hugs the bottom of the screen (the ask bar) and
  // below would pinch off. Always clamped into the viewport, using the
  // bubble's measured height (a body's length varies per step).
  let bubbleTop = 0
  let bubbleLeft = 0
  if (spot) {
    const fitsRight = spot.left + spot.width + BUBBLE_GAP + BUBBLE_WIDTH <= window.innerWidth
    const fitsLeft = spot.left - BUBBLE_GAP - BUBBLE_WIDTH >= 0
    if (fitsRight || fitsLeft) {
      bubbleLeft = fitsRight
        ? spot.left + spot.width + BUBBLE_GAP
        : spot.left - BUBBLE_GAP - BUBBLE_WIDTH
      bubbleTop = spot.top
    } else {
      bubbleLeft = Math.max(spot.left, 8)
      const below = spot.top + spot.height + BUBBLE_GAP
      const fitsBelow = below + bubbleHeight + 8 <= window.innerHeight
      bubbleTop = fitsBelow ? below : spot.top - BUBBLE_GAP - bubbleHeight
    }
    bubbleLeft = Math.min(Math.max(bubbleLeft, 8), window.innerWidth - BUBBLE_WIDTH - 8)
    bubbleTop = Math.min(Math.max(bubbleTop, 8), window.innerHeight - bubbleHeight - 8)
  }

  return (
    <div className="tour-backdrop" role="dialog" aria-label="Guided tour">
      {spot && <div className="tour-spotlight" style={spot} />}
      <div className="tour-bubble" ref={bubbleRef} style={{ top: bubbleTop, left: bubbleLeft }}>
        <div className="tour-bubble-head">
          {/* The title doubles as the jump select: the h4 is the visual, and
              an invisible native <select> stretched over it supplies the
              dropdown — click the title, pick any stop. */}
          <span className="tour-jump">
            <h4>{step.title}</h4>
            <span className="tour-jump-caret" aria-hidden="true">
              ▾
            </span>
            <select
              value={index}
              onChange={(event) => setIndex(Number(event.target.value))}
              aria-label="Jump to a tip"
            >
              {stops.map((stop, stopIndex) => (
                <option key={stop.target} value={stopIndex}>
                  {stopIndex + 1}. {stop.title}
                </option>
              ))}
            </select>
          </span>
          <button className="tour-close" onClick={() => onClose(false)} aria-label="Quit the tour">
            ✕
          </button>
        </div>
        <p>{step.body}</p>
        <div className="tour-foot">
          <button className="tour-skip" onClick={() => onClose(false)}>
            Skip tips
          </button>
          <span className="tour-count">
            {index + 1} / {stops.length}
          </span>
          <div className="tour-nav">
            <button onClick={back} disabled={index === 0}>
              Back
            </button>
            <button className="tour-next" onClick={next}>
              {isLast ? 'Done' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
