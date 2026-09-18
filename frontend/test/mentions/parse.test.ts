/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `@`-mention grammar: which mention the caret is in, what a pick splices
 * into the text, and what a finished message turns out to be asking for.
 *
 * These rules decide whether a message seeds the graph, grounds a question, or
 * goes to the paper scout, so they are pinned here rather than left to a
 * component test — the composer's job is to call them, not to define them.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import type { MentionPaper } from '../../src/api'
import {
  activeMention,
  insertMention,
  mentionText,
  mentionsIn,
  readMessage,
  threadMatches,
} from '../../src/mentions/parse'
import type { MentionThread } from '../../src/mentions/parse'

/** A resolved paper, as the dropdown hands one back. */
function paper(title: string, overrides: Partial<MentionPaper> = {}): MentionPaper {
  return { id: `id-${title}`, arxiv_id: null, title, ...overrides }
}

/** A sibling thread, as the dropdown offers one. */
function thread(title: string): MentionThread {
  return { id: `thread-${title}`, title }
}

/** The draft's resolved-mention map, keyed the way the composer keys it. */
function resolved(...papers: MentionPaper[]): Map<string, MentionPaper> {
  return new Map(papers.map((entry) => [`@${entry.title}`, entry]))
}

describe('activeMention', () => {
  it('finds the mention the caret is inside', () => {
    const found = activeMention('what does @attention', 20)
    expect(found).toEqual({ query: 'attention', start: 10, end: 20, whole: false })
  })

  it('knows when the mention is the whole message', () => {
    // A bare mention is a statement of intent, so Enter on a chosen paper
    // can open it in the same press; inside a sentence it only completes.
    expect(activeMention('@dqn', 4)?.whole).toBe(true)
    expect(activeMention('  @dqn', 6)?.whole).toBe(true)
    expect(activeMention('@dqn and', 4)?.whole).toBe(false)
    expect(activeMention('see @dqn', 8)?.whole).toBe(false)
  })

  it('ends at a completed paper mention, so the question after it is not a query', () => {
    // The bug: after picking `@Attention Is All You Need `, every keystroke
    // of the question typed after it re-ran the lookup on the whole tail.
    const text = '@Attention Is All You Need what does it say'
    expect(activeMention(text, text.length, ['@Attention Is All You Need'])).toBeNull()
    // Without the record it is still a (very long) live mention — the rule
    // is about what the draft resolved, not about the words.
    expect(activeMention(text, text.length)?.query).toBe(
      'Attention Is All You Need what does it say',
    )
  })

  it('reopens when the caret is INSIDE a completed mention', () => {
    // Editing the title: what precedes the caret is only a prefix of the
    // completed text, so the reader is back inside a live mention.
    expect(activeMention('@Attention Is All', 17, ['@Attention Is All You Need'])?.query).toBe(
      'Attention Is All',
    )
  })

  it('ends at a closed thread reference — the bracket is its delimiter', () => {
    const text = '@thread[General] what are some of the other'
    expect(activeMention(text, text.length)).toBeNull()
    // Still open while the bracket is unclosed.
    expect(activeMention('@thread[Gen', 11)?.query).toBe('thread[Gen')
  })

  it('a later @ after a completed mention is its own mention', () => {
    const text = '@thread[General] compare with @dq'
    expect(activeMention(text, text.length)?.query).toBe('dq')
  })

  it('keeps spaces in the query, because paper titles have them', () => {
    // The whole reason a mention has no closing delimiter: `@attention is all
    // you need` must be ONE mention, not five.
    expect(activeMention('@attention is all', 17)?.query).toBe('attention is all')
  })

  it('ignores an @ that does not open a word', () => {
    // An email address or a handle mid-word must not open the dropdown.
    expect(activeMention('mail me at bob@example.com', 26)).toBeNull()
  })

  it('opens on an @ at the very start', () => {
    expect(activeMention('@dqn', 4)?.query).toBe('dqn')
  })

  it('ends a mention at a newline — a mention is a phrase, not a paragraph', () => {
    expect(activeMention('@dqn\nand another thing', 21)).toBeNull()
  })

  it('reads relative to the caret, not the end of the text', () => {
    // The reader clicked back into an earlier mention; what follows the caret
    // is not part of it.
    expect(activeMention('@dqn and @resnet', 4)?.query).toBe('dqn')
  })

  it('is null with no @ at all', () => {
    expect(activeMention('a plain question', 16)).toBeNull()
  })
})

