// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention dropdown's rows: a title over `authors • venue • year`, the
 * sibling-thread section above the papers, and one highlight state shared by
 * mouse and keyboard across both.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MentionPaper } from '../../src/api'
import MentionSuggestions, { hintFor } from '../../src/mentions/MentionSuggestions'

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
        threads={[]}
        papers={PAPERS}
        highlighted={0}
        whole={false}
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
        threads={[]}
        papers={[PAPERS[1]]}
        highlighted={0}
        whole={false}
        loading={false}
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.queryByText(/•/)).toBeNull()
  })

  it('lists sibling threads in their own section above the papers', () => {
    const onPick = vi.fn()
    render(
      <MentionSuggestions
        threads={[{ id: 't1', title: 'PPO' }]}
        papers={PAPERS}
        highlighted={-1}
        whole={false}
        loading={false}
        onPick={onPick}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Discussions in this exploration')).toBeTruthy()
    expect(screen.getByText('All paper results')).toBeTruthy()
    const rows = screen.getAllByRole('option')
    expect(rows.map((row) => row.textContent)).toEqual([
      '💬PPO',
      '📄Playing Atari with Deep RLMnih et al. • NeurIPS • 2013',
      '📄Dueling DQN',
    ])
    fireEvent.mouseDown(screen.getByText('PPO'))
    expect(onPick).toHaveBeenCalledWith({ kind: 'thread', thread: { id: 't1', title: 'PPO' } })
  })

  it('numbers rows across both sections, so one highlight walks one list', () => {
    const onHighlight = vi.fn()
    render(
      <MentionSuggestions
        threads={[{ id: 't1', title: 'PPO' }]}
        papers={PAPERS}
        highlighted={1}
        whole={false}
        loading={false}
        onPick={() => {}}
        onHighlight={onHighlight}
      />,
    )
    const rows = screen.getAllByRole('option')
    // Row 1 is the FIRST paper, not the second: the thread took row 0.
    expect(rows[0].getAttribute('aria-selected')).toBe('false')
    expect(rows[1].getAttribute('aria-selected')).toBe('true')
    fireEvent.mouseEnter(screen.getByText('Dueling DQN'))
    expect(onHighlight).toHaveBeenCalledWith(2)
  })

  it('highlights nothing at -1 and says what Enter does', () => {
    // Nothing is pre-selected, so the reader needs telling that Enter sends
    // what they typed rather than grabbing the top row.
    render(
      <MentionSuggestions
        threads={[]}
        papers={PAPERS}
        highlighted={-1}
        whole
        loading={false}
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    for (const row of screen.getAllByRole('option')) {
      expect(row.getAttribute('aria-selected')).toBe('false')
    }
    expect(screen.getByText(/Enter searches for what you typed/)).toBeTruthy()
  })

  it('the hint follows the state: what Enter does right now', () => {
    // Enter has two jobs — send what I typed, take what I chose — told apart
    // only by whether a row is lit. The footer says which, every time.
    const thread = { id: 't1', title: 'PPO' }
    expect(hintFor(null, true)).toMatch(/^Enter searches for what you typed/)
    expect(hintFor(null, false)).toMatch(/^Enter sends your message/)
    expect(hintFor({ kind: 'paper', paper: PAPERS[0] }, true)).toMatch(/^Enter opens this paper/)
    expect(hintFor({ kind: 'paper', paper: PAPERS[0] }, false)).toBe(
      'Enter adds this paper to your question',
    )
    expect(hintFor({ kind: 'thread', thread }, true)).toBe('Enter attaches this discussion')
  })

  it('shows no paper section below the query floor, only the threads', () => {
    render(
      <MentionSuggestions
        threads={[{ id: 't1', title: 'PPO' }]}
        papers={[]}
        highlighted={-1}
        whole={false}
        loading={false}
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.queryByText('All paper results')).toBeNull()
    expect(screen.queryByText('Searching…')).toBeNull()
  })

  it('marks the highlighted row for assistive tech, not just visually', () => {
    render(
      <MentionSuggestions
        threads={[]}
        papers={PAPERS}
        highlighted={1}
        whole={false}
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
        threads={[]}
        papers={PAPERS}
        highlighted={0}
        whole={false}
        loading={false}
        onPick={onPick}
        onHighlight={() => {}}
      />,
    )
    fireEvent.mouseDown(screen.getByText('Dueling DQN'))
    expect(onPick).toHaveBeenCalledWith({ kind: 'paper', paper: PAPERS[1] })
  })

  it('moves the keyboard selection on hover, so the two never disagree', () => {
    const onHighlight = vi.fn()
    render(
      <MentionSuggestions
        threads={[]}
        papers={PAPERS}
        highlighted={0}
        whole={false}
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
        threads={[]}
        papers={[]}
        highlighted={0}
        whole={false}
        loading
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Searching…')).toBeTruthy()
  })

  it('shows the phase the server named, in place of a generic spinner text', () => {
    render(
      <MentionSuggestions
        threads={[]}
        papers={PAPERS}
        highlighted={0}
        whole={false}
        loading
        step="Working out which paper “dqn” is"
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Working out which paper “dqn” is')).toBeTruthy()
    expect(screen.queryByText('Searching…')).toBeNull()
  })

  it('shows the phase even with results already up', () => {
    // The provisional cached list lands first, so the reader needs to be able
    // to tell that more is still coming — and which phase is taking the time.
    render(
      <MentionSuggestions
        threads={[]}
        papers={PAPERS}
        highlighted={0}
        whole={false}
        loading
        step="Searching Semantic Scholar"
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Searching Semantic Scholar')).toBeTruthy()
    expect(screen.getByText('Playing Atari with Deep RL')).toBeTruthy()
  })

  it('falls back to a generic line before the first phase arrives', () => {
    render(
      <MentionSuggestions
        threads={[]}
        papers={[]}
        highlighted={0}
        whole={false}
        loading
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(screen.getByText('Searching…')).toBeTruthy()
  })

  it('announces the phase politely, without stealing focus from the textarea', () => {
    const { container } = render(
      <MentionSuggestions
        threads={[]}
        papers={[]}
        highlighted={0}
        whole={false}
        loading
        step="Looking in your library"
        onPick={() => {}}
        onHighlight={() => {}}
      />,
    )
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toBe(
      'Looking in your library',
    )
  })
})
