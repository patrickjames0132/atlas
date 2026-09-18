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
 * went in v7.21.0 when a `/lecture` command replaced the button, which left a lone
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
import type { MentionPaper } from '../../src/api'
import type { MentionThread } from '../../src/mentions/parse'
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

/** What the last whole-turn click asked to light — see the lecture-bubble test. */
const onChatClick = vi.fn()
/** The three destinations a submit can reach, spied — see the Enter tests. */
const onPaperSeed = vi.fn()
const send = vi.fn()
const runSearch = vi.fn()

vi.mock('../../src/teacher/useConversation', () => ({
  useConversation: () => ({
    hasGraph,
    asking: false,
    error: null,
    activeChat: null,
    activeChatBeat: null,
    onChatBeatClick: () => {},
    onChatClick,
    onRefClick: () => {},
    onGraphIds: new Set<string>(),
    onPaperSeed,
    provider: 's2',
    ask: () => {},
    send,
    reroute: () => {},
    lectureInChat: () => {},
    retryAnswer: () => {},
    stopAsk: () => {},
    clearChat: () => {},
  }),
}))

vi.mock('../../src/search/useDirectSearch', () => ({
  useDirectSearch: () => ({ searching: false, runSearch }),
}))

/** The `@` dropdown's state, set per test: what is open, and what is chosen. */
const mentionState: {
  open: boolean
  active: { query: string; start: number; end: number; whole: boolean } | null
  choice: { kind: 'paper'; paper: MentionPaper } | { kind: 'thread'; thread: MentionThread } | null
} = { open: false, active: null, choice: null }

vi.mock('../../src/mentions/useMentionSuggestions', () => ({
  useMentionSuggestions: () => ({
    get open() {
      return mentionState.open
    },
    get active() {
      return mentionState.active
    },
    get choice() {
      return mentionState.choice
    },
    threads: [],
    papers: [],
    loading: false,
    step: null,
    highlighted: -1,
    onInput: () => {},
    move: () => {},
    setHighlighted: () => {},
    dismiss: () => {},
    reset: () => {},
  }),
}))

// Imported after the mocks so the component picks them up.
const { default: Teacher } = await import('../../src/teacher/Teacher')

beforeEach(() => {
  hasGraph = true
  sources = []
  turns = []
  onChatClick.mockClear()
  onPaperSeed.mockClear()
  send.mockClear()
  runSearch.mockClear()
  Object.assign(mentionState, { open: false, active: null, choice: null })
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})

