// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The collapsible find control: a 🔍 toggle that expands into the input pill
 * on click, stays pinned open while a query is live, reports typing/hits, and
 * collapses again when cleared — with Esc inside the box clearing the query
 * first (never bubbling into a graph-wide reset).
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import FindBar from '../../../src/graph/controls/FindBar'
import type { ComponentProps } from 'react'

const INPUT_LABEL = 'Find a paper among those on screen (title or author)'
const TOGGLE_LABEL = 'Find a paper on screen'

/** Full prop set with inert defaults; override what a case exercises. */
function makeProps(
  overrides: Partial<ComponentProps<typeof FindBar>> = {},
): ComponentProps<typeof FindBar> {
  return { query: '', count: null, onQuery: () => {}, onSelectAll: () => {}, ...overrides }
}

afterEach(cleanup)

describe('FindBar', () => {
  it('starts as the collapsed 🔍 and expands (focused) on click', () => {
    render(<FindBar {...makeProps()} />)
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
    fireEvent.click(screen.getByLabelText(TOGGLE_LABEL))
    const input = screen.getByLabelText(INPUT_LABEL)
    expect(document.activeElement).toBe(input)
  })

  it('a live query pins the pill open without any toggle click', () => {
    render(<FindBar {...makeProps({ query: 'bert', count: 3 })} />)
    expect(screen.getByLabelText(INPUT_LABEL)).toBeTruthy()
    expect(screen.getByText('3 hits', { exact: false })).toBeTruthy()
  })

  it('reports typing and clears+collapses via ✕', () => {
    const onQuery = vi.fn()
    const { rerender } = render(<FindBar {...makeProps({ query: 'bert', count: 3, onQuery })} />)
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: 'berts' } })
    expect(onQuery).toHaveBeenCalledWith('berts')
    fireEvent.click(screen.getByLabelText('Clear the find'))
    expect(onQuery).toHaveBeenCalledWith('')
    rerender(<FindBar {...makeProps({ onQuery })} />)
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
    expect(screen.getByLabelText(TOGGLE_LABEL)).toBeTruthy()
  })

  it('Esc clears the query first, then a second Esc collapses the empty pill', () => {
    const onQuery = vi.fn()
    const { rerender } = render(<FindBar {...makeProps({ query: 'bert', count: 0, onQuery })} />)
    const input = screen.getByLabelText(INPUT_LABEL)
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onQuery).toHaveBeenCalledWith('')
    rerender(<FindBar {...makeProps({ onQuery })} />)
    // The pill was pinned open only by the query; once empty a second Esc
    // (or the blur it causes) tucks it away.
    const stillOpen = screen.queryByLabelText(INPUT_LABEL)
    if (stillOpen) fireEvent.keyDown(stillOpen, { key: 'Escape' })
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
  })

  it('offers "select" only when there are hits, and fires the select-all', () => {
    const onSelectAll = vi.fn()
    const { rerender } = render(
      <FindBar {...makeProps({ query: 'bert', count: 3, onSelectAll })} />,
    )
    fireEvent.click(screen.getByText('select'))
    expect(onSelectAll).toHaveBeenCalledTimes(1)
    // Zero hits: nothing to select, the link stays away.
    rerender(<FindBar {...makeProps({ query: 'zzz', count: 0, onSelectAll })} />)
    expect(screen.queryByText('select')).toBeNull()
  })

  it('Enter in the box is the same select-all — and a no-op with zero hits', () => {
    const onSelectAll = vi.fn()
    const { rerender } = render(
      <FindBar {...makeProps({ query: 'bert', count: 3, onSelectAll })} />,
    )
    fireEvent.keyDown(screen.getByLabelText(INPUT_LABEL), { key: 'Enter' })
    expect(onSelectAll).toHaveBeenCalledTimes(1)
    rerender(<FindBar {...makeProps({ query: 'zzz', count: 0, onSelectAll })} />)
    fireEvent.keyDown(screen.getByLabelText(INPUT_LABEL), { key: 'Enter' })
    expect(onSelectAll).toHaveBeenCalledTimes(1)
  })

  it('blurring an empty box tidies the pill back to the 🔍', () => {
    render(<FindBar {...makeProps()} />)
    fireEvent.click(screen.getByLabelText(TOGGLE_LABEL))
    fireEvent.blur(screen.getByLabelText(INPUT_LABEL))
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
    expect(screen.getByLabelText(TOGGLE_LABEL)).toBeTruthy()
  })
})
