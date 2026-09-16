import { activateThread } from '../store/workspace'
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The unified assistant — a slim shell around one conversation, rendered in
 * two shapes and at two capability levels. The shapes:
 *   • `landing` — no graph yet, so the chat owns the whole body as a centred
 *     column. This is the app's front door, and needs neither a graph nor an
 *     uploaded library to be useful.
 *   • docked — a graph is open, so it collapses to a resizable side panel
 *     beside the map.
 * The capability, independently:
 *   • No graph → the researcher, seedless: the literature plus whatever
 *     sources the reader has uploaded.
 *   • A graph is open → the streaming lecture + agentic Q&A over it.
 *
 * **The two shapes are one component instance, deliberately.** The shell keeps
 * it at a single position in the tree and only swaps the `landing` flag, so
 * entering graph mode collapses the chat into the panel without remounting —
 * the conversation, its scroll position and its run state all survive. That
 * is the whole point of clicking a cited paper: the answer you were reading is
 * still there when its graph arrives. (`epoch`, which the parent keys on, no
 * longer bumps on a graph load for the same reason — only Home and a session
 * restore remount.)
 *
 * **Docked, the panel is a stack of folding sections** (v7.10.0): *Lectures*
 * — the four mode buttons and whichever lecture is shown — and *Chat*, the
 * conversation, whose caret row also carries every control that binds the ask:
 * the 🎓/📚 scope pickers and the 🔍/▽ search controls, because those scope
 * the researcher answering there rather than the lecturer above.
 * Before this the two shared one scroll and took turns: playing a lecture hid
 * the chat, asking a question hid the lecture. Sections let a reader keep a
 * lecture open and ask about it. With no graph there is nothing to divide, so
 * the conversation simply is the panel.
 *
 * **The ask bar itself holds nothing but the question** (v7.11.0). Those four
 * controls all used to sit inside the pill, which made the one thing you came
 * here to use — a box to type in — read as a toolbar with a text field wedged
 * in it. Without a graph they moved out to a chip row directly beneath the
 * bar; with one, up to the Chat row above it. Either way they stay adjacent to
 * the ask they modify, and the bar goes back to looking like a bar.
 *
 * The conversation itself lives in the store (transcript slice) and the
 * stream orchestration in useConversation; this component owns only what it
 * alone renders — the input box, the section folds, the scope picker's data,
 * the lightbox. A restored session's transcript arrives via the store, no
 * seeding props needed.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import {
  DEFAULT_SEARCH_OPTIONS,
  type AnswerFigure,
  type MentionPaper,
  type SearchOptions,
} from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { loadLibrary, selectLibrary } from '../store/library'
import { selectConversation } from '../store/transcript'
import HopDots from './HopDots'
import ScopePicker from './ScopePicker'
import SearchControls from '../search/SearchControls'
import { useDirectSearch } from '../search/useDirectSearch'
import { ID_RE } from '../graph/model'
import MentionSuggestions from '../mentions/MentionSuggestions'
import { insertMention, readMessage } from '../mentions/parse'
import { useMentionSuggestions } from '../mentions/useMentionSuggestions'
import Lightbox from '../figures/Lightbox'
import ChatMessage from './transcript/ChatMessage'
import { useConversation } from './useConversation'
import { useResizablePanel } from '../ui/useResizablePanel'
import './teacher.css'

/**
 * The bin the two Clear controls share — the composer's (which wipes the
 * conversation) and the Lectures row's (which drops the shown lecture).
 *
 * @returns The inline glyph.
 */
function ClearGlyph() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M3.2 4.6h9.6M6.5 4.6V3.3a.8.8 0 0 1 .8-.8h1.4a.8.8 0 0 1 .8.8v1.3M4.8 4.6l.45 7.9a1.1 1.1 0 0 0 1.1 1h3.3a1.1 1.1 0 0 0 1.1-1l.45-7.9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * Whether the reader has asked the OS for less motion.
 *
 * The CSS entrances answer this with a `prefers-reduced-motion` block; the
 * composer's FLIP is scripted, so it has to ask directly. Read at call time,
 * never at module scope — this module is imported by tests running in the
 * node environment, where there is no `window` at all.
 *
 * @returns True when motion should be skipped.
 */
