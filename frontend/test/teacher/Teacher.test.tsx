// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The docked panel's sections — v7.10.0's split of one shared scroll into a
 * folding Lecture section and a folding Chat section. What's pinned here: the
 * lecture control starts folded behind its caret while the conversation starts
 * open, the tour unfolds both via `stagedOpen`, and the scope pickers sit on
 * the Chat row (whose reach they actually scope) rather than in the panel
 * header. With no graph there are no sections at all, and the source picker
 * falls back into the ask bar, where the composer is wide and the scope
 * belongs to the question.
 *
 * The store is mocked to a plain state object rather than wired to a real
 * one: every selector this component reads is a pure function of that state,
 * and the conversation engine behind it is the subject of its own tests.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { Source } from '../../src/api'
import highlightReducer from '../../src/store/highlight'
import libraryReducer from '../../src/store/library'
import transcriptReducer from '../../src/store/transcript'
import workspaceReducer from '../../src/store/workspace'

/** One uploaded source, enough for the scope picker to appear. */
const SOURCE: Source = {
  id: 'src-1',
  title: 'Deep Learning',
  kind: 'pdf',
  origin: 'deep-learning.pdf',
  pages: 800,
  n_chunks: 400,
  created_at: '2026-08-16T00:00:00Z',
}

// Whether a graph is open — flipped per test before rendering.
let hasGraph = true
// The uploaded library the panel sees.
let sources: Source[] = []

/** Each slice at rest, which is all these tests need behind the selectors. */
const state = () => ({
  workspace: workspaceReducer(undefined, { type: '@@test/init' }),
  transcript: transcriptReducer(undefined, { type: '@@test/init' }),
  highlight: highlightReducer(undefined, { type: '@@test/init' }),
  // `loaded` so the panel never dispatches its first-reader fetch.
  library: { ...libraryReducer(undefined, { type: '@@test/init' }), sources, loaded: true },
})

vi.mock('../../src/store', () => ({
  useAppDispatch: () => () => {},
  useAppSelector: (selector: (rootState: ReturnType<typeof state>) => unknown) => selector(state()),
}))

vi.mock('../../src/teacher/useConversation', () => ({
  useConversation: () => ({
    hasGraph,
    lecturing: false,
    asking: false,
    error: null,
    activeBeat: null,
    activeChat: null,
    onBeatClick: () => {},
    onChatClick: () => {},
    onRefClick: () => {},
    onGraphIds: new Set<string>(),
    onPaperSeed: () => {},
    provider: 's2',
    toggleLecture: () => {},
    ask: () => {},
    retryAnswer: () => {},
    stopAsk: () => {},
    clearLecture: () => {},
    clearChat: () => {},
  }),
}))

vi.mock('../../src/search/useDirectSearch', () => ({
  useDirectSearch: () => ({ searching: false, runSearch: () => {} }),
}))

// Imported after the mocks so the component picks them up.
const { default: Teacher } = await import('../../src/teacher/Teacher')

beforeEach(() => {
  hasGraph = true
  sources = []
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})

describe('the docked assistant panel', () => {
  it('starts with the lecture folded away, and opens it on the caret', () => {
    render(<Teacher onClose={() => {}} />)

    // Hidden, so out of the accessibility tree entirely.
    expect(screen.queryByRole('button', { name: 'Play the lecture' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /^Lecture/ }))
    expect(screen.getByRole('button', { name: 'Play the lecture' })).toBeTruthy()
  })

  it('offers ONE lecture control, not a mode per story', () => {
    // The v7.17.0 shape. The four mode buttons are gone; what a lecture covers
    // is the reader's on-screen scope, not a button they pick.
    render(<Teacher onClose={() => {}} stagedOpen />)
    for (const retired of [
      'How we got here',
      "This paper's intuition",
      "What's evolved since",
      'The current frontier',
    ]) {
      expect(screen.queryByRole('button', { name: retired })).toBeNull()
    }
    expect(screen.getByRole('button', { name: 'Play the lecture' })).toBeTruthy()
  })

  it('offers the two framings, defaulting to Summary', () => {
    // The reader's one remaining choice about a lecture: the scope says which
    // papers, framing says how to tell them. Summary leads because a
    // chronological arc is a strong claim about an arbitrary selection — and
    // forcing one is what produced beats about the timeline itself.
    render(<Teacher onClose={() => {}} stagedOpen />)
    const summary = screen.getByRole('button', { name: 'Summary' })
    const history = screen.getByRole('button', { name: 'History' })
    expect(summary.getAttribute('aria-pressed')).toBe('true')
    expect(history.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(history)
    expect(screen.getByRole('button', { name: 'History' }).getAttribute('aria-pressed')).toBe(
      'true',
    )
  })

  it('unfolds the lecture when the tour stages the panel open', () => {
    render(<Teacher onClose={() => {}} stagedOpen />)
    // No click needed — the tour's lecture step must land on something.
    expect(screen.getByRole('button', { name: 'Play the lecture' })).toBeTruthy()
  })

  it('opens with the conversation showing, and folds it on the caret', () => {
    const { container } = render(<Teacher onClose={() => {}} />)
    const body = () => container.querySelectorAll('.section-body')[1] as HTMLElement

    expect(body().hidden).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: /Chat/ }))
    expect(body().hidden).toBe(true)
  })

  it('hangs every ask-binding control off the Chat row, not the panel header', () => {
    // The scopes bind the researcher answering below, not the lecturer above,
    // and the search controls bind the same ask — so the row they sit on is
    // the claim being made about them. None of the four is in the bar itself.
    sources = [SOURCE]
    const { container } = render(<Teacher onClose={() => {}} />)

    const row = container.querySelector('.section-head-right')
    const bar = container.querySelector('form.teacher-ask')
    for (const anchor of ['source-scope', 'direct-search', 'search-filters']) {
      const control = container.querySelector(`[data-tour="${anchor}"]`)
      expect(control).toBeTruthy()
      expect(row?.contains(control!)).toBe(true)
      expect(bar?.contains(control!)).toBe(false)
    }
    const picker = container.querySelector('[data-tour="source-scope"]')
    expect(container.querySelector('.teacher-head-right')?.contains(picker!)).toBe(false)
  })
})

describe('the landing assistant', () => {
  it('puts the ask-binding controls in a row under the bar, never inside it', () => {
    // v7.11.0: the pill holds the question and nothing else. With no graph
    // there is no section row to hang these off, so they sit directly beneath.
    hasGraph = false
    sources = [SOURCE]
    const { container } = render(<Teacher landing />)

    const tools = container.querySelector('.ask-tools')
    const bar = container.querySelector('form.teacher-ask')
    expect(tools).toBeTruthy()
    for (const anchor of ['source-scope', 'direct-search', 'search-filters']) {
      const control = container.querySelector(`[data-tour="${anchor}"]`)
      expect(control).toBeTruthy()
      expect(tools?.contains(control!)).toBe(true)
      expect(bar?.contains(control!)).toBe(false)
    }
  })

  it('has no sections at all — nothing to narrate, so nothing to divide', () => {
    hasGraph = false
    const { container } = render(<Teacher landing />)
    expect(container.querySelector('.panel-section')).toBeNull()
    expect(screen.queryByRole('button', { name: /Lecture/ })).toBeNull()
  })
})
