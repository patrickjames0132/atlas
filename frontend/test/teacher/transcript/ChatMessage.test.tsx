// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * A chat turn carrying a lecture: its beats, the caret that folds them, the
 * line saying which assistant produced it, and the account a turn gives of
 * itself once the reader has moved to another graph.
 *
 * Two things are pinned hardest. The *correction affordance*, because it is
 * what makes routing by model affordable at all — a misroute has to cost one
 * click, not a wrong answer the reader must notice. And the *graph line*,
 * which is the only thing that can explain a turn whose citations have gone
 * grey: the app degrades correctly across a graph switch but says nothing
 * about why, and this is the half that says why.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { Beat, ChatMsg } from '../../../src/api'
import ChatMessage from '../../../src/teacher/transcript/ChatMessage'

const BEAT: Beat = { heading: 'Where it started', text: 'The first idea.', node_ids: ['n1'] }
const LATER: Beat = { heading: 'What came next', text: 'The second idea.', node_ids: ['n2'] }

/** The graph stamp a turn carries, naming what it was answered over. */
const GRAPH = { seedId: 'seed-attention', seedTitle: 'Attention Is All You Need', nodes: 14 }

/** One assistant turn; override per test. */
const turn = (overrides: Partial<ChatMsg> = {}): ChatMsg => ({
  role: 'assistant',
  text: '',
  ...overrides,
})

afterEach(cleanup)

describe('a turn whose answer is a lecture', () => {
  it('renders its beats where the prose would be', () => {
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], routedTo: 'lecture' })}
        active={false}
        streaming={false}
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText('Where it started')).toBeTruthy()
    expect(screen.getByText('The first idea.')).toBeTruthy()
  })

  it('shows no thinking dots once beats are arriving', () => {
    // The turn's `text` stays empty for a lecture, which is exactly the
    // condition the placeholder dots key off — so beats have to suppress them
    // or every lecture streams under a "Thinking" line that never resolves.
    const { container } = render(
      <ChatMessage
        message={turn({ beats: [BEAT] })}
        active={false}
        streaming
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.hop-dots')).toBeNull()
  })

  it('still shows the dots before the first beat lands', () => {
    const { container } = render(
      <ChatMessage message={turn()} active={false} streaming onEnlarge={() => {}} />,
    )
    expect(container.querySelector('.hop-dots')).toBeTruthy()
  })

  it('lights a clicked beat without also re-lighting the whole answer', () => {
    // Both handlers hang off nested elements. A beat click that bubbled would
    // light the beat and then immediately replace its highlight with the
    // turn's own cited set.
    const onBeatClick = vi.fn()
    const onActivate = vi.fn()
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], cited: ['n1'] })}
        active={false}
        streaming={false}
        onActivate={onActivate}
        onBeatClick={onBeatClick}
        onEnlarge={() => {}}
      />,
    )
    fireEvent.click(screen.getByText('Where it started'))
    expect(onBeatClick).toHaveBeenCalledWith(0, BEAT)
    expect(onActivate).not.toHaveBeenCalled()
  })
})

describe("a lecture turn's caret", () => {
  it('names how many beats it holds', () => {
    render(
      <ChatMessage
        message={turn({ beats: [BEAT, LATER] })}
        active={false}
        streaming={false}
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: /2 beats/ })).toBeTruthy()
  })

  it('hides the beats when folded, without unmounting them', () => {
    // `hidden` rather than unmounted so a folded lecture keeps its figures
    // loaded — unfolding is instant instead of a flash of re-fetched images.
    const { container } = render(
      <ChatMessage
        message={turn({ beats: [BEAT] })}
        active={false}
        streaming={false}
        beatsOpen={false}
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.beats-toggle')?.getAttribute('aria-expanded')).toBe('false')
    expect(screen.getByText('Where it started')).toBeTruthy()
    expect((container.querySelector('.chat-beats > div[hidden]') as HTMLElement)?.hidden).toBe(true)
  })

  it('shows them open by default, so a caller that forgets cannot hide a lecture', () => {
    const { container } = render(
      <ChatMessage
        message={turn({ beats: [BEAT] })}
        active={false}
        streaming={false}
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.beats-toggle')?.getAttribute('aria-expanded')).toBe('true')
  })

  it('folds without re-lighting the answer underneath', () => {
    const onToggleBeats = vi.fn()
    const onActivate = vi.fn()
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], cited: ['n1'] })}
        active={false}
        streaming={false}
        onActivate={onActivate}
        onToggleBeats={onToggleBeats}
        onEnlarge={() => {}}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /1 beat/ }))
    expect(onToggleBeats).toHaveBeenCalledOnce()
    expect(onActivate).not.toHaveBeenCalled()
  })

  it('gives a lecture its own grounding line, since it has no provenance', () => {
    // The backend's provenance counts tool calls and a lecture makes none, so
    // a lecture turn used to carry no footer at all. What it covered is the
    // honest equivalent of what an answer cited.
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], graph: GRAPH })}
        active={false}
        streaming={false}
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText(/narrated 14 papers/)).toBeTruthy()
  })
})

