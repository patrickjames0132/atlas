// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The scope picker's popover is controlled (`open`/`onOpenChange`) so the
 * assistant header can keep its two pickers mutually exclusive — these tests
 * pin the controlled contract: the popover renders only when told to, the
 * trigger reports a toggle, and the header ✕ reports a close.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import ScopePicker from '../../src/teacher/ScopePicker'

afterEach(cleanup)

const LABELS = {
  icon: '📚',
  unit: 'source',
  heading: 'Search in',
  allHint: 'All sources are searched.',
  someHint: 'Only the checked sources are searched.',
  noneHint: 'No sources selected.',
  buttonTitle: 'Choose sources',
}

const ITEMS = [
  { id: 'a', title: 'First source' },
  { id: 'b', title: 'Second source' },
]

/**
 * Render the picker with inert selection callbacks and the given open state.
 *
 * @param open Whether the popover is shown.
 * @param onOpenChange Spy receiving the requested open state.
 * @returns The RTL render result.
 */
function renderPicker(open: boolean, onOpenChange: (open: boolean) => void) {
  return render(
    <ScopePicker
      items={ITEMS}
      checkedIds={['a', 'b']}
      open={open}
      onOpenChange={onOpenChange}
      onToggle={() => {}}
      onSelectAll={() => {}}
      onDeselectAll={() => {}}
      labels={LABELS}
    />,
  )
}

describe('ScopePicker', () => {
  it('renders the popover only when open (state is the parent’s)', () => {
    const { rerender } = renderPicker(false, () => {})
    expect(screen.queryByText('Search in')).toBeNull()
    rerender(
      <ScopePicker
        items={ITEMS}
        checkedIds={['a', 'b']}
        open={true}
        onOpenChange={() => {}}
        onToggle={() => {}}
        onSelectAll={() => {}}
        onDeselectAll={() => {}}
        labels={LABELS}
      />,
    )
    expect(screen.getByText('Search in')).toBeTruthy()
  })

  it('clicking the trigger requests the opposite open state', () => {
    const onOpenChange = vi.fn()
    renderPicker(false, onOpenChange)
    fireEvent.click(screen.getByText('📚 All sources'))
    expect(onOpenChange).toHaveBeenCalledWith(true)
  })

  it('the popover ✕ requests a close', () => {
    const onOpenChange = vi.fn()
    renderPicker(true, onOpenChange)
    fireEvent.click(screen.getByLabelText('Close the source picker'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

/**
 * Render an open picker with the given checked subset and bulk-action spies.
 *
 * @param checkedIds The ids currently checked.
 * @returns The bulk-action spies.
 */
function renderWithChecked(checkedIds: string[]) {
  const onSelectAll = vi.fn()
  const onDeselectAll = vi.fn()
  render(
    <ScopePicker
      items={ITEMS}
      checkedIds={checkedIds}
      open={true}
      onOpenChange={() => {}}
      onToggle={() => {}}
      onSelectAll={onSelectAll}
      onDeselectAll={onDeselectAll}
      labels={LABELS}
    />,
  )
  return { onSelectAll, onDeselectAll }
}

describe('ScopePicker bulk actions', () => {
  // The labels are deliberately the compact "All"/"None", not
  // "Select all"/"Deselect all": a subset shows BOTH at once, and the long
  // pair overflowed the 240px popover — heading wrapped, ✕ off-view, a
  // horizontal scrollbar underneath (Patrick's 2026-07-17 report).
  it('a subset shows compact All and None, both wired', () => {
    const { onSelectAll, onDeselectAll } = renderWithChecked(['a'])
    fireEvent.click(screen.getByText('All'))
    fireEvent.click(screen.getByText('None'))
    expect(onSelectAll).toHaveBeenCalledTimes(1)
    expect(onDeselectAll).toHaveBeenCalledTimes(1)
  })

  it('everything checked hides All; nothing checked hides None', () => {
    renderWithChecked(['a', 'b'])
    expect(screen.queryByText('All')).toBeNull()
    expect(screen.getByText('None')).toBeTruthy()
    cleanup()
    renderWithChecked([])
    expect(screen.getByText('All')).toBeTruthy()
    expect(screen.queryByText('None')).toBeNull()
  })
})
