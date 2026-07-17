// @vitest-environment jsdom
/**
 * The Esc-to-clear binding: Escape fires the reset, any other key doesn't,
 * and a focused form control (typing Esc in the search box means "leave the
 * box") swallows it.
 */

import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useEscapeClear } from '../../../src/graph/hooks/useEscapeClear'

/** Dispatch a window keydown of `key` from `target` (default: the body). */
function press(key: string, target: EventTarget = document.body) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true })
  target.dispatchEvent(event)
}

describe('useEscapeClear', () => {
  it('fires on Escape and only on Escape', () => {
    const onClear = vi.fn()
    renderHook(() => useEscapeClear(onClear))
    press('a')
    press('Enter')
    expect(onClear).not.toHaveBeenCalled()
    press('Escape')
    expect(onClear).toHaveBeenCalledTimes(1)
  })

  it('ignores Escape typed inside a form control', () => {
    const onClear = vi.fn()
    renderHook(() => useEscapeClear(onClear))
    const input = document.createElement('input')
    document.body.appendChild(input)
    press('Escape', input)
    expect(onClear).not.toHaveBeenCalled()
    input.remove()
  })

  it('unbinds on unmount', () => {
    const onClear = vi.fn()
    const { unmount } = renderHook(() => useEscapeClear(onClear))
    unmount()
    press('Escape')
    expect(onClear).not.toHaveBeenCalled()
  })
})
