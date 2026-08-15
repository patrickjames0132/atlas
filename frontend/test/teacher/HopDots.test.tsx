/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The shared "working on it" indicator. The animation itself is CSS and not
 * observable here; what IS worth pinning is the accessibility contract, which
 * is the component's only branch — the dots are the whole message on some
 * surfaces and pure decoration on others, and getting that backwards either
 * silences a wait or announces it twice.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import HopDots from '../../src/teacher/HopDots'

afterEach(cleanup)

describe('HopDots', () => {
  it('announces itself when the dots are the only thing saying what is happening', () => {
    render(<HopDots label="Thinking" />)
    expect(screen.getByRole('img', { name: 'Thinking' })).toBeTruthy()
  })

  it('stays silent inside a control that already names the state', () => {
    // The send button becomes "Stop generating" while streaming; dots with
    // their own name would make a screen reader say it twice.
    const { container } = render(<HopDots />)
    const dots = container.querySelector('.hop-dots')
    expect(dots?.getAttribute('aria-hidden')).toBe('true')
    expect(dots?.getAttribute('role')).toBeNull()
  })

  it('renders three dots — the stagger in teacher.css assumes exactly three', () => {
    const { container } = render(<HopDots />)
    expect(container.querySelectorAll('.hop-dot').length).toBe(3)
  })
})
