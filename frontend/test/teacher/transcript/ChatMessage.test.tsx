// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * A chat turn the router placed (v7.20.0): a lecture rendered as the answer,
 * and the line that says which assistant produced it.
 *
 * What's pinned here is the *correction affordance*, because it is what makes
 * routing by model affordable at all — a misroute has to cost one click, not a
 * wrong answer the reader must notice. So: the offer names the other
 * assistant, it appears only on a turn a model routed, and it never fires the
 * bubble's own re-light handler underneath it.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { Beat, ChatMsg } from '../../../src/api'
import ChatMessage from '../../../src/teacher/transcript/ChatMessage'

const BEAT: Beat = { heading: 'Where it started', text: 'The first idea.', node_ids: ['n1'] }

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
