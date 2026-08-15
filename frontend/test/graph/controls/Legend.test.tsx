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
    render(<Legend hasDiscovered={false} />)
    for (const label of ['Seed', 'References', 'Field Landmarks', 'Latest Publications']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
  })

  it('no longer shows a Similar entry (relation retired from the build)', () => {
    render(<Legend hasDiscovered={false} />)
    expect(screen.queryByText('Similar')).toBeNull()
  })

  it('hides the discovered entry until the agent has actually acted', () => {
    render(<Legend hasDiscovered={false} />)
    expect(screen.queryByText('Discovered by teacher')).toBeNull()
  })

  it('shows the discovered entry once its flag flips', () => {
    render(<Legend hasDiscovered={true} />)
    expect(screen.getByText('Discovered by teacher')).toBeTruthy()
  })

  // The legend lists what the graph can contain. A "Found by search" entry sat
  // here until v7.5.0, when the `search` and `similar` relations were removed
  // outright — an entry for a colour nothing can be is worse than no entry.
  it('no longer offers an entry for a retired relation', () => {
    render(<Legend hasDiscovered={true} />)
    expect(screen.queryByText('Found by search')).toBeNull()
  })
})
