/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `/`-command grammar: which command the caret is in, what a pick splices
 * in, and what a finished message invokes.
 *
 * The valuable half here is the **negatives**. A prefix as common as `/` sits
 * inside URLs, dates and fractions, and the anchoring rule that keeps those
 * from opening the menu is the whole reason `/` is safe to use — so it is
 * pinned by test rather than left to the reader of the regex. The same goes for
 * `readCommand`'s strictness: everything it declines falls through to the
 * v7.20.0 router, and that fall-through is a feature, not a gap.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import {
  COMMANDS,
  activeCommand,
  commandChoices,
  insertCommand,
  readCommand,
} from '../../src/commands/parse'

/** The caret at the end of the text, which is where typing leaves it. */
function atEnd(text: string) {
  return activeCommand(text, text.length)
}

describe('activeCommand', () => {
  it('opens on a slash at the start of the message', () => {
    expect(atEnd('/')).toEqual({ stage: 'name', query: '', start: 0, end: 1 })
  })

  it('carries the partial name as the query', () => {
    expect(atEnd('/lec')?.query).toBe('lec')
  })

  it('tolerates a stray leading space', () => {
    const active = atEnd('  /lec')
    expect(active?.query).toBe('lec')
    // `start` is the slash, not the message — so a pick replaces the command
    // and leaves the reader's whitespace alone.
    expect(active?.start).toBe(2)
  })

  it('moves to the argument stage past a known command', () => {
    const active = atEnd('/lecture his')
    expect(active?.stage).toBe('argument')
    expect(active?.command?.name).toBe('lecture')
    expect(active?.query).toBe('his')
  })

  it('offers the arguments the moment the space is typed', () => {
    expect(atEnd('/lecture ')).toMatchObject({ stage: 'argument', query: '' })
  })

  // The negatives: everything below must leave the composer alone.
  it.each([
    ['a mid-message slash', 'see figure 2/3'],
    ['a pasted URL', 'https://arxiv.org/abs/1706.03762'],
    ['a date', 'published 9/13'],
    ['a question that merely contains one', 'what is p/q here?'],
  ])('stays shut on %s', (_label, text) => {
    expect(atEnd(text)).toBeNull()
  })

  it('stays shut once the command line has been left', () => {
    const text = '/lecture\nand then a thought'
    expect(activeCommand(text, text.length)).toBeNull()
  })

  it('stops offering arguments once a sentence is under way', () => {
    // No command takes two words, so this is prose now — and prose is the
    // router's business, not the menu's.
    expect(atEnd('/lecture on the')).toBeNull()
  })

  it('does not recognise a command the composer was not given', () => {
    expect(activeCommand('/lecture his', 12, [])).toBeNull()
  })
})

describe('commandChoices', () => {
  it('matches a command by prefix, not by substring', () => {
    const byPrefix = commandChoices(atEnd('/lec')!)
    expect(byPrefix.map((choice) => choice.id)).toEqual(['lecture'])
    // `ture` is inside `lecture` but is not how anyone types a command.
    expect(commandChoices(atEnd('/ture')!)).toEqual([])
  })

  it('offers every command on a bare slash', () => {
    expect(commandChoices(atEnd('/')!)).toHaveLength(COMMANDS.length)
  })

  it('marks a command with arguments as continuing', () => {
    const [lecture] = commandChoices(atEnd('/lecture')!)
    expect(lecture.continues).toBe(true)
    // The trailing space is what re-opens the menu on the arguments.
    expect(lecture.insert).toBe('/lecture ')
  })

  it('offers the command its own arguments at the argument stage', () => {
    const choices = commandChoices(atEnd('/lecture ')!)
    expect(choices.map((choice) => choice.label)).toEqual(['Summary', 'History'])
    expect(choices.every((choice) => !choice.continues)).toBe(true)
  })

  it('narrows the arguments as they are typed', () => {
    expect(commandChoices(atEnd('/lecture his')!).map((choice) => choice.label)).toEqual([
      'History',
    ])
  })
})

describe('insertCommand', () => {
  it('replaces the partial name with the command', () => {
    const active = atEnd('/lec')!
    const [lecture] = commandChoices(active)
    expect(insertCommand('/lec', active, lecture)).toEqual({ text: '/lecture ', caret: 9 })
  })

  it('replaces the partial argument and leaves the command alone', () => {
    const active = atEnd('/lecture his')!
    const [history] = commandChoices(active)
    expect(insertCommand('/lecture his', active, history)).toEqual({
      text: '/lecture history ',
      caret: 17,
    })
  })

  it('keeps whatever follows the caret', () => {
    const text = '/lec trailing'
    const active = activeCommand(text, 4)!
    const [lecture] = commandChoices(active)
    expect(insertCommand(text, active, lecture).text).toBe('/lecture  trailing')
  })
})

describe('readCommand', () => {
  it('reads a bare command as its default argument', () => {
    expect(readCommand('/lecture')).toMatchObject({ arg: 'summary' })
  })

  it('reads the argument the reader named', () => {
    expect(readCommand('/lecture history')).toMatchObject({ arg: 'history' })
  })

  it('is case-insensitive and tolerates surrounding whitespace', () => {
    expect(readCommand('  /Lecture HISTORY  ')).toMatchObject({ arg: 'history' })
  })

  // Everything below is deliberately *not* a command: it falls through to the
  // ordinary path, where the router reads it as words. That is a better
  // outcome than silently dropping the words or inventing an argument.
  it.each([
    ['an unknown command', '/summarise'],
    ['an unknown argument', '/lecture chronological'],
    ['a command with a sentence after it', '/lecture on these papers'],
    ['a message that only contains a slash later', 'lecture /history'],
    ['an empty message', ''],
  ])('declines %s', (_label, text) => {
    expect(readCommand(text)).toBeNull()
  })

  it('declines a command the composer was not given', () => {
    // With no graph there is nothing to lecture about, so `/lecture` is not
    // merely hidden — it is unrecognised, and the message is treated as words.
    expect(readCommand('/lecture history', [])).toBeNull()
  })
})
