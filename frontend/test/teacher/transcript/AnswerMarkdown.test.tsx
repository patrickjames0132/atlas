// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * AnswerMarkdown's clickable `[n]` citations, end to end (render → resolve →
 * click). The focus is the combined-marker case (`[14, 29]`): it must render
 * one chip per index, each resolving to its own paper and spotlighting it.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import AnswerMarkdown from '../../../src/teacher/transcript/AnswerMarkdown'

// Test globals are off, so RTL's auto-cleanup isn't registered — unmount
// between cases so one test's chips don't leak into the next.
afterEach(cleanup)

describe('AnswerMarkdown citations', () => {
  it('makes each index of a combined [14, 29] marker its own clickable chip', () => {
    const onRefClick = vi.fn()
    render(
      <AnswerMarkdown
        text="Both [14, 29] agree."
        graphRefs={{ '14': 'node-fourteen', '29': 'node-twentynine' }}
        onRefClick={onRefClick}
      />,
    )
    // Two separate chips, one per index.
    const chip14 = screen.getByRole('button', { name: '[14]' })
    const chip29 = screen.getByRole('button', { name: '[29]' })

    chip14.click()
    chip29.click()
    expect(onRefClick).toHaveBeenNthCalledWith(1, 'node-fourteen')
    expect(onRefClick).toHaveBeenNthCalledWith(2, 'node-twentynine')
  })

  it('renders an unresolved marker as inert text, not a chip', () => {
    const onRefClick = vi.fn()
    render(<AnswerMarkdown text="See [9] though." graphRefs={{}} onRefClick={onRefClick} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText(/\[9\]/)).toBeTruthy()
  })
})

