import explorationsReducer from '../../src/store/explorations'
// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The panel's structure, which is now **one shape rather than two**: the
 * conversation, with the ask-binding controls in a row under the bar, whether
 * or not a graph is open. What's pinned here is mostly what is *absent* — no
 * lecture UI, no folding sections — plus the derived fold rule for the
 * lectures that arrive as turns.
 *
 * Most of this file used to describe v7.10.0's split: a Lecture section
 * (folded by default, a Summary|History pair, one Play button, `stagedOpen`
 * unfolding it for the tour) above a Chat section, and the ask-binding
 * controls living in one of two homes depending on the shape. The lecture half
 * went in v7.21.0 when `/lecture` replaced the button, which left a lone
 * "CHAT" caret folding away the only thing in a panel already titled "AI
 * Teacher & Discovery" — so the sections went too, and with them the two-homes
 * rule. The negative assertions below are the point.
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
import transcriptReducer, { chatBeatAdded, turnStarted } from '../../src/store/transcript'
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
// Actions to play into the transcript before rendering, for tests that need
// turns on screen.
let turns: Parameters<typeof transcriptReducer>[1][] = []

/** The transcript slice with `turns` played into it. */
const transcript = () =>
  turns.reduce(
    (state, action) => transcriptReducer(state, action),
    transcriptReducer(undefined, { type: '@@test/init' }),
  )

/** Each slice at rest, which is all these tests need behind the selectors. */
const state = () => ({
  explorations: explorationsReducer(undefined, { type: '@@test/init' }),
  workspace: workspaceReducer(undefined, { type: '@@test/init' }),
  transcript: transcript(),
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
    asking: false,
    error: null,
    activeChat: null,
    activeChatBeat: null,
    onChatBeatClick: () => {},
    onChatClick: () => {},
    onRefClick: () => {},
    onGraphIds: new Set<string>(),
    onPaperSeed: () => {},
    provider: 's2',
    ask: () => {},
    send: () => {},
    reroute: () => {},
    lectureInChat: () => {},
    retryAnswer: () => {},
    stopAsk: () => {},
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
  turns = []
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})

