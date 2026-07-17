// @vitest-environment jsdom
/**
 * The coach-mark tour: step walking, absent-target skipping, and the three
 * ways out. jsdom has no layout, so these tests build *presence* (targets in
 * the DOM) and drive the walking logic; pixel placement is a browser-pass
 * item. `checkVisibility` doesn't exist in jsdom — the component treats that
 * as visible, which is exactly what lets presence-based tests work.
 */

import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Tour from '../../src/tour/Tour'
import type { TourStep } from '../../src/tour/Tour'

afterEach(cleanup)

const STEPS: TourStep[] = [
  { target: '[data-tour="alpha"]', title: 'Alpha stop', body: 'About alpha.' },
  { target: '[data-tour="missing"]', title: 'Ghost stop', body: 'Never shown.' },
  { target: '[data-tour="omega"]', title: 'Omega stop', body: 'About omega.' },
]

/** Render the tour beside the target elements the steps point at. */
function renderTour(onClose = vi.fn()) {
  const view = render(
    <div>
      <div data-tour="alpha" />
      <div data-tour="omega" />
      <Tour steps={STEPS} onClose={onClose} />
    </div>,
  )
  return { view, onClose }
}

describe('Tour', () => {
  it('skips steps whose target is absent and counts only real stops', () => {
    renderTour()
    expect(screen.getByText('Alpha stop')).toBeTruthy()
    expect(screen.getByText('1 / 2')).toBeTruthy()
    fireEvent.click(screen.getByText('Next'))
    // The ghost step never appears — the walk lands straight on omega.
    expect(screen.getByText('Omega stop')).toBeTruthy()
    expect(screen.getByText('2 / 2')).toBeTruthy()
  })

  it('walks Back, and Next becomes Done on the last stop', () => {
    const { onClose } = renderTour()
    const backButton = screen.getByText('Back') as HTMLButtonElement
    expect(backButton.disabled).toBe(true)
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Back'))
    expect(screen.getByText('Alpha stop')).toBeTruthy()
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Done'))
    expect(onClose).toHaveBeenCalledWith(true)
  })

  it('Skip tips and the ✕ both close without completing', () => {
    const first = renderTour()
    fireEvent.click(screen.getByText('Skip tips'))
    expect(first.onClose).toHaveBeenCalledWith(false)
    cleanup()
    const second = renderTour()
    fireEvent.click(screen.getByLabelText('Quit the tour'))
    expect(second.onClose).toHaveBeenCalledWith(false)
  })

  it('the jump select lists every stop and skips straight to the chosen one', () => {
    renderTour()
    const jump = screen.getByLabelText('Jump to a tip') as HTMLSelectElement
    // Only the real stops appear — the ghost step is not offered.
    expect(Array.from(jump.options).map((option) => option.text)).toEqual([
      '1. Alpha stop',
      '2. Omega stop',
    ])
    fireEvent.change(jump, { target: { value: '1' } })
    expect(screen.getByText('Omega stop')).toBeTruthy()
    expect(screen.getByText('2 / 2')).toBeTruthy()
    // And back again — the select is a two-way jump, not a forward skip.
    fireEvent.change(jump, { target: { value: '0' } })
    expect(screen.getByText('Alpha stop')).toBeTruthy()
  })

  it('Escape quits, arrow keys navigate', () => {
    const { onClose } = renderTour()
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByText('Omega stop')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByText('Alpha stop')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledWith(false)
  })

  it('closes immediately when no step has a target on screen', () => {
    const onClose = vi.fn()
    render(<Tour steps={STEPS.slice(1, 2)} onClose={onClose} />)
    expect(onClose).toHaveBeenCalledWith(false)
    expect(screen.queryByText('Ghost stop')).toBeNull()
  })

  it('a staged step opens its panel, waits for the target, and puts it away after', async () => {
    const staged: TourStep[] = [
      { target: '[data-tour="alpha"]', title: 'Alpha stop', body: 'About alpha.' },
      { target: '[data-tour="inner"]', stage: 'panel', title: 'Inner stop', body: 'In the panel.' },
      { target: '[data-tour="omega"]', title: 'Omega stop', body: 'About omega.' },
    ]
    const stages: (string | undefined)[] = []

    /** A caller that opens a "panel" (mounting the inner target) on demand. */
    function Harness() {
      const [stage, setStage] = useState<string | undefined>(undefined)
      return (
        <div>
          <div data-tour="alpha" />
          <div data-tour="omega" />
          {stage === 'panel' && <div data-tour="inner" />}
          <Tour
            steps={staged}
            onClose={vi.fn()}
            onStage={(next) => {
              stages.push(next)
              setStage(next)
            }}
          />
        </div>
      )
    }

    render(<Harness />)
    expect(screen.getByText('1 / 3')).toBeTruthy() // staged step counts up front
    fireEvent.click(screen.getByText('Next'))
    // The panel mounts a beat after onStage — the tour polls until it lands.
    await waitFor(() => expect(screen.getByText('Inner stop')).toBeTruthy())
    expect(stages).toContain('panel')
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText('Omega stop')).toBeTruthy()
    expect(stages[stages.length - 1]).toBeUndefined() // moving on stages nothing
  })

  it('a staged step whose target never appears is dropped after the retry window', async () => {
    const staged: TourStep[] = [
      { target: '[data-tour="alpha"]', title: 'Alpha stop', body: 'About alpha.' },
      {
        target: '[data-tour="never"]',
        stage: 'panel',
        title: 'Never stop',
        body: 'No such panel.',
      },
      { target: '[data-tour="omega"]', title: 'Omega stop', body: 'About omega.' },
    ]
    render(
      <div>
        <div data-tour="alpha" />
        <div data-tour="omega" />
        <Tour steps={staged} onClose={vi.fn()} onStage={vi.fn()} />
      </div>,
    )
    fireEvent.click(screen.getByText('Next'))
    // Staged polling exhausts (~1.5s) and the stop drops; the walk lands on omega.
    await waitFor(() => expect(screen.getByText('Omega stop')).toBeTruthy(), { timeout: 4000 })
    expect(screen.getByText('2 / 2')).toBeTruthy()
  })

  it('presentIf gates a staged step by its proxy selector', () => {
    const staged: TourStep[] = [
      { target: '[data-tour="alpha"]', title: 'Alpha stop', body: 'About alpha.' },
      {
        target: '[data-tour="inner"]',
        stage: 'panel',
        presentIf: '[data-tour="absent-toggle"]',
        title: 'Gated stop',
        body: 'Needs a toggle that is not there.',
      },
    ]
    render(
      <div>
        <div data-tour="alpha" />
        <Tour steps={staged} onClose={vi.fn()} onStage={vi.fn()} />
      </div>,
    )
    expect(screen.getByText('1 / 1')).toBeTruthy()
    expect(screen.getByText('Done')).toBeTruthy()
  })

  it('a swapped step list restarts the walk from its first stop', () => {
    // The caller switches phases mid-run (home tour -> graph tour when the
    // first graph lands): the new list must not inherit the old list's index.
    const onClose = vi.fn()
    const { rerender } = render(
      <div>
        <div data-tour="alpha" />
        <div data-tour="omega" />
        <Tour steps={STEPS} onClose={onClose} />
      </div>,
    )
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText('Omega stop')).toBeTruthy()
    const swapped: TourStep[] = [
      { target: '[data-tour="omega"]', title: 'Fresh stop', body: 'A new tour.' },
      { target: '[data-tour="alpha"]', title: 'Second stop', body: 'Its second stop.' },
    ]
    rerender(
      <div>
        <div data-tour="alpha" />
        <div data-tour="omega" />
        <Tour steps={swapped} onClose={onClose} />
      </div>,
    )
    expect(screen.getByText('Fresh stop')).toBeTruthy()
    expect(screen.getByText('1 / 2')).toBeTruthy()
  })
})
