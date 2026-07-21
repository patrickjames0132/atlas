// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The controls panel's action row and count readout: the Clear button arms
 * for a hand-picked selection OR a teacher highlight (and fires the one
 * shared reset), the shared readout flips between "papers shown" and
 * "papers selected" in the footer and collapsed bar alike, and Release
 * stays enabled with nothing pinned — it doubles as "re-settle the
 * layout". Plus the header's collapse-to-a-bar: the body hides (but stays
 * in the DOM for the tour's existence checks) and the tour's 'controls'
 * staging re-expands a collapsed panel.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import GraphControls from '../../../src/graph/controls/GraphControls'
import type { GraphControlsProps } from '../../../src/graph/controls/GraphControls'

/** Full prop set with inert defaults; override what a case exercises. */
function makeProps(overrides: Partial<GraphControlsProps> = {}): GraphControlsProps {
  return {
    layout: 'force',
    onLayout: () => {},
    enabled: new Set(['reference', 'citation', 'latest']),
    onToggleType: () => {},
    minYear: 2000,
    maxYear: 2026,
    yearLo: 2000,
    yearHi: 2026,
    onYearLo: () => {},
    onYearHi: () => {},
    minCitations: 0,
    maxCitations: 100,
    citeLo: 0,
    citeHi: 24,
    onCiteLo: () => {},
    onCiteHi: () => {},
    visibleCount: 10,
    totalCount: 12,
    selectedCount: 0,
    litCount: 0,
    onClearAll: () => {},
    pinnedCount: 0,
    onReleaseAll: () => {},
    onFit: () => {},
    onRefresh: () => {},
    refreshing: false,
    providerNote: null,
    ...overrides,
  }
}

// No test globals in this suite, so RTL's auto-cleanup never registers —
// unmount between tests explicitly or renders accumulate in the document.
afterEach(cleanup)

describe('GraphControls Clear button', () => {
  it('sits disabled in the action row until something is lit', () => {
    render(<GraphControls {...makeProps()} />)
    const clear = screen.getByRole('button', { name: 'Clear' })
    expect(clear.hasAttribute('disabled')).toBe(true)
  })

  it('arms for a teacher highlight alone and fires the one shared reset', () => {
    const onClearAll = vi.fn()
    render(<GraphControls {...makeProps({ litCount: 3, onClearAll })} />)
    const clear = screen.getByRole('button', { name: 'Clear' })
    expect(clear.hasAttribute('disabled')).toBe(false)
    fireEvent.click(clear)
    expect(onClearAll).toHaveBeenCalledTimes(1)
  })

  it('arms for a hand-picked selection alone', () => {
    render(<GraphControls {...makeProps({ selectedCount: 2 })} />)
    expect(screen.getByRole('button', { name: 'Clear' }).hasAttribute('disabled')).toBe(false)
  })
})

describe('GraphControls count readout', () => {
  it('reads "papers shown" in the footer under bare filters', () => {
    render(<GraphControls {...makeProps()} />)
    expect(screen.getByText('10 / 12 papers shown')).toBeTruthy()
  })

  it('flips to the selected count (out of the shown papers) during a hand-pick', () => {
    render(<GraphControls {...makeProps({ selectedCount: 2 })} />)
    expect(screen.getByText('2 / 10 papers selected')).toBeTruthy()
    expect(screen.queryByText('10 / 12 papers shown')).toBeNull()
  })
})

describe('GraphControls collapse', () => {
  it('collapses to the slim header bar (body hidden, not unmounted) and back', () => {
    const { container } = render(<GraphControls {...makeProps()} />)
    const head = screen.getByRole('button', { name: /Graph controls/ })
    const body = container.querySelector('.ctrl-body')!
    expect(head.getAttribute('aria-expanded')).toBe('true')
    expect(body.hasAttribute('hidden')).toBe(false)

    fireEvent.click(head)
    expect(head.getAttribute('aria-expanded')).toBe('false')
    // Hidden, NOT unmounted — the tour's presentIf existence checks rely on
    // the year/citation targets staying in the DOM while collapsed.
    expect(body.hasAttribute('hidden')).toBe(true)
    expect(container.querySelector('[data-tour="years"]')).not.toBeNull()
    // The visible-count readout rides the collapsed bar, unit and all.
    expect(head.textContent).toContain('10 / 12 papers shown')

    fireEvent.click(head)
    expect(body.hasAttribute('hidden')).toBe(false)
    expect(head.textContent).not.toContain('10 / 12 papers shown')
  })

  it('reports the hand-picked selection in the collapsed bar, and reverts on clear', () => {
    const { rerender } = render(<GraphControls {...makeProps({ selectedCount: 3 })} />)
    const head = screen.getByRole('button', { name: /Graph controls/ })
    fireEvent.click(head)
    expect(head.textContent).toContain('3 / 10 papers selected')

    // Deselecting all hands the bar back to the visible-count readout.
    rerender(<GraphControls {...makeProps({ selectedCount: 0 })} />)
    expect(head.textContent).toContain('10 / 12 papers shown')
    expect(head.textContent).not.toContain('selected')
  })

  it('re-expands when the tour stages the panel open', () => {
    const { container, rerender } = render(<GraphControls {...makeProps()} />)
    fireEvent.click(screen.getByRole('button', { name: /Graph controls/ }))
    const body = container.querySelector('.ctrl-body')!
    expect(body.hasAttribute('hidden')).toBe(true)

    rerender(<GraphControls {...makeProps({ stagedOpen: true })} />)
    expect(body.hasAttribute('hidden')).toBe(false)
  })
})