describe('the graph a turn came from', () => {
  it('names it once the reader is looking at a different graph', () => {
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], graph: GRAPH })}
        active={false}
        streaming={false}
        currentSeedId="seed-dqn"
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText(/From the “Attention Is All You Need” graph/)).toBeTruthy()
  })

  it('says nothing while that graph is the one on screen', () => {
    // The reader is looking at it. A line repeating the title under every turn
    // would be noise; what earns the line is the discrimination.
    const { container } = render(
      <ChatMessage
        message={turn({ beats: [BEAT], graph: GRAPH })}
        active={false}
        streaming={false}
        currentSeedId="seed-attention"
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.chat-graph')).toBeNull()
  })

  it('says nothing graph-free, where there is nothing to differ from', () => {
    const { container } = render(
      <ChatMessage
        message={turn({ text: 'From your library.', graph: GRAPH })}
        active={false}
        streaming={false}
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.chat-graph')).toBeNull()
  })

  it('says nothing on a turn saved before the stamp existed', () => {
    const { container } = render(
      <ChatMessage
        message={turn({ beats: [BEAT] })}
        active={false}
        streaming={false}
        currentSeedId="seed-dqn"
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.chat-graph')).toBeNull()
  })

  it('names the graph on a researcher answer too, not just a lecture', () => {
    render(
      <ChatMessage
        message={turn({ text: 'Because [1].', cited: ['n1'], graph: GRAPH })}
        active={false}
        streaming={false}
        currentSeedId="seed-dqn"
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText(/From the “Attention Is All You Need” graph/)).toBeTruthy()
  })
})

describe('the route line', () => {
  it('names the assistant that answered and offers the other one', () => {
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], routedTo: 'lecture' })}
        active={false}
        streaming={false}
        onReroute={() => {}}
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText('Answered as a lecture')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Answer it instead' })).toBeTruthy()
  })

  it('offers the lecturer on a turn the router sent to the researcher', () => {
    render(
      <ChatMessage
        message={turn({ text: 'Attention weights tokens.', routedTo: 'answer' })}
        active={false}
        streaming={false}
        onReroute={() => {}}
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText('Answered as a question')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Lecture on it instead' })).toBeTruthy()
  })

  it('says nothing on a turn no model routed', () => {
    // The Lecture button, a correction the reader already made, every turn
    // saved before v7.20.0. There was no decision, so there is nothing to
    // account for or undo.
    const { container } = render(
      <ChatMessage
        message={turn({ text: 'An answer.' })}
        active={false}
        streaming={false}
        onReroute={() => {}}
        onEnlarge={() => {}}
      />,
    )
    expect(container.querySelector('.chat-routed')).toBeNull()
  })

  it('still accounts for the route when the offer is withheld', () => {
    // `onReroute` is undefined while another turn is streaming: the reader
    // cannot act yet, but the turn must still say what happened to it.
    render(
      <ChatMessage
        message={turn({ beats: [BEAT], routedTo: 'lecture' })}
        active={false}
        streaming={false}
        onEnlarge={() => {}}
      />,
    )
    expect(screen.getByText('Answered as a lecture')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Answer it instead' })).toBeNull()
  })

  it('corrects the route without re-lighting the answer underneath', () => {
    const onReroute = vi.fn()
    const onActivate = vi.fn()
    render(
      <ChatMessage
        message={turn({ text: 'An answer.', routedTo: 'answer', cited: ['n1'] })}
        active={false}
        streaming={false}
        onActivate={onActivate}
        onReroute={onReroute}
        onEnlarge={() => {}}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Lecture on it instead' }))
    expect(onReroute).toHaveBeenCalledOnce()
    expect(onActivate).not.toHaveBeenCalled()
  })
})
