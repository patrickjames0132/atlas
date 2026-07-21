// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The color legend never explains marks that aren't on screen: the four
 * relation entries are static, the two agent entries appear on first use.
 * (Similar was retired from the seed-graph build in v5.0.0 — no legend entry.)
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import Legend from '../../../src/graph/controls/Legend'

describe('Legend', () => {
  it('always shows the four relation entries', () => {
    render(<Legend hasDiscovered={false} hasSearchHits={false} />)
    for (const label of ['Seed', 'References', 'Field Landmarks', 'Latest Publications']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
  })

  it('no longer shows a Similar entry (relation retired from the build)', () => {
    render(<Legend hasDiscovered={false} hasSearchHits={false} />)
    expect(screen.queryByText('Similar')).toBeNull()
  })

  it('hides the agent entries until the agent has actually acted', () => {
    render(<Legend hasDiscovered={false} hasSearchHits={false} />)
    expect(screen.queryByText('Discovered by teacher')).toBeNull()
    expect(screen.queryByText('Found by search')).toBeNull()
  })

  it('shows each agent entry once its flag flips', () => {
    render(<Legend hasDiscovered={true} hasSearchHits={true} />)
    expect(screen.getByText('Discovered by teacher')).toBeTruthy()
    expect(screen.getByText('Found by search')).toBeTruthy()
  })
})