describe('the docked assistant panel', () => {
  it('has no lecture UI left — it is a command now', () => {
    // The whole section went in v7.21.0: no Play button, no Summary|History
    // pair, no caret to unfold. A lecture is `/lecture summary` typed into the
    // bar, and the command menu is where a reader finds that out. `stagedOpen`
    // is passed because it used to be what revealed this section for the tour
    // — if any of it came back, this is where it would show up.
    render(<Teacher onClose={() => {}} stagedOpen />)
    expect(screen.queryByRole('button', { name: 'Play the lecture' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Lecture/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Summary' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'History' })).toBeNull()
    expect(screen.queryByRole('group', { name: 'How to frame the lecture' })).toBeNull()
  })

  it('keeps the newest lecture open and folds the ones behind it', () => {
    // Twelve beats are fine as the newest thing on screen and unusable as the
    // third lecture you have scrolled past — and the Lecture section that
    // could once fold them away is gone. The rule is a fact about the whole
    // conversation, which is why the default is derived here rather than
    // stored per turn.
    const beat = (heading: string) => ({ heading, text: 'A beat.', node_ids: [] })
    turns = [
      turnStarted('/lecture summary'),
      chatBeatAdded(beat('First lecture')),
      turnStarted('/lecture history'),
      chatBeatAdded(beat('Second lecture')),
    ]
    const { container } = render(<Teacher onClose={() => {}} />)

    const carets = container.querySelectorAll('.beats-toggle')
    expect(carets).toHaveLength(2)
    expect(carets[0].getAttribute('aria-expanded')).toBe('false')
    expect(carets[1].getAttribute('aria-expanded')).toBe('true')
  })

  it('lets the reader overrule that on a turn, without touching the others', () => {
    const beat = (heading: string) => ({ heading, text: 'A beat.', node_ids: [] })
    turns = [
      turnStarted('/lecture summary'),
      chatBeatAdded(beat('First lecture')),
      turnStarted('/lecture history'),
      chatBeatAdded(beat('Second lecture')),
    ]
    const { container } = render(<Teacher onClose={() => {}} />)

    const carets = () => container.querySelectorAll('.beats-toggle')
    fireEvent.click(carets()[0])
    expect(carets()[0].getAttribute('aria-expanded')).toBe('true')
    // The newest one is left exactly as it was: the reader asked about the
    // older lecture, not about this one.
    expect(carets()[1].getAttribute('aria-expanded')).toBe('true')
  })

  it('has no folding sections left, so the conversation IS the panel', () => {
    const { container } = render(<Teacher onClose={() => {}} />)
    expect(container.querySelector('.panel-section')).toBeNull()
    expect(container.querySelector('.section-toggle')).toBeNull()
    // Most of all: no caret whose job is folding away the whole panel.
    expect(screen.queryByRole('button', { name: /Chat/ })).toBeNull()
  })

  it('tells a reader with an empty conversation how to get a lecture', () => {
    // The deleted section carried a paragraph explaining what a lecture
    // covers. With it gone this hint and the command menu are the only places
    // a first-time reader learns lectures exist.
    render(<Teacher onClose={() => {}} />)
    expect(screen.getByText(/\/lecture/)).toBeTruthy()
  })

  it('has no 🎓 lecture scope, because there is nothing to opt out of', () => {
    // The picker asked whether the played lecture was fed to the researcher —
    // a question that only existed while a lecture sat outside the
    // conversation. A lecture is a turn now, so it is ordinary history.
    const { container } = render(<Teacher onClose={() => {}} />)
    expect(container.querySelector('[data-tour="lecture-scope"]')).toBeNull()
  })

  it('puts each ask-binding control where it belongs', () => {
    // Where a control sits is the claim being made about it. The 📚 source
    // scope is a chip under the bar — near what it modifies, out of the pill.
    // ▽ Filters is back INSIDE the bar (Patrick, 2026-09-14): it was moved out
    // in v7.11.0 when the pill held three controls and a textarea, and two of
    // those three have since gone (the 🔍 toggle to `@` in v7.18.0, the 🎓
    // scope in v7.21.0), so there is room for the one that binds the question
    // most directly. Neither is in the panel header, which would imply they
    // scope everything.
    sources = [SOURCE]
    const { container } = render(<Teacher onClose={() => {}} />)

    const tools = container.querySelector('.ask-tools')
    const bar = container.querySelector('form.teacher-ask')
    const scope = container.querySelector('[data-tour="source-scope"]')
    const filters = container.querySelector('[data-tour="search-filters"]')
    expect(tools?.contains(scope!)).toBe(true)
    expect(bar?.contains(scope!)).toBe(false)
    expect(bar?.contains(filters!)).toBe(true)
    for (const control of [scope, filters]) {
      expect(control).toBeTruthy()
      expect(container.querySelector('.teacher-head-right')?.contains(control!)).toBe(false)
    }
  })

  it('renders both in the same place with a graph and without one', () => {
    // Two homes until v7.21.0 — the Chat caret row docked, a row under the bar
    // on the landing surface — which only existed because docked there was a
    // row above to hang them off. There isn't one now, and one home each is
    // the simpler claim as well as the simpler code.
    sources = [SOURCE]
    const docked = render(<Teacher onClose={() => {}} />)
    expect(docked.container.querySelector('.ask-tools [data-tour="source-scope"]')).toBeTruthy()
    expect(
      docked.container.querySelector('form.teacher-ask [data-tour="search-filters"]'),
    ).toBeTruthy()
    cleanup()

    hasGraph = false
    const landing = render(<Teacher landing />)
    expect(landing.container.querySelector('.ask-tools [data-tour="source-scope"]')).toBeTruthy()
    expect(
      landing.container.querySelector('form.teacher-ask [data-tour="search-filters"]'),
    ).toBeTruthy()
  })
})

describe('the landing assistant', () => {
  it('keeps the source scope out of the pill', () => {
    // v7.11.0's rule, still standing for the scope: the box you type in should
    // look like a box you type in. ▽ Filters is the one exception, made
    // deliberately — see the docked test above.
    hasGraph = false
    sources = [SOURCE]
    const { container } = render(<Teacher landing />)

    const tools = container.querySelector('.ask-tools')
    const bar = container.querySelector('form.teacher-ask')
    const scope = container.querySelector('[data-tour="source-scope"]')
    expect(tools?.contains(scope!)).toBe(true)
    expect(bar?.contains(scope!)).toBe(false)
  })

  it('has no sections and no lecture control', () => {
    hasGraph = false
    const { container } = render(<Teacher landing />)
    expect(container.querySelector('.panel-section')).toBeNull()
    expect(screen.queryByRole('button', { name: /Lecture/ })).toBeNull()
  })
})