function prefersStill(): boolean {
  return (
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Render the assistant panel: the conversation and the ask form.
 *
 * @returns The docked, resizable assistant panel.
 */
export default function Teacher({
  collapsed = false,
  landing = false,
  onClose,
}: {
  /** Hidden (but kept mounted, so the conversation survives) when collapsed. */
  collapsed?: boolean
  /**
   * This is the landing surface, not a docked side panel: no graph is open, so
   * the conversation gets the whole body as a centred column. Deliberately the
   * *same component instance* as the docked panel — the shell keeps it at one
   * position in the tree and only swaps this flag, so entering graph mode
   * collapses the chat into the side panel without remounting it, and the
   * answer you were reading keeps its scroll position.
   */
  landing?: boolean
  /** Collapse the panel (the header ✕). */
  onClose?: () => void
}) {
  const chat = useAppSelector((state) => selectConversation(state).chat)
  // The graph on screen, so a turn answered over a different one can say which.
  const subject = useAppSelector((state) =>
    state.explorations.byId[state.explorations.activeId]?.threads.find(
      (thread) => thread.id === state.transcript.activeKey,
    ),
  )
  const scopeCount = useAppSelector(
    (state) => state.workspace.selectedNodeIds.length || state.workspace.visibleNodeIds.length,
  )
  // How many nodes the user has hand-picked on the graph (alt-drag / shift-click)
  // to scope the teacher; 0 means it grounds in every visible paper.
  const pickedCount = useAppSelector((state) => state.workspace.selectedNodeIds.length)
  const {
    hasGraph,
    asking,
    error,
    activeChat,
    activeChatBeat,
    onChatBeatClick,
    onChatClick,
    onRefClick,
    onPaperSeed,
    provider,
    send,
    reroute,
    retryAnswer,
    stopAsk,
    clearChat,
  } = useConversation()

  const siblingThreads = useAppSelector(
    (state) =>
      state.explorations.byId[state.explorations.activeId]?.threads.filter(
        (thread) => thread.id !== state.transcript.activeKey,
      ) ?? [],
  )
  const [threadQuery, setThreadQuery] = useState<{
    start: number
    end: number
    query: string
  } | null>(null)
  const [threadChoice, setThreadChoice] = useState(0)
  const threadOptions = siblingThreads.filter((thread) =>
    thread.title.toLowerCase().includes(threadQuery?.query.toLowerCase() ?? ''),
  )
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // The uploaded library, powering the source-scope picker (shown whenever
  // there is anything to scope — see the render site for why one source
  // counts). Read LIVE from the library slice — the Sources drawer reloads
  // the slice on every upload/delete, so the picker appears the moment a
  // source lands (it used to sit on a stale mount-time fetch until a page
  // reload).
  const dispatch = useAppDispatch()
  const { sources: libraryItems, loaded: libraryLoaded } = useAppSelector(selectLibrary)
  // Sources the assistant may NOT search — tracked by EXCLUSION so a source
  // uploaded after the user last touched the picker is searchable by default.
  // Checked = current sources minus these; a deleted source's lingering id
  // here is inert.
  const [excludedSources, setExcludedSources] = useState<string[]>([])
  // The papers picked from the `@` dropdown in the message being composed,
  // keyed by the text inserted for each. A ref rather than state because
  // nothing renders from it — it is read once, at send — and re-rendering the
  // composer on every pick would fight the textarea's own caret handling.
  const resolvedMentions = useRef<Map<string, MentionPaper>>(new Map())
  const mentions = useMentionSuggestions(provider)
  // Which scope picker's popover is open — one shared slot, so opening either
  // picker closes the other (their popovers overlap when both are open).
  const [openScope, setOpenScope] = useState<'lectures' | 'sources' | 'filters' | null>(null)
  // The bar's filters. They bind every paper search — the reader's `@`
  // lookups excepted (see routes/search.py's api_mentions) and the
  // assistant's own included — which is why they sit beside the input rather
  // than inside any one search control. The "Find papers" toggle they used to
  // sit outside is gone in v7.18.0: a search is now something you say, with
  // `@`, not a mode you arm.
  const [searchOptions, setSearchOptions] = useState<SearchOptions>(DEFAULT_SEARCH_OPTIONS)
  // The answer figure opened full-screen (null = closed).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)
  // The paper scout's own failure slot. Separate from the conversation's
  // `error` because only a transport failure lands here — the scout
  // degrades internally, so a rate-limited provider arrives as a normal
  // result whose summary says so.
  const [searchError, setSearchError] = useState<string | null>(null)
  const { width, onHandlePointerDown, dragging } = useResizablePanel('atlas.teacherWidth', 340)
  // A scout run shares the bar's busy state with the researcher: one bar, one
  // spinner, and neither can be fired while the other is running.
  const { searching, runSearch } = useDirectSearch(provider, searchOptions, setSearchError)

  // First reader fetches; the loaded flag keeps the drawer (and the remounts
  // that Home and a session restore still cause) from re-fetching a library
  // the store already holds.
  useEffect(() => {
    if (!libraryLoaded) dispatch(loadLibrary())
  }, [libraryLoaded, dispatch])

  // Checked = the assistant may search that source (everything not excluded).
  const scopeIds = libraryItems
    .filter((source) => !excludedSources.includes(source.id))
    .map((source) => source.id)
  // "No scope" (search the whole library) only when every source is checked;
  // any other state is sent as an explicit id list (empty = search nothing).
  const scopeAll = libraryItems.length === 0 || scopeIds.length === libraryItems.length
  const scopeArg = scopeAll ? undefined : scopeIds

  // One bar, four destinations. The first three are decided HERE on plain
  // facts — a pasted id is exact, a picked mention is a paper they already
  // chose, an unresolved `@phrase` is a search — so they cost nothing and
  // cannot be wrong. Only the fourth asks a model, because "teach me these
  // papers" and "which of these used dropout" differ in their words and
  // nowhere else; `send` owns that, and the turn it produces says which
  // assistant it picked so the reader can take the other in one click.
  //
  // There was a fifth until v7.23.0: a `/lecture` command, the deterministic
  // way to name the lecturer (and its framing) without a classify. It went
  // because the router already reads all of that off the words — and, since
  // the same version, reads *which papers* too ("lecture me on the
  // references"), which a two-value command could never say. What survives
  // of it is the router's own no-model fast path for "lecture me on these".
  const submitQuestion = () => {
    const question = input.trim()
    if (!question || asking || searching) return
    setInput('')
    mentions.reset()
    setThreadQuery(null)
    // A pasted arXiv id/URL is a statement of intent, not a question: land on
    // that exact paper. First in the tree because it needs no lookup at all —
    // the id IS the answer, where every branch below has to resolve something.
    if (ID_RE.test(question)) {
      onPaperSeed(question)
      return
    }
    // What the words turn out to be. `readMessage` is a substring check and a
    // startsWith — the three branches below stay free and exact. What changed
    // in v7.18.0 is that the reader says which of them they meant, with `@`,
    // instead of arming a mode beforehand.
    if (question.includes('@thread[')) {
      void send(question, scopeArg, searchOptions)
      return
    }
    const intent = readMessage(question, resolvedMentions.current)
    resolvedMentions.current = new Map()
    if (intent.kind === 'seed') {
      // A resolved mention alone: we already hold the exact paper, so seed on
      // its id rather than re-resolving the title we just looked up.
      onPaperSeed(intent.paper.arxiv_id || intent.paper.id)
      return
    }
    if (intent.kind === 'find') {
      // `@words` that resolved to nothing, alone on the line — the dropdown's
      // fallback. This is what the "Find papers" toggle used to do, now said
      // rather than switched to.
      void runSearch(intent.query)
      return
    }
    // Anything else: a message whose destination is genuinely unknown. `send`
    // classifies it and streams from the lecturer or the researcher.
    void send(question, scopeArg, searchOptions, intent.mentioned)
  }

  const onAsk = (event: FormEvent) => {
    event.preventDefault()
    submitQuestion()
  }

  // The ask box is a textarea so long questions wrap and stay readable. Keep
  // the chat convention: Enter sends, Shift+Enter drops a newline (letting a
  // question run multiple lines without hitting the Ask button).
  /**
   * Accept a suggestion: splice the paper's title in and remember what it
   * resolved to, so `readMessage` can find it again at send.
   *
   * @param paper The picked paper.
   */
  const pickMention = (paper: MentionPaper) => {
    const field = inputRef.current
    if (!field || !mentions.active) return
    const { text: next, caret } = insertMention(input, mentions.active, paper)
    resolvedMentions.current.set(`@${paper.title}`, paper)
    setInput(next)
    mentions.reset()
    // The caret has to be restored after React paints the new value, or the
    // browser parks it at the end of the message and the reader's sentence
    // continues in the wrong place.
    requestAnimationFrame(() => {
      field.focus()
      field.setSelectionRange(caret, caret)
    })
  }

  /** Insert a labelled sibling reference without invoking paper search.
   * @param title The selected discussion's title.
   */
  const pickThread = (title: string) => {
    if (!threadQuery) return
    const inserted = `@thread[${title}] `
    setInput(input.slice(0, threadQuery.start) + inserted + input.slice(threadQuery.end))
    const caret = threadQuery.start + inserted.length
    setThreadQuery(null)
    requestAnimationFrame(() => {
      inputRef.current?.focus()
      inputRef.current?.setSelectionRange(caret, caret)
    })
  }

  /**
   * Re-read the composer after any change that could move the caret, so the
   * typeaheads (the `@thread` picker and the `@` mention dropdown) follow it.
   *
   * @param field The textarea, read for both its value and its caret.
   */
  const syncComposer = (field: HTMLTextAreaElement) => {
    const caret = field.selectionStart ?? field.value.length
    const threadMatch = /@thread(?:\[)?([^\]\n]*)$/.exec(field.value.slice(0, caret))
    if (threadMatch) {
      setThreadQuery({ start: threadMatch.index, end: caret, query: threadMatch[1].trim() })
      setThreadChoice(0)
      mentions.reset()
      return
    }
    setThreadQuery(null)
    mentions.onInput(field.value, caret)
  }

  const onInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // While a typeahead is open it owns the arrows, Enter, Tab and Escape —
    // the keys a reader picking from a list expects to work. Everything else
    // still reaches the textarea, so typing never stops.
    if (threadQuery) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setThreadQuery(null)
        return
      }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        setThreadChoice((previous) =>
          Math.max(
            0,
            Math.min(threadOptions.length - 1, previous + (event.key === 'ArrowDown' ? 1 : -1)),
          ),
        )
        return
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && threadOptions[threadChoice]) {
        event.preventDefault()
        pickThread(threadOptions[threadChoice].title)
        return
      }
    }
    if (mentions.open) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        mentions.move(event.key === 'ArrowDown' ? 1 : -1)
        return
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && mentions.choice) {
        event.preventDefault()
        pickMention(mentions.choice)
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        mentions.dismiss()
        return
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitQuestion()
    }
  }

  // Grow the textarea to fit its content (up to the CSS max-height, past which
  // it scrolls): reset to auto so it can shrink back, then match scrollHeight.
  // Runs on every input change, including the reset to '' after a submit.
  //
  // **An empty composer is one line by construction, never by measurement.**
  // The inline height is cleared and the effect returns, leaving the CSS
  // `min-height` to floor it at exactly one line. Everything that can make
  // `scrollHeight` lie about an empty field — measuring inside a
  // `display:none` panel (it reports 0), measuring mid-layout, a stale inline
  // height from a longer draft — then cannot make the bar open several lines
  // tall with nothing in it, which is the one state a reader is guaranteed to
  // see and the one where being wrong looks like a broken control.
  useEffect(() => {
    const field = inputRef.current
    if (!field) return
    if (!input) {
      field.style.height = ''
      return
    }
    field.style.height = 'auto'
    if (field.scrollHeight > 0) field.style.height = `${field.scrollHeight}px`
  }, [input])

  // Follow the bottom while an answer builds. Trace chips, tokens and beats all
  // arrive at the end of the transcript, and without this they simply grow past
  // the fold — the reader watches the agent work right up until the moment the
  // work scrolls out of sight.
  //
  // Conditional on purpose: it follows only while the reader is already AT the
  // bottom. Scroll up mid-answer to re-read something and the transcript stops
  // chasing, because yanking someone back down is worse than the problem this
  // solves; scroll back down and it resumes. The threshold is generous — a few
  // pixels of rounding, or a half-line of overshoot, still counts as "at the
  // bottom", and `.chat`'s entrance transform means the last element is briefly
  // 16px lower than its resting place while it animates in.
  const scrollRef = useRef<HTMLDivElement>(null)
  const following = useRef(true)
  const onTranscriptScroll = () => {
    const box = scrollRef.current
    if (box) following.current = box.scrollHeight - box.scrollTop - box.clientHeight < 40
  }
  useEffect(() => {
    const box = scrollRef.current
    if (!box || !following.current) return
    // Instant, never smooth: a smooth scroll can't keep up with SSE frames, and
    // several in flight at once fight each other into a visible judder.
    box.scrollTop = box.scrollHeight
  }, [chat])

  // The composer's drop, on the first question of a landing session. Empty, it
  // sits optically centred with the greeting; the moment a conversation starts
  // it belongs at the bottom with the transcript filling in above. That move is
  // a flex-layout change, which CSS cannot transition — so this is a FLIP:
  // remember where the bar *was* on the last commit, and once the browser has
  // put it in its new place, animate it from the old position to the new one.
  // Nothing in the layout is faked; only a transform is played over the top.
  //
  // Keyed on `empty` alone, and deliberately not on every render: reading
  // getBoundingClientRect forces layout, and this component re-renders on every
  // streamed token.
  const askRef = useRef<HTMLDivElement>(null)
  const askTop = useRef<number | null>(null)
  const wasEmpty = useRef(false)
  const empty = landing && chat.length === 0
  useLayoutEffect(() => {
    const bar = askRef.current
    if (!bar) return
    const from = askTop.current
    if (wasEmpty.current && !empty && from !== null && !prefersStill()) {
      const travelled = from - bar.getBoundingClientRect().top
      // `animate` is optional-called: jsdom has no Web Animations API, so a
      // component test would otherwise die on a purely decorative flourish.
      if (travelled) {
        bar.animate?.(
          [{ transform: `translateY(${travelled}px)` }, { transform: 'translateY(0)' }],
          // Paced with the CSS entrances (`rise-in`, teacher.css) and eased
          // the same way — this travels much further than any of them, so it
          // gets the longer end of the range. Retune the two together.
          { duration: 560, easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)' },
        )
      }
    }
    wasEmpty.current = empty
    askTop.current = bar.getBoundingClientRect().top
  }, [empty])

  // What the ask bar invites, which is not always the same offer. The old copy
  // promised books and PDFs whenever there was no graph — fine back when a
  // library was the price of admission, and a lie now that the assistant is
  // the landing surface for everyone. Only name the library when there is one.
  // The placeholder is where `@` is taught, because it is the only help
  // surface a reader is already looking at when they would need it. Every
  // variant names it: the gesture is the same with a graph, without one, and
  // with a library. The graph variant also teaches the lecture, and only that
  // one does — a lecture needs papers on screen to be about, so offering it
  // with no graph would advertise something the bar cannot do.
  //
  // **No prefix is named.** All three used to end "…or @ a paper", and for a
  // while the graph variant taught `/` — a verb and two prefixes in one line
  // of grey text read as a legend, not an invitation. `@` teaches itself the
  // moment it is typed (the dropdown opens on the third character) and the
  // tour covers it; the lecture is asked for in words, which needs no
  // teaching beyond saying so.
  const askPlaceholder = hasGraph
    ? 'Ask about these papers, or for a lecture…'
    : libraryItems.length > 0
      ? 'Ask your books, PDFs, or the literature…'
      : 'Ask a research question…'

  // The one-line "Answers also draw on …" note above the ask bar, naming the
  // 📚 picker's state. It had a second half until v7.21.0 — "the lecture
  // (🎓)" — which went with that picker: a lecture is a turn now, so the
  // conversation itself says what the answer can draw on.
  //
  // Graph mode only. There the picker is a bare icon on the Chat row and this
  // line is the only place its state is spelled out; with no graph the tool
  // row under the bar wears its own label ("2 sources"), so the note would be
  // saying the same thing twice a centimetre apart.
  const askContextParts: string[] = []
  if (hasGraph && scopeIds.length > 0) {
    askContextParts.push(`${scopeIds.length} source${scopeIds.length > 1 ? 's' : ''} (📚)`)
  }

  // Which sources the researcher may search. ONE picker, rendered in one of
  // two places depending on the shape the panel is in — but never *inside* the
  // ask bar any more (v7.11.0). It sat there, with the two search controls
  // beside it, until the pill was three controls and a textarea and read as
  // clutter: the box you type in should look like a box you type in. So:
  //   • no graph — down in the tool row directly under the bar, still plainly
  //     part of the question you are about to ask, and with the room to wear
  //     its label;
  //   • docked — up on the Chat section's row beside the 🎓 lecture scope,
  //     because beside a graph the panel is ~340px and nothing fits in the
  //     pill. That row already hosts exactly this kind of control.
  // At ONE source too, not two. The gate used to be `> 1` on the reading that
  // a lone source leaves no choice to make — but "use it / don't" is a choice,
  // and it's the one a reader with a single uploaded book most wants: without
  // the picker there was no way to ask a question *without* their textbook in
  // play. The empty scope (`scopeArg = []`) was already plumbed end to end.
  const sourcePicker = libraryItems.length > 0 && (
    <ScopePicker
      items={libraryItems}
      checkedIds={scopeIds}
      dataTour="source-scope"
      open={openScope === 'sources'}
      onOpenChange={(nowOpen) => setOpenScope(nowOpen ? 'sources' : null)}
      onToggle={(id) =>
        setExcludedSources((prev) =>
          prev.includes(id) ? prev.filter((other) => other !== id) : [...prev, id],
        )
      }
      onSelectAll={() => setExcludedSources([])}
      onDeselectAll={() => setExcludedSources(libraryItems.map((source) => source.id))}
      labels={{
        icon: '📚',
        unit: 'source',
        heading: 'Search in',
        allHint: 'All sources are searched.',
        someHint: 'Only the checked sources are searched.',
        noneHint: "No sources selected — the assistant won't search your library.",
        buttonTitle: 'Choose which of your sources the assistant may search',
      }}
    />
  )

  // The filter control, which travels with the source picker above for the
  // same reason and to the same two places — the tool row under the bar
  // without a graph, the Chat row with one. Its popover anchors to whichever
  // container it lands in, so it still spans the panel rather than the button
  // that opened it. It was two controls until v7.18.0, when the "Find papers"
  // toggle beside it was replaced by typing `@`.
  const searchControls = (
    <SearchControls
      options={searchOptions}
      onOptions={setSearchOptions}
      provider={provider}
      open={openScope === 'filters'}
      onOpenChange={(nowOpen) => setOpenScope(nowOpen ? 'filters' : null)}
    />
  )

  // Which lecture turn is expanded. **Derived, with an override** rather than
  // stored per turn: the rule is "the newest lecture is open, the ones behind
  // it are folded", which is a fact about the whole conversation and would
  // need an effect per arriving lecture to maintain as state. So the default
  // is computed here and `openByReader` holds only the turns whose state the
  // reader has actually changed — nothing to keep in sync, and a lecture that
  // arrives while they are reading an older one folds that older one without
  // touching their choice about it.
  //
  // Keyed by turn index, like `activeChatBeat`. Indices move when a failed
  // turn is dropped, so the map is cleared whenever the conversation is (see
  // `clearConversation`) rather than tracked through every mutation — a stale
  // entry would fold the wrong lecture, and the cost of being wrong here is a
  // caret the reader clicks once.
  const [openByReader, setFoldedByReader] = useState<Record<number, boolean>>({})
  const newestLecture = chat.reduce(
    (latest, message, index) => (message.beats?.length ? index : latest),
    -1,
  )

  /** Clear the conversation, and the fold choices that addressed its turns. */
  const clearConversation = () => {
    setFoldedByReader({})
    clearChat()
  }

  // The conversation's turns, rendered identically wherever they land — in
  // the Q&A section beside a graph, or as the whole panel without one.
  const chatTurns = chat.map((message, index) => {
    // Clicking the bubble re-lights the answer's whole grounding set — so it's
    // only a control while at least one of those papers is actually on the
    // graph. Since the conversation now outlives the graph it was written
    // against, an older answer can cite nothing that's still loaded, and a
    // clickable bubble that highlights nothing is the same dead pointer its
    // `[n]` chips grey out for. Partial overlap still counts: lighting the
    // papers that *are* here is useful.
    //
    // A lecture turn has no `cited` — its papers live on its beats — so the
    // whole-turn set is every beat's papers, deduped. Clicking the bubble
    // lights the lecture's full scope; clicking a beat lights that beat's.
    const grounded =
      message.cited && message.cited.length > 0
        ? message.cited
        : [...new Set((message.beats ?? []).flatMap((beat) => beat.node_ids))]
    const clickable = message.role === 'assistant' && grounded.length > 0
    return (
      <ChatMessage
        key={`c${index}`}
        message={message}
        onThreadOpen={(id) => void dispatch(activateThread(id))}
        active={activeChat === index}
        streaming={asking || searching}
        // Only the LAST turn can be the one being generated, so only it gets
        // the live trace treatment; every earlier turn's trace stays folded.
        working={(asking || searching) && index === chat.length - 1}
        onActivate={clickable ? () => onChatClick(index, grounded) : undefined}
        onRetry={message.failed ? () => retryAnswer(index) : undefined}
        onRefClick={onRefClick}
        onPaperSeed={onPaperSeed}
        provider={provider}
        onEnlarge={setLightbox}
        // A lecture answered in the chat: this turn's beats, lit one at a
        // time. `activeChatBeat` addresses a beat by turn as well as index,
        // since a conversation can hold more than one lecture.
        activeBeat={activeChatBeat?.turn === index ? activeChatBeat.beat : null}
        beatsOpen={openByReader[index] ?? index === newestLecture}
        onToggleBeats={
          message.beats?.length
            ? () =>
                setFoldedByReader((folded) => ({
                  ...folded,
                  [index]: !(folded[index] ?? index === newestLecture),
                }))
            : undefined
        }
        onBeatClick={
          message.beats?.length
            ? (beatIndex, beat) => onChatBeatClick(index, beatIndex, beat)
            : undefined
        }
        // Only offered on a turn a *model* routed, and only while nothing
        // else is running — a reroute sends a new message, and two at once
        // would abort each other.
        onReroute={message.routedTo && !asking && !searching ? () => reroute(index) : undefined}
      />
    )
  })

  return (
    <section
      className={`teacher${landing ? ' landing' : ''}${landing && chat.length === 0 ? ' empty' : ''}${collapsed ? ' collapsed' : ''}`}
      data-tour="assistant-panel"
      style={landing ? undefined : { width }}
    >
      {/* Nothing to resize against on the landing surface — it owns the body. */}
      {!landing && (
        <div
          className={`panel-resize-handle${dragging ? ' dragging' : ''}`}
          onPointerDown={onHandlePointerDown}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panel"
        />
      )}
      <div className="teacher-head">
        {/* The landing surface has no panel title and nothing to close — the
            row would be an empty strip of chrome. */}
        {!landing && (
          <div className="teacher-head-top">
            <span className="teacher-title">
              {hasGraph ? 'AI Teacher & Discovery' : 'Ask the assistant'}
            </span>
            <div className="teacher-head-right">
              {onClose && (
                <button
                  className="link-btn"
                  onClick={onClose}
                  aria-label="Close the assistant panel"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* One scroller, holding the conversation and nothing else.
          It held **sections** from v7.10.0 to v7.21.0 — a Lecture section
          above a Chat one, each behind its own caret — because the panel had
          two things in it that had to be able to coexist. Deleting the lecture
          half left one section, and a caret whose only job was folding away
          the whole point of the panel: a "CHAT" header over the chat, in a
          panel already titled "AI Teacher & Discovery", with a ✕ next to it
          that does the same job more honestly. So the sections are gone and
          the two shapes are now the same shape. The follow-the-bottom effect
          above watches this box, so a streaming answer keeps itself in view. */}
      <div className="teacher-scroll" ref={scrollRef} onScroll={onTranscriptScroll}>
        {chatTurns}
        {chat.length === 0 &&
          (landing ? (
            <h1 className="landing-greeting">What do you want to explore?</h1>
          ) : hasGraph ? (
            <div className="teacher-hint">
              Ask a question about the papers on the graph — or ask for a lecture on them, on the
              references, or on a paper by name.
            </div>
          ) : (
            <div className="teacher-hint">
              Ask a question and I’ll answer straight from your uploaded sources — books, PDFs, and
              pages — citing them by page. No graph needed.
            </div>
          ))}
        {(error || searchError) && <div className="teacher-error">{error ?? searchError}</div>}
      </div>

      {hasGraph && pickedCount > 0 && (
        <p className="ask-context-note">
          Scoped to {pickedCount} hand-picked paper{pickedCount > 1 ? 's' : ''} — lectures and
          answers focus on your selection (clear it on the graph to widen).
        </p>
      )}
      {askContextParts.length > 0 && (
        <p className="ask-context-note">Answers also draw on {askContextParts.join(' · ')}.</p>
      )}
      {/* Bar and tool row move as one thing — which is why the FLIP below
          measures this wrapper rather than the form: on the landing surface
          the whole group drops from the optical centre to the bottom on the
          first question, and a row that snapped down while the bar above it
          slid would read as two separate controls. */}
      <div className="ask-dock" ref={askRef}>
        <p className="ask-context-note thread-subject">
          {subject?.identity
            ? `Asking about ${subject.title} · ${scopeCount} papers`
            : 'General · Search and discuss across your exploration'}
        </p>
        <form className="teacher-ask" data-tour="ask" onSubmit={onAsk}>
          {/* The `@` dropdown, anchored to the bar (which is positioned) and
              opening upward — the composer sits at the bottom of the panel, so
              a list below it would open off-screen. */}
          {threadQuery && (
            <div className="thread-suggestions" role="listbox" aria-label="Mention a thread">
              <div className="thread-suggestions-title">Discussions in this exploration</div>
              {threadOptions.map((thread, index) => (
                <button
                  type="button"
                  role="option"
                  aria-selected={index === threadChoice}
                  key={thread.id}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => pickThread(thread.title)}
                >
                  {thread.title}
                </button>
              ))}
              {!threadOptions.length && <p>No matching threads</p>}
            </div>
          )}
          {mentions.open && (
            <MentionSuggestions
              papers={mentions.papers}
              highlighted={mentions.highlighted}
              loading={mentions.loading}
              step={mentions.step}
              onPick={pickMention}
              onHighlight={mentions.setHighlighted}
            />
          )}
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => {
              setInput(event.target.value)
              syncComposer(event.target)
            }}
            // Clicking and arrowing move the caret without changing the text,
            // and a mention is defined relative to the caret — so the dropdown
            // has to re-read on both, or it goes on offering candidates for a
            // mention the reader has navigated out of.
            onKeyUp={(event) => syncComposer(event.currentTarget)}
            onClick={(event) => syncComposer(event.currentTarget)}
            onBlur={() => mentions.reset()}
            onKeyDown={onInputKeyDown}
            rows={1}
            placeholder={askPlaceholder}
            aria-label="Ask the assistant a question"
          />
          {/* ▽ Filters, back inside the pill at Patrick's call (2026-09-14).
              It was moved OUT in v7.11.0 along with two other controls, on the
              reasoning that a pill holding three controls and a textarea read
              as clutter — "the box you type in should look like a box you type
              in". Two of those three are gone since (the 🔍 toggle to `@` in
              v7.18.0, the 🎓 scope in v7.21.0), so what came back is one
              button into a bar that has room for it, next to the question it
              actually binds. Its popover anchors to the bar and spans it,
              which is the same width the Chat row used to give it. */}
          {searchControls}
          {/* Clear, inside the bar beside the send rather than floating above the
              transcript — same round shape and size, but muted rather than
              accent: it's the destructive one, and it shouldn't compete with the
              control you actually came here to press. Contextual, as it always
              was: with a lecture on screen it clears that instead of the chat,
              which the tooltip says since the icon can't. */}
          {chat.length > 0 && (
            <button
              type="button"
              className="ask-clear"
              onClick={clearConversation}
              title="Clear the chat — start a fresh conversation"
              aria-label="Clear chat"
            >
              <ClearGlyph />
            </button>
          )}
          {/* One button, two jobs. While an answer streams it shows the same
              hopping dots the lecture buttons wear — and hovering turns it into a
              stop, so the control that says "working" is also the one that ends
              it. Deliberately not disabled mid-flight: that was the old ellipsis,
              which looked inert and offered no way out of a long run. */}
          <button
            type={asking || searching ? 'button' : 'submit'}
            className={asking ? 'is-stop' : undefined}
            disabled={(!asking && !input.trim()) || searching}
            onClick={asking ? stopAsk : undefined}
            title={asking ? 'Stop generating' : undefined}
            aria-label={asking ? 'Stop generating' : 'Ask'}
          >
            {asking ? (
              <>
                <HopDots />
                <span className="stop-glyph" aria-hidden="true" />
              </>
            ) : searching ? (
              // A direct search is short and has no partial result worth
              // keeping, so it shows progress without offering a stop.
              <HopDots />
            ) : (
              '↑'
            )}
          </button>
        </form>
        {/* The 📚 source scope, as a chip directly beneath the bar: near what
            it modifies, and out of the pill. **One home since v7.21.0** — it
            rode the Chat section's caret row with a graph open and this row
            without one, and deleting the sections left this row as the only
            place. Renders nothing when there is no library to scope, so an
            empty row never shows. */}
        <div className="ask-tools">{sourcePicker}</div>
      </div>

      {lightbox && <Lightbox figure={lightbox} onClose={() => setLightbox(null)} />}
    </section>
  )
}