describe('the docked assistant panel', () => {
  it('has no lecture UI left — it is asked for in words now', () => {
    // The whole section went in v7.21.0: no Play button, no Summary|History
    // pair, no caret to unfold. A lecture is "lecture me on these" typed into
    // the bar (v7.21.0's `/lecture` command went too, in v7.23.0). `stagedOpen`
    // is passed because it used to be what revealed this section for the tour
    // — if any of it came back, this is where it would show up.
    render(<Teacher onClose={() => {}} stagedOpen />)
    expect(screen.queryByRole('button', { name: 'Play the lecture' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Lecture/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Summary' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'History' })).toBeNull()
    expect(screen.queryByRole('group', { name: 'How to frame the lecture' })).toBeNull()
  })

  it('lights every beat\u2019s papers when the lecture bubble itself is clicked', () => {
    // A lecture turn has no `cited` list — its papers live on the beats — so
    // the bubble used to be the one assistant turn that was not a control.
    // Clicking it lights the whole scope, deduped; a beat still lights its own.
    const beat = (heading: string, nodeIds: string[]) => ({
      heading,
      text: 'A beat.',
      node_ids: nodeIds,
    })
    turns = [
      turnStarted('lecture me on the references'),
      chatBeatAdded(beat('Origins', ['r1', 'r2'])),
      chatBeatAdded(beat('Aftermath', ['r2', 'r3'])),
    ]
    const { container } = render(<Teacher onClose={() => {}} />)
    const bubble = container.querySelector('.chat.assistant')!
    expect(bubble.classList.contains('clickable')).toBe(true)
    fireEvent.click(bubble)
    expect(onChatClick).toHaveBeenCalledWith(1, ['r1', 'r2', 'r3'])
  })

  it('keeps the newest lecture open and folds the ones behind it', () => {
    // Twelve beats are fine as the newest thing on screen and unusable as the
    // third lecture you have scrolled past — and the Lecture section that
    // could once fold them away is gone. The rule is a fact about the whole
    // conversation, which is why the default is derived here rather than
    // stored per turn.
    const beat = (heading: string) => ({ heading, text: 'A beat.', node_ids: [] })
    turns = [
      turnStarted('lecture me on these'),
      chatBeatAdded(beat('First lecture')),
      turnStarted('lecture me on the history of these'),
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
      turnStarted('lecture me on these'),
      chatBeatAdded(beat('First lecture')),
      turnStarted('lecture me on the history of these'),
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
    // covers, and the `/lecture` command menu that replaced it went in
    // v7.23.0. This hint and the placeholder are now the only places a
    // first-time reader learns lectures exist — and that a message can say
    // which papers.
    render(<Teacher onClose={() => {}} />)
    expect(screen.getByText(/ask for a lecture on them/)).toBeTruthy()
    expect(screen.getByPlaceholderText(/or for a lecture/)).toBeTruthy()
  })

  it('has no `/` command menu any more', () => {
    const { container } = render(<Teacher onClose={() => {}} />)
    const field = screen.getByLabelText('Ask the assistant a question') as HTMLTextAreaElement
    fireEvent.change(field, { target: { value: '/lec' } })
    expect(container.querySelector('.command-menu')).toBeNull()
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

describe('Enter in the composer, with the @ dropdown open', () => {
  const atari: MentionPaper = {
    id: 'p1',
    arxiv_id: '1312.5602',
    title: 'Playing Atari with Deep RL',
  }

  /**
   * Type into the composer and press a key with the dropdown in a given state.
   *
   * @param text  The draft.
   * @param key   The key to press.
   * @param state The dropdown's open/chosen state during the press.
   * @returns The textarea, for reading what the press left behind.
   */
  function press(text: string, key: string, state: Partial<typeof mentionState>) {
    render(<Teacher landing={false} />)
    const field = screen.getByRole('textbox', { name: /Ask the assistant/ })
    fireEvent.change(field, { target: { value: text } })
    Object.assign(mentionState, state)
    fireEvent.keyDown(field, { key })
    return field as HTMLTextAreaElement
  }

  it('with NO row chosen, sends what was typed — a bare @phrase to the scout', () => {
    // The fix for "Enter loaded a graph": an untouched list has no
    // selection, so Enter is a send, and a bare mention is a search.
    press('@sparse autoencoders', 'Enter', {
      open: true,
      active: { query: 'sparse autoencoders', start: 0, end: 20, whole: true },
      choice: null,
    })
    expect(runSearch).toHaveBeenCalledWith('sparse autoencoders')
    expect(onPaperSeed).not.toHaveBeenCalled()
  })

  it('on a chosen paper that is the whole message, opens it in ONE press', () => {
    // Completing `@Title` into the box and demanding a second Enter was a
    // step with no decision in it.
    const field = press('@atari', 'Enter', {
      open: true,
      active: { query: 'atari', start: 0, end: 6, whole: true },
      choice: { kind: 'paper', paper: atari },
    })
    expect(onPaperSeed).toHaveBeenCalledTimes(1)
    expect(onPaperSeed).toHaveBeenCalledWith('1312.5602')
    expect(field.value).toBe('')
    expect(runSearch).not.toHaveBeenCalled()
  })

  it('Tab on that same paper only completes the text', () => {
    // The escape hatch: the title in the box, nothing sent.
    const field = press('@atari', 'Tab', {
      open: true,
      active: { query: 'atari', start: 0, end: 6, whole: true },
      choice: { kind: 'paper', paper: atari },
    })
    expect(onPaperSeed).not.toHaveBeenCalled()
    expect(field.value).toBe('@Playing Atari with Deep RL ')
  })

  it('on a chosen paper inside a sentence, completes it and waits for the question', () => {
    const field = press('what does @atari', 'Enter', {
      open: true,
      active: { query: 'atari', start: 10, end: 16, whole: false },
      choice: { kind: 'paper', paper: atari },
    })
    expect(onPaperSeed).not.toHaveBeenCalled()
    expect(send).not.toHaveBeenCalled()
    expect(field.value).toBe('what does @Playing Atari with Deep RL ')
  })

  it('on a chosen thread, completes it — a thread alone is not a message', () => {
    const field = press('@gen', 'Enter', {
      open: true,
      active: { query: 'gen', start: 0, end: 4, whole: true },
      choice: { kind: 'thread', thread: { id: 't1', title: 'General' } },
    })
    expect(send).not.toHaveBeenCalled()
    expect(field.value).toBe('@thread[General] ')
  })

  it('a sent @thread[…] mention goes to the assistant, never the scout', () => {
    press('@thread[General] what else came up?', 'Enter', { open: false })
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0]).toBe('@thread[General] what else came up?')
    expect(runSearch).not.toHaveBeenCalled()
  })
})
