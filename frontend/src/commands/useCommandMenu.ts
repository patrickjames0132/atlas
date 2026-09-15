/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `/`-command menu's engine: watch what is being typed, match it against
 * the registry, and hold the keyboard selection.
 *
 * This is the `@`-mention hook with its expensive half removed. There is no
 * network, no cache, no provider and therefore **no debounce, no abort and no
 * out-of-order results** — the command list is static and local, so matching
 * is a filter over an array and the menu can simply re-render on every
 * keystroke. Two consequences worth stating, because they are what the mention
 * hook spends most of its code on and this one doesn't:
 *
 * * **The selection is tracked by index**, not by id. The mention list is
 *   re-ranked underneath the reader when the full results land, so an index
 *   would point at a different paper than the one they were looking at; here
 *   the order is registry order and never changes under a fixed query, so an
 *   index is both correct and simpler.
 * * **There is no `loading` and no phase line.** Nothing is in flight, ever.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useMemo, useRef, useState } from 'react'
import { activeCommand, commandChoices } from './parse'
import type { ActiveCommand, Command, CommandChoice } from './parse'

/**
 * Drive the command menu for one composer.
 *
 * @param commands The commands this composer may offer. Pass a shorter list
 *                 when the panel can't run them all — a command absent here is
 *                 neither suggested nor recognised at send, so it is honestly
 *                 unavailable rather than silently inert.
 * @returns The menu's state plus the handlers the composer wires up.
 */
export function useCommandMenu(commands: Command[]) {
  const [active, setActive] = useState<ActiveCommand | null>(null)
  const [highlighted, setHighlighted] = useState(0)
  // The reader pressed Escape on this exact text: stay shut until they type
  // something else, rather than reopening on the next keystroke.
  const dismissed = useRef<string | null>(null)

  const choices = useMemo(
    () => (active ? commandChoices(active, commands) : []),
    [active, commands],
  )

  /** Re-read the composer and open, update, or close the menu. */
  const onInput = useCallback(
    (text: string, caret: number) => {
      const found = activeCommand(text, caret, commands)
      if (!found) {
        setActive(null)
        return
      }
      const token = `${found.stage}:${found.query}`
      if (dismissed.current === token) return
      dismissed.current = null
      // A new query starts at the top: the rows have changed, so the row the
      // keyboard was on is not the row it looks like it is on.
      setActive((previous) => {
        if (previous?.stage !== found.stage || previous.query !== found.query) setHighlighted(0)
        return found
      })
    },
    [commands],
  )

  /** Close the menu and remember not to reopen on this text. */
  const dismiss = useCallback(() => {
    dismissed.current = active ? `${active.stage}:${active.query}` : null
    setActive(null)
  }, [active])

  /** Close it outright — after a pick that finishes the command, or a send. */
  const reset = useCallback(() => {
    dismissed.current = null
    setActive(null)
    setHighlighted(0)
  }, [])

  /** Move the keyboard selection, wrapping at both ends. */
  const move = useCallback(
    (delta: number) => {
      if (choices.length === 0) return
      setHighlighted((current) => (current + delta + choices.length) % choices.length)
    },
    [choices],
  )

  // Clamped rather than trusted: the rows shrink as the reader types, and the
  // selection must never sit past the end of a list that got shorter.
  const index = Math.min(highlighted, Math.max(0, choices.length - 1))

  return {
    /** The command being typed, or null when the menu is shut. */
    active,
    /** Whether the menu should render: a live command with something to offer. */
    open: active !== null && choices.length > 0,
    choices,
    highlighted: index,
    /** The row Enter would accept, or null. */
    choice: (choices[index] ?? null) as CommandChoice | null,
    onInput,
    move,
    setHighlighted,
    dismiss,
    reset,
  }
}