describe('GraphControls Release button', () => {
  it('stays enabled with nothing pinned and fires the release/reheat', () => {
    const onReleaseAll = vi.fn()
    render(<GraphControls {...makeProps({ pinnedCount: 0, onReleaseAll })} />)
    const release = screen.getByRole('button', { name: /Release/ })
    expect(release.hasAttribute('disabled')).toBe(false)
    fireEvent.click(release)
    expect(onReleaseAll).toHaveBeenCalledTimes(1)
  })
})

describe('per-chip count sliders', () => {
  const withCaps = {
    showRelCaps: true,
    relTotals: { reference: 40, citation: 120, latest: 30 },
  }

  it('shows no sliders while the build is adaptive', () => {
    // The default: the backend already sized the graph, so there is nothing
    // for a second trim to do.
    render(<GraphControls {...makeProps({ relTotals: withCaps.relTotals })} />)
    expect(screen.queryByRole('slider', { name: /References shown/i })).toBeNull()
  })

  it('gives each enabled relation a slider once sizing is user-controlled', () => {
    render(<GraphControls {...makeProps(withCaps)} />)
    expect(screen.getByRole('slider', { name: /References shown/i })).toBeTruthy()
    expect(screen.getByRole('slider', { name: /Field Landmarks shown/i })).toBeTruthy()
  })

  it('bounds a slider by that relation and defaults to showing all of it', () => {
    render(<GraphControls {...makeProps(withCaps)} />)
    const slider = screen.getByRole('slider', { name: /References shown/i }) as HTMLInputElement
    expect(slider.max).toBe('40')
    expect(slider.min).toBe('1') // never trims to nothing
    expect(slider.value).toBe('40') // no cap set -> the whole relation
  })

  it('reports the cap as a fraction of the relation', () => {
    render(<GraphControls {...makeProps({ ...withCaps, relCaps: { reference: 12 } })} />)
    expect(screen.getByText('12/40')).toBeTruthy()
  })

  it('reports the chosen cap upward', () => {
    const onRelCap = vi.fn()
    render(<GraphControls {...makeProps({ ...withCaps, onRelCap })} />)
    fireEvent.change(screen.getByRole('slider', { name: /References shown/i }), {
      target: { value: '15' },
    })
    expect(onRelCap).toHaveBeenCalledWith('reference', 15)
  })

  it('drops the slider for a relation whose chip is off', () => {
    // A cap on a hidden relation would trim nothing visible.
    render(
      <GraphControls {...makeProps({ ...withCaps, enabled: new Set(['citation', 'latest']) })} />,
    )
    expect(screen.queryByRole('slider', { name: /References shown/i })).toBeNull()
    expect(screen.getByRole('slider', { name: /Field Landmarks shown/i })).toBeTruthy()
  })

  it('drops the slider for a relation with nothing to trim', () => {
    render(<GraphControls {...makeProps({ ...withCaps, relTotals: { reference: 1 } })} />)
    expect(screen.queryByRole('slider', { name: /References shown/i })).toBeNull()
  })

  it('keeps the chip as a working toggle even in caps mode', () => {
    // The chip is now the slider's label, but it must still fire the on/off
    // toggle — that's the whole reason it stayed a button.
    const onToggleType = vi.fn()
    render(<GraphControls {...makeProps({ ...withCaps, onToggleType })} />)
    fireEvent.click(screen.getByRole('button', { name: 'References' }))
    expect(onToggleType).toHaveBeenCalledWith('reference')
  })

  it('still shows the chip for a relation with no slider', () => {
    // Field Landmarks with a single paper: no slider, but the chip must remain
    // so it can still be toggled off/on.
    render(<GraphControls {...makeProps({ ...withCaps, relTotals: { citation: 1 } })} />)
    expect(screen.getByRole('button', { name: /Field Landmarks/i })).toBeTruthy()
    expect(screen.queryByRole('slider', { name: /Field Landmarks shown/i })).toBeNull()
  })
})