describe('insertMention', () => {
  it('replaces the typed mention with the full title and a trailing space', () => {
    const active = activeMention('what does @atten', 16)!
    const { text, caret } = insertMention('what does @atten', active, {
      kind: 'paper',
      paper: paper('Attention Is All You Need'),
    })
    expect(text).toBe('what does @Attention Is All You Need ')
    // Caret sits after the space, so the sentence carries on without
    // reopening the dropdown on the mention just resolved.
    expect(caret).toBe(text.length)
  })

  it('keeps whatever followed the caret', () => {
    const active = activeMention('what does @atten say?', 16)!
    const { text } = insertMention('what does @atten say?', active, {
      kind: 'paper',
      paper: paper('DQN'),
    })
    expect(text).toBe('what does @DQN  say?')
  })

  it('inserts a thread as the bracketed form the send path reads', () => {
    // `@thread[Title]` is what `history.ts` and `useConversation` look for;
    // the brackets are what separates a discussion from a paper title.
    const active = activeMention('compare with @pp', 16)!
    const { text } = insertMention('compare with @pp', active, {
      kind: 'thread',
      thread: thread('PPO'),
    })
    expect(text).toBe('compare with @thread[PPO] ')
    expect(mentionText({ kind: 'thread', thread: thread('PPO') })).toBe('@thread[PPO]')
  })
})

describe('threadMatches', () => {
  it('matches a title substring, case-insensitively', () => {
    const threads = [thread('General'), thread('PPO'), thread('Deep Q-Networks')]
    expect(threadMatches(threads, 'q-net')).toEqual([thread('Deep Q-Networks')])
    expect(threadMatches(threads, 'p')).toEqual([thread('PPO'), thread('Deep Q-Networks')])
  })

  it('offers every thread for an empty query — `@` alone lists them', () => {
    // How a reader discovers that discussions are mentionable at all.
    const threads = [thread('General'), thread('PPO')]
    expect(threadMatches(threads, '')).toEqual(threads)
  })

  it('matches nothing when no title contains the query', () => {
    expect(threadMatches([thread('PPO')], 'attention')).toEqual([])
  })
})

describe('mentionsIn', () => {
  it('finds resolved mentions in the order they appear', () => {
    const first = paper('DQN')
    const second = paper('ResNet')
    const text = 'compare @ResNet with @DQN'
    expect(mentionsIn(text, resolved(first, second))).toEqual([second, first])
  })

  it('drops a mention whose inserted text the reader has since edited', () => {
    // The deliberate failure mode: edit the title and the paper stops being a
    // resolved mention, so the words are treated as words. Tracking offsets
    // through every edit would break in far harder-to-explain ways.
    expect(mentionsIn('what does @DQ say?', resolved(paper('DQN')))).toEqual([])
  })
})

describe('readMessage — what a sent message is asking for', () => {
  it('a bare resolved mention seeds the graph', () => {
    // The rule already shipped for a pasted arXiv id: naming one paper and
    // nothing else is a statement of intent.
    const dqn = paper('DQN')
    expect(readMessage('@DQN', resolved(dqn))).toEqual({ kind: 'seed', paper: dqn })
  })

  it('a bare resolved mention seeds even with surrounding whitespace', () => {
    const dqn = paper('DQN')
    expect(readMessage('  @DQN  ', resolved(dqn))).toEqual({ kind: 'seed', paper: dqn })
  })

  it('a resolved mention inside a question grounds it instead', () => {
    // The case the ticket was written for: re-seeding here would destroy the
    // graph the question was asked about.
    const dqn = paper('DQN')
    expect(readMessage('what does @DQN say about replay?', resolved(dqn))).toEqual({
      kind: 'ask',
      mentioned: [dqn],
    })
  })

  it('a bare unresolved mention goes to the scout', () => {
    // The dropdown's fallback, and what makes it safe to keep cheap: a paper
    // the cache has never seen is still reachable, just after sending.
    expect(readMessage('@sparse autoencoders', new Map())).toEqual({
      kind: 'find',
      query: 'sparse autoencoders',
    })
  })

  it('an unresolved mention inside a question is just part of the question', () => {
    // NOT routed to the scout: sending the whole sentence there would drop the
    // question. The researcher has its own paper search and can use it.
    expect(readMessage('what about @sparse autoencoders?', new Map())).toEqual({
      kind: 'ask',
      mentioned: [],
    })
  })

  it('a bare thread mention is a question, never a search', () => {
    // `@thread[PPO]` alone would otherwise be a bare unresolved `@phrase`
    // and go to the scout — which would search for papers titled
    // "thread[PPO]". It names a discussion to attach; `send` resolves it.
    expect(readMessage('@thread[PPO]', new Map())).toEqual({ kind: 'ask', mentioned: [] })
  })

  it('a too-short bare mention is a question, not a search', () => {
    // Matches the lookup floor, so the scout is never sent a query the
    // dropdown would have refused to look up.
    expect(readMessage('@ab', new Map())).toEqual({ kind: 'ask', mentioned: [] })
  })

  it('an ordinary question is an ordinary question', () => {
    expect(readMessage('why does attention work?', new Map())).toEqual({
      kind: 'ask',
      mentioned: [],
    })
  })

  it('several mentions in a question all ground it', () => {
    const dqn = paper('DQN')
    const resnet = paper('ResNet')
    expect(readMessage('compare @DQN and @ResNet', resolved(dqn, resnet))).toEqual({
      kind: 'ask',
      mentioned: [dqn, resnet],
    })
  })
})
