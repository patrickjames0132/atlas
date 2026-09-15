// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `/`-command menu's selection behaviour — the part a grammar test can't
 * reach, because it is about state surviving (or not surviving) a keystroke.
 *
 * Three things are worth pinning. The selection must **reset** when the rows
 * change, or Enter takes a row the reader never looked at. It must **clamp**,
 * because the list shrinks as they type and an index can outlive its row. And
 * Escape must **stay** dismissed on the same text, or the menu reopens on the
 * next keystroke and the reader can't get rid of it.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { COMMANDS } from '../../src/commands/parse'
import { useCommandMenu } from '../../src/commands/useCommandMenu'

/**
 * Mount the menu and type `text` into it, caret at the end.
 *
 * @param text     What the composer holds.
 * @param commands The commands on offer.
 * @returns The rendered hook.
 */
function typed(text: string, commands = COMMANDS) {
  const menu = renderHook(() => useCommandMenu(commands))
  act(() => {
    menu.result.current.onInput(text, text.length)
  })
  return menu
}

describe('useCommandMenu', () => {
  it('opens with the matching rows and starts at the top', () => {
    const menu = typed('/')
    expect(menu.result.current.open).toBe(true)
    expect(menu.result.current.highlighted).toBe(0)
    expect(menu.result.current.choice?.id).toBe('lecture')
  })

  it('stays shut when nothing matches', () => {
    const menu = typed('/zzz')
    expect(menu.result.current.open).toBe(false)
    expect(menu.result.current.choice).toBeNull()
  })

  it('stays shut with no commands on offer', () => {
    // The no-graph case: nothing to lecture about, so nothing is suggested.
    expect(typed('/lecture', []).result.current.open).toBe(false)
  })

  it('wraps the selection at both ends', () => {
    const menu = typed('/lecture ')
    expect(menu.result.current.choices).toHaveLength(2)
    act(() => menu.result.current.move(-1))
    expect(menu.result.current.choice?.label).toBe('History')
    act(() => menu.result.current.move(1))
    expect(menu.result.current.choice?.label).toBe('Summary')
  })

  it('resets the selection when the rows change under it', () => {
    const menu = typed('/lecture ')
    act(() => menu.result.current.move(1))
    expect(menu.result.current.choice?.label).toBe('History')
    // Typing narrows the list to one row; the old index must not carry over.
    act(() => menu.result.current.onInput('/lecture s', 10))
    expect(menu.result.current.highlighted).toBe(0)
    expect(menu.result.current.choice?.label).toBe('Summary')
  })

  it('never points past the end of a list that shrank', () => {
    const menu = typed('/lecture ')
    act(() => menu.result.current.setHighlighted(1))
    act(() => menu.result.current.onInput('/lecture his', 12))
    expect(menu.result.current.choices).toHaveLength(1)
    expect(menu.result.current.highlighted).toBe(0)
  })

  it('stays dismissed on the same text, and reopens on the next change', () => {
    const menu = typed('/lec')
    act(() => menu.result.current.dismiss())
    expect(menu.result.current.open).toBe(false)
    act(() => menu.result.current.onInput('/lec', 4))
    expect(menu.result.current.open).toBe(false)
    act(() => menu.result.current.onInput('/lect', 5))
    expect(menu.result.current.open).toBe(true)
  })

  it('reopens after a reset, unlike a dismiss', () => {
    const menu = typed('/lec')
    act(() => menu.result.current.reset())
    expect(menu.result.current.open).toBe(false)
    act(() => menu.result.current.onInput('/lec', 4))
    expect(menu.result.current.open).toBe(true)
  })
})
