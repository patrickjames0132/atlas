/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `/`-command menu: the commands (or values) matching what is being typed,
 * shown above the composer.
 *
 * Above the composer for the same reason the mention dropdown is — the bar sits
 * at the bottom of the panel, so a list below it would open off-screen — and
 * built to the same row shape, because they are the same gesture with a
 * different prefix and a reader should not have to learn it twice.
 *
 * Each row is a **label over a hint**, and the hint is the point: this menu is
 * where a reader finds out that lectures exist at all, now that the panel has
 * no Lecture section to explain itself. It is documentation that happens to be
 * clickable.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { CommandChoice } from './parse'
import './commands.css'

/** Props for {@link CommandMenu}. */
export interface CommandMenuProps {
  /** The rows to show, in registry order. */
  choices: CommandChoice[]
  /** Index of the row the keyboard is on — Enter accepts it. */
  highlighted: number
  /** Heading naming what is being chosen ("Commands", or the command's name). */
  heading: string
  /** Accept a row (click). */
  onPick: (choice: CommandChoice) => void
  /** Move the keyboard selection onto a row (hover), so mouse and keyboard
   *  never disagree about which row Enter would take. */
  onHighlight: (index: number) => void
}

/**
 * Render the command menu.
 *
 * @param props See {@link CommandMenuProps}.
 * @returns The menu panel.
 */
export default function CommandMenu({
  choices,
  highlighted,
  heading,
  onPick,
  onHighlight,
}: CommandMenuProps) {
  return (
    <div className="command-panel" role="listbox" aria-label="Commands">
      <div className="command-head">{heading}</div>
      {choices.map((choice, index) => (
        <button
          key={choice.id}
          type="button"
          role="option"
          aria-selected={index === highlighted}
          className={`command-row${index === highlighted ? ' on' : ''}`}
          // Pointer-down, not click: the composer's blur would otherwise close
          // the panel before a click could land on it.
          onMouseDown={(event) => {
            event.preventDefault()
            onPick(choice)
          }}
          onMouseEnter={() => onHighlight(index)}
        >
          <span className="command-text">
            <span className="command-label">{choice.label}</span>
            <span className="command-hint">{choice.hint}</span>
          </span>
          {/* Says the pick is not the end of the invocation — Enter here opens
              the values rather than sending. Without it, a reader who picks
              `/lecture` and sees the menu stay up reads it as a failed pick. */}
          {choice.continues && (
            <span className="command-more" aria-hidden="true">
              ›
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