describe('AnswerMarkdown library citations', () => {
  const SOURCE_REFS = {
    '2': { source_id: 'src-rl', title: 'Reinforcement Learning: An Introduction' },
  }

  it('renders [S2, p.460] as the source title and page', () => {
    render(<AnswerMarkdown text="Defined recursively [S2, p.460]." sourceRefs={SOURCE_REFS} />)
    // The wire format never reaches the reader — the resolved title does.
    expect(screen.getByText('(Reinforcement Learning: An Introduction, p.460)')).toBeTruthy()
    expect(screen.queryByText(/\[S2/)).toBeNull()
  })

  it('drops the page half for a page-less source', () => {
    render(<AnswerMarkdown text="A note [S2]." sourceRefs={SOURCE_REFS} />)
    expect(screen.getByText('(Reinforcement Learning: An Introduction)')).toBeTruthy()
  })

  it('degrades an unresolved marker to its raw text', () => {
    // A hallucinated index, or a saved session from before the map existed.
    render(<AnswerMarkdown text="See [S9, p.1] though." sourceRefs={SOURCE_REFS} />)
    expect(screen.getByText(/\[S9, p\.1\]/)).toBeTruthy()
  })

  it('renders paper and library citations side by side', () => {
    const onRefClick = vi.fn()
    render(
      <AnswerMarkdown
        text="Both [14] and [S2, p.460] agree."
        graphRefs={{ '14': 'node-fourteen' }}
        sourceRefs={SOURCE_REFS}
        onRefClick={onRefClick}
      />,
    )
    screen.getByRole('button', { name: '[14]' }).click()
    expect(onRefClick).toHaveBeenCalledWith('node-fourteen')
    expect(screen.getByText('(Reinforcement Learning: An Introduction, p.460)')).toBeTruthy()
  })
})

describe('AnswerMarkdown paper citations with no graph', () => {
  const PAPER_REFS = {
    '1': {
      node_id: 'node-atari',
      title: 'Playing Atari with Deep RL',
      url: 'https://example.org/atari',
      provider: 's2' as const,
    },
  }

  it('renders [n] as a linked title when there is no graph to resolve it', () => {
    // The graph-free case: `graphRefs` is empty because the frontend never held a
    // numbered list, so without this the marker is dead text.
    render(<AnswerMarkdown text="As shown in [1]." paperRefs={PAPER_REFS} />)
    const link = screen.getByRole('link', { name: '(Playing Atari with Deep RL)' })
    expect(link.getAttribute('href')).toBe('https://example.org/atari')
    expect(screen.queryByText(/\[1\]/)).toBeNull()
  })

  it('prefers the graph chip when a graph IS open', () => {
    const onRefClick = vi.fn()
    render(
      <AnswerMarkdown
        text="As shown in [1]."
        graphRefs={{ '1': 'node-atari' }}
        paperRefs={PAPER_REFS}
        onRefClick={onRefClick}
      />,
    )
    // Clicking spotlights the node rather than navigating away.
    screen.getByRole('button', { name: '[1]' }).click()
    expect(onRefClick).toHaveBeenCalledWith('node-atari')
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('renders a title with no link when the paper has no URL', () => {
    render(
      <AnswerMarkdown
        text="As shown in [1]."
        paperRefs={{ '1': { node_id: 'n', title: 'Untraceable Paper', url: '' } }}
      />,
    )
    expect(screen.getByText('(Untraceable Paper)')).toBeTruthy()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('maps the paper on click when seeding is available', () => {
    // The headline behaviour: in graph-free mode the chip builds that paper's
    // graph rather than making a trip to Semantic Scholar.
    const onPaperSeed = vi.fn()
    render(
      <AnswerMarkdown text="As shown in [1]." paperRefs={PAPER_REFS} onPaperSeed={onPaperSeed} />,
    )
    screen.getByRole('button', { name: '[1]' }).click()
    expect(onPaperSeed).toHaveBeenCalledWith('node-atari', 's2')
  })

  it('seeds under the backend that minted the id, and says so first', () => {
    // Switching the dropdown mid-conversation leaves live chips holding ids
    // the new backend never issued. Building under the ref's own provider is
    // what keeps the click working — the workspace follows it there, so the
    // tooltip warns before the click rather than after.
    const onPaperSeed = vi.fn()
    render(
      <AnswerMarkdown
        text="As shown in [1]."
        paperRefs={PAPER_REFS}
        onPaperSeed={onPaperSeed}
        provider="openalex"
      />,
    )
    const chip = screen.getByRole('button', { name: '[1]' })
    expect(chip.getAttribute('title')).toContain('Semantic Scholar')
    chip.click()
    expect(onPaperSeed).toHaveBeenCalledWith('node-atari', 's2')
  })

  it('says nothing about the backend when the citation is from this one', () => {
    render(
      <AnswerMarkdown
        text="As shown in [1]."
        paperRefs={PAPER_REFS}
        onPaperSeed={vi.fn()}
        provider="s2"
      />,
    )
    expect(screen.getByRole('button', { name: '[1]' }).getAttribute('title')).not.toContain(
      'switching',
    )
  })

  it('keeps the marker compact and puts the title in the tooltip', () => {
    // A full title inline derailed the sentence — twice over when two papers
    // back one claim. The prose keeps its `[n]`; the title is on hover.
    render(<AnswerMarkdown text="As shown in [1]." paperRefs={PAPER_REFS} onPaperSeed={vi.fn()} />)
    const chip = screen.getByRole('button', { name: '[1]' })
    expect(chip.getAttribute('title')).toContain('Playing Atari with Deep RL')
    expect(screen.queryByText(/Playing Atari with Deep RL/)).toBeNull()
  })

  it('greys out a citation whose paper is not on the graph on screen', () => {
    // Reachable only because a chat-seeded jump carries the conversation
    // across a graph change: the marker resolved when it was written, but
    // clicking would now highlight nothing.
    const onRefClick = vi.fn()
    render(
      <AnswerMarkdown
        text="As shown in [1]."
        graphRefs={{ '1': 'node-atari' }}
        onRefClick={onRefClick}
        onGraphIds={new Set(['node-something-else'])}
      />,
    )
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText(/\[1\]/)).toBeTruthy()
  })

  it('keeps the chip live when the paper IS on the graph on screen', () => {
    const onRefClick = vi.fn()
    render(
      <AnswerMarkdown
        text="As shown in [1]."
        graphRefs={{ '1': 'node-atari' }}
        onRefClick={onRefClick}
        onGraphIds={new Set(['node-atari'])}
      />,
    )
    screen.getByRole('button', { name: '[1]' }).click()
    expect(onRefClick).toHaveBeenCalledWith('node-atari')
  })

  it('marks a seeding chip apart from a spotlight chip in shape, not only colour', () => {
    // The two chips do different things — one highlights, one rebuilds the
    // workspace — so the difference must survive a colour-blind reader.
    const { container: seeding } = render(
      <AnswerMarkdown text="As shown in [1]." paperRefs={PAPER_REFS} onPaperSeed={vi.fn()} />,
    )
    expect(seeding.querySelector('.cite-ref-seed svg')).toBeTruthy()
    cleanup()
    const { container: spotlight } = render(
      <AnswerMarkdown
        text="As shown in [1]."
        graphRefs={{ '1': 'node-atari' }}
        onRefClick={vi.fn()}
      />,
    )
    // The spotlight chip carries its own glyph — same family, different shape.
    expect(spotlight.querySelector('.cite-ref-seed')).toBeNull()
    expect(spotlight.querySelector('.cite-ref-spot svg')).toBeTruthy()
  })
})

describe('AnswerMarkdown dollars', () => {
  it('renders money as money, not as one formula spanning the paragraph', () => {
    // The reported bug: remark-math paired the two currency dollars and
    // rendered everything between them as inline math — italic nonsense in a
    // 500px unwrappable box, which scrolled the docked panel sideways.
    const { container } = render(
      <AnswerMarkdown text="They raised $3.77 billion, up from $1.8 billion in 2024." />,
    )
    expect(container.querySelector('.katex')).toBeNull()
    expect(screen.getByText(/\$3\.77 billion, up from \$1\.8 billion/)).toBeTruthy()
  })

  it('still renders a real formula', () => {
    const { container } = render(<AnswerMarkdown text="The loss $L = x^2$ falls." />)
    expect(container.querySelector('.katex')).toBeTruthy()
  })
})
