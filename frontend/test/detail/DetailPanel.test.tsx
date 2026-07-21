// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The detail panel's joint loading gate: while ANY of the node's fetches
 * (summary hydration, arXiv tags, code links, figures) is still in flight,
 * every loadable section holds its place with an anonymous skeleton — even
 * one whose answer already landed — and the whole set reveals in a single
 * paint once the last answer arrives (empty sections simply don't appear).
 * Non-arXiv papers never fetch the arXiv-keyed extras, so only summary
 * hydration can gate them.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import DetailPanel from '../../src/detail/DetailPanel'
import type { DetailPanelProps } from '../../src/detail/DetailPanel'
import type { VNode } from '../../src/graph/model'
import type { CategoriesResponse, CodeLinksResponse, FiguresResponse } from '../../src/api'

function makeNode(overrides: Partial<VNode> = {}): VNode {
  return {
    id: 'W123',
    arxiv_id: null,
    title: 'Playing Atari with Deep RL',
    year: 2013,
    citation_count: 100,
    url: null,
    rels: ['citation'],
    is_seed: false,
    abstract: 'We present a deep reinforcement learning approach.',
    tldr: null,
    ...overrides,
  }
}

function makeProps(overrides: Partial<DetailPanelProps> = {}): DetailPanelProps {
  return {
    node: makeNode(),
    fieldsLabel: 'Semantic Scholar tags',
    onEnlarge: () => {},
    isPinned: false,
    onTogglePin: () => {},
    onClose: () => {},
    onExplore: () => {},
    ...overrides,
  }
}

const NO_CODE_LINKS: CodeLinksResponse = {
  available: false,
  paper_url: null,
  upvotes: 0,
  github: null,
  models: [],
  datasets: [],
  spaces: [],
  totals: { models: 0, datasets: 0, spaces: 0 },
}
const NO_CATEGORIES: CategoriesResponse = { available: false, categories: [] }
const NO_FIGURES: FiguresResponse = { available: false, figures: [] }

afterEach(cleanup)

describe('the venue line', () => {
  it('renders the publication venue in the meta block, only when known', () => {
    const { container, rerender } = render(
      <DetailPanel {...makeProps({ node: makeNode({ venue: 'Nature' }) })} />,
    )
    const venueLine = container.querySelector('.detail-venue')
    expect(venueLine).not.toBeNull()
    expect(venueLine!.textContent).toBe('Publisher: Nature')

    rerender(<DetailPanel {...makeProps({ node: makeNode({ venue: null }) })} />)
    expect(container.querySelector('.detail-venue')).toBeNull()
  })
})

describe('the joint loading gate', () => {
  it('gates a non-arXiv paper on summary hydration alone', () => {
    const bare = makeNode({ abstract: null })
    const { container, rerender } = render(
      <DetailPanel {...makeProps({ node: bare, detailLoading: true })} />,
    )
    expect(container.querySelector('.detail-summary-skel')).not.toBeNull()
    expect(container.querySelector('.detail-summary')).toBeNull()

    rerender(<DetailPanel {...makeProps({ detailLoading: false })} />)
    expect(container.querySelector('.skel')).toBeNull()
    expect(container.querySelector('.detail-summary')).not.toBeNull()
  })

  it('holds EVERY loadable section while any arXiv fetch is in flight — a known abstract too', () => {
    const arxivNode = makeNode({ arxiv_id: '1312.5602' })
    // Tags and code already answered; figures still pending — nothing reveals.
    const { container } = render(
      <DetailPanel
        {...makeProps({ node: arxivNode, categories: NO_CATEGORIES, codeLinks: NO_CODE_LINKS })}
      />,
    )
    expect(container.querySelector('.detail-summary-skel')).not.toBeNull()
    expect(container.querySelector('.detail-summary')).toBeNull()
    expect(container.querySelector('.detail-cats .skel-chip')).not.toBeNull()
    expect(container.querySelector('.detail-code-skel')).not.toBeNull()
    expect(container.querySelector('.detail-figs-skel')).not.toBeNull()
  })

  it('reveals everything in one paint once the last answer lands', () => {
    const arxivNode = makeNode({ arxiv_id: '1312.5602' })
    const { container } = render(
      <DetailPanel
        {...makeProps({
          node: arxivNode,
          categories: NO_CATEGORIES,
          codeLinks: NO_CODE_LINKS,
          figures: NO_FIGURES,
        })}
      />,
    )
    expect(container.querySelector('.skel')).toBeNull()
    expect(container.querySelector('.detail-summary')).not.toBeNull()
  })

  it('title, meta, and actions render instantly even while the gate holds', () => {
    const arxivNode = makeNode({ arxiv_id: '1312.5602', url: 'https://arxiv.org/abs/1312.5602' })
    const { container, getByText } = render(<DetailPanel {...makeProps({ node: arxivNode })} />)
    expect(getByText('Playing Atari with Deep RL')).toBeTruthy()
    expect(getByText('Abstract ↗')).toBeTruthy()
    expect(container.querySelector('.detail-summary-skel')).not.toBeNull()
  })

  it('never shows any skeleton for a non-arXiv paper that needs no hydration', () => {
    const { container } = render(<DetailPanel {...makeProps()} />)
    expect(container.querySelector('.skel')).toBeNull()
    expect(container.querySelector('.detail-summary')).not.toBeNull()
  })
})
