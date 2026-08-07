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
        refs={{ '14': 'node-fourteen', '29': 'node-twentynine' }}
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
    render(<AnswerMarkdown text="See [9] though." refs={{}} onRefClick={onRefClick} />)
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
        refs={{ '14': 'node-fourteen' }}
        sourceRefs={SOURCE_REFS}
        onRefClick={onRefClick}
      />,
    )
    screen.getByRole('button', { name: '[14]' }).click()
    expect(onRefClick).toHaveBeenCalledWith('node-fourteen')
    expect(screen.getByText('(Reinforcement Learning: An Introduction, p.460)')).toBeTruthy()
  })
})
