// @vitest-environment jsdom
/**
 * The collapsible find control: a 🔍 toggle that expands into the input pill
 * on click, stays pinned open while a query is live, reports typing/hits, and
 * collapses again when cleared — with Esc inside the box clearing the query
 * first (never bubbling into a graph-wide reset).
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import FindBar from '../../../src/graph/controls/FindBar'

const INPUT_LABEL = 'Find a paper among those on screen (title or author)'
const TOGGLE_LABEL = 'Find a paper on screen'

afterEach(cleanup)

describe('FindBar', () => {
  it('starts as the collapsed 🔍 and expands (focused) on click', () => {
    render(<FindBar query="" count={null} onQuery={() => {}} />)
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
    fireEvent.click(screen.getByLabelText(TOGGLE_LABEL))
    const input = screen.getByLabelText(INPUT_LABEL)
    expect(document.activeElement).toBe(input)
  })

  it('a live query pins the pill open without any toggle click', () => {
    render(<FindBar query="bert" count={3} onQuery={() => {}} />)
    expect(screen.getByLabelText(INPUT_LABEL)).toBeTruthy()
    expect(screen.getByText('3 hits', { exact: false })).toBeTruthy()
  })

  it('reports typing and clears+collapses via ✕', () => {
    const onQuery = vi.fn()
    const { rerender } = render(<FindBar query="bert" count={3} onQuery={onQuery} />)
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: 'berts' } })
    expect(onQuery).toHaveBeenCalledWith('berts')
    fireEvent.click(screen.getByLabelText('Clear the find'))
    expect(onQuery).toHaveBeenCalledWith('')
    rerender(<FindBar query="" count={null} onQuery={onQuery} />)
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
    expect(screen.getByLabelText(TOGGLE_LABEL)).toBeTruthy()
  })

  it('Esc clears the query first, then a second Esc collapses the empty pill', () => {
    const onQuery = vi.fn()
    const { rerender } = render(<FindBar query="bert" count={0} onQuery={onQuery} />)
    const input = screen.getByLabelText(INPUT_LABEL)
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onQuery).toHaveBeenCalledWith('')
    rerender(<FindBar query="" count={null} onQuery={onQuery} />)
    // The pill was pinned open only by the query; once empty a second Esc
    // (or the blur it causes) tucks it away.
    const stillOpen = screen.queryByLabelText(INPUT_LABEL)
    if (stillOpen) fireEvent.keyDown(stillOpen, { key: 'Escape' })
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
  })

  it('blurring an empty box tidies the pill back to the 🔍', () => {
    render(<FindBar query="" count={null} onQuery={() => {}} />)
    fireEvent.click(screen.getByLabelText(TOGGLE_LABEL))
    fireEvent.blur(screen.getByLabelText(INPUT_LABEL))
    expect(screen.queryByLabelText(INPUT_LABEL)).toBeNull()
    expect(screen.getByLabelText(TOGGLE_LABEL)).toBeTruthy()
  })
})
