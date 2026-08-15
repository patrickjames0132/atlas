/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Three dots hopping in a cascade — the panel's one "working on it" idiom,
 * shared by every surface that has to say so: a lecture button that's
 * generating, the send control while an answer streams, and the assistant
 * bubble before its first token lands.
 *
 * Extracted once it had a third caller. The point of sharing it is the
 * *rhythm*: one keyframe and one stagger (`teacher.css`), so the panel never
 * shows two almost-but-not-quite-matching waits at the same time — which is
 * exactly what happens when each surface rolls its own.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/**
 * Render the hopping-dots indicator.
 *
 * @param label An accessible name, for the surfaces where the dots are the
 *              only thing saying what's happening. Omit inside a control that
 *              already names the state itself (the send button becomes "Stop
 *              generating"), so a screen reader hears it once, not twice.
 * @returns The three-dot indicator.
 */
export default function HopDots({ label }: { label?: string }) {
  return (
    <span
      className="hop-dots"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <span className="hop-dot" />
      <span className="hop-dot" />
      <span className="hop-dot" />
    </span>
  )
}
