// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention dropdown's rows: a title over `authors • venue • year`, and
 * one highlight state shared by mouse and keyboard.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MentionPaper } from '../../src/api'
import MentionSuggestions from '../../src/mentions/MentionSuggestions'

const PAPERS: MentionPaper[] = [
  {
    id: 'p1',
    arxiv_id: '1312.5602',
    title: 'Playing Atari with Deep RL',
    authors: 'Mnih et al.',
    venue: 'NeurIPS',
    year: 2013,
  },
  { id: 'p2', arxiv_id: null, title: 'Dueling DQN', authors: null, venue: null, year: null },
]

afterEach(cleanup)

describe('MentionSuggestions', () => {
  it('shows the title over an authors • venue • year byline', () => {
    render(
      <MentionSuggestions
        papers={PAPERS}
        highlighted={0}
        loading={false}
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Playing Atari with Deep RL')).toBeTruthy()
    expect(screen.getByText('Mnih et al. • NeurIPS • 2013')).toBeTruthy()
  })

  it('renders no orphaned separators for a sparse record', () => {
    // A provider hit can arrive with no authors, venue or year at all; the
    // byline must then be absent rather than a row of bullets.
    render(
      <MentionSuggestions
        papers={[PAPERS[1]]}
        highlighted={0}
        loading={false}
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.queryByText(/•/)).toBeNull()
  })

  it('marks the highlighted row for assistive tech, not just visually', () => {
    render(
      <MentionSuggestions
        papers={PAPERS}
        highlighted={1}
        loading={false}
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    const rows = screen.getAllByRole('option')
    expect(rows[0].getAttribute('aria-selected')).toBe('false')
    expect(rows[1].getAttribute('aria-selected')).toBe('true')
  })

  it('picks on pointer-DOWN, not click', () => {
    // The composer's blur closes the panel, which would unmount the row before
    // a click could ever land on it.
    const onPick = vi.fn()
    render(
      <MentionSuggestions
        papers={PAPERS}
        highlighted={0}
        loading={false}
        onPick={onPick}
        onHighlight={() => {}}
      />,
    )
    fireEvent.mouseDown(screen.getByText('Dueling DQN'))
    expect(onPick).toHaveBeenCalledWith(PAPERS[1])
  })

  it('moves the keyboard selection on hover, so the two never disagree', () => {
    const onHighlight = vi.fn()
    render(
      <MentionSuggestions
        papers={PAPERS}
        highlighted={0}
        loading={false}
        onPick={() => {}}
        onHighlight={onHighlight}
      />,
    )
    fireEvent.mouseEnter(screen.getAllByRole('option')[1])
    expect(onHighlight).toHaveBeenCalledWith(1)
  })

  it('says it is searching when a lookup is in flight with nothing yet', () => {
    render(
      <MentionSuggestions
        papers={[]}
        highlighted={0}
        loading
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Searching…')).toBeTruthy()
  })
})
