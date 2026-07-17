// @vitest-environment jsdom
/**
 * The controls panel's clear-all status and the Release button: the "clear"
 * link appears for a hand-picked selection OR a teacher highlight (and fires
 * the one shared reset), and Release stays enabled with nothing pinned — it
 * doubles as "re-settle the layout".
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

describe('GraphControls clear-all status', () => {
  it('shows nothing when neither a selection nor a highlight is active', () => {
    render(<GraphControls {...makeProps()} />)
    expect(screen.queryByText('clear')).toBeNull()
  })

  it('shows "lit" with the clear link when only a teacher highlight is active', () => {
    const onClearAll = vi.fn()
    render(<GraphControls {...makeProps({ litCount: 3, onClearAll })} />)
    expect(screen.getByText('lit', { exact: false })).toBeTruthy()
    fireEvent.click(screen.getByText('clear'))
    expect(onClearAll).toHaveBeenCalledTimes(1)
  })

  it('prefers the picked count when both are active', () => {
    render(<GraphControls {...makeProps({ selectedCount: 2, litCount: 3 })} />)
    expect(screen.getByText('picked', { exact: false })).toBeTruthy()
    expect(screen.queryByText('lit', { exact: false })).toBeNull()
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
