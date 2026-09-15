# `src/commands`

Telling the assistant what to do rather than asking it: type `/`, pick from the
menu that appears, and the message is an instruction the composer runs directly
— no classifier, no latency, no guess.

```
commands/
  parse.ts           — the grammar, as pure functions: the registry, which
                       command the caret is in, what a pick splices in, and
                       what a finished message invokes
  useCommandMenu.ts  — the menu engine: matching and keyboard selection
  CommandMenu.tsx    — the menu above the composer
  commands.css       — its styles
```

## Why this exists

The chat bar acquired a fourth job in v7.20.0: a typed message can reach the
**lecturer** as well as the researcher, decided by a classifier that reads the
words. That works, and it is what serves a reader who writes *"summarize these
papers for me"* without knowing the app has commands at all — but it costs
~780ms on every message that isn't obviously a lecture, and it can be wrong.

A command is the other end of that trade. `/lecture history` states the
destination *and* the framing, so nothing is inferred, nothing is billed, and
there is nothing to correct. It is the deterministic fast path made
first-class, and it is what lets the panel's Lecture section — a button, a
framing pair and an explanatory paragraph taking permanent space above the
conversation — be deleted rather than merely folded away.

## Design decisions worth knowing

- **Commands are anchored to the start of the message; mentions are not.** An
  `@`-mention is a *reference inside* a sentence, so it opens at any `@` that
  starts a word. A command is what the message **is**, so it opens only at the
  first non-blank character. That single rule is what makes a prefix as common
  as `/` safe: a URL's slashes, `9/13`, `2/3` and `p/q` are all mid-message, so
  none of them can open the menu. The negatives are pinned by test, because
  they are the whole reason the prefix works.
- **`/` rather than `!`.** The composer already owns `@`, and `/` is what
  every other app puts a command menu behind (Claude Code, Slack, Discord,
  Notion), so the two read as siblings. `!` would have been a third unrelated
  convention in one text box.
- **The menu is the documentation.** Each row is a label over a one-line hint,
  and the hint is load-bearing: with the Lecture section gone, this menu is
  where a reader finds out lectures exist and what Summary and History mean.
  A command with arguments inserts `/name ` and re-opens on its values, so the
  reader is walked through the whole invocation instead of having to remember
  what it accepts — hence the `›` on a row that continues.
- **The registry gates recognition, not just display.** `useCommandMenu` and
  `readCommand` are both given the same command list, and the composer passes
  an empty one when there is no graph. So `/lecture` with nothing on screen is
  not a hidden-but-live command that would silently no-op; it is not a command
  at all, and the message goes to the router as words.
- **`readCommand` is strict, and what it declines is a feature.** The name must
  match exactly and what follows must be empty or one of the command's own
  values. `/lecture on transformers` is therefore *not* a command — it falls
  through to the ordinary path, where the router reads it as words and will
  almost certainly send it to the lecturer anyway. The alternatives were worse:
  silently ignoring words the reader typed, or inventing a topic argument the
  lecturer cannot honour (it narrates the scoped graph, and a topic is not a
  scope).
- **No debounce, no abort, no phase line** — the list is static and local, so
  matching is a filter over an array. That is also why the keyboard selection
  is tracked **by index** here and **by id** in `useMentionSuggestions`: the
  mention list is re-ranked underneath the reader when the full results land,
  so an index would point at a different paper than the one they were looking
  at; these rows never move under a fixed query.

## Who uses it

`teacher/Teacher.tsx` only. It is the first branch of `submitQuestion`'s
decision tree — ahead of a pasted arXiv id, a bare `@`-mention, an unresolved
`@phrase` and finally the router — because it is the only branch where the
message is *entirely* an instruction. A `/lecture` call runs
`lectureInChat(..., routed: false)`: the reader named the destination, so the
turn carries no offer to re-route it.

## How it is verified

`frontend/test/commands/` mirrors this folder. `parse.test.ts` pins the grammar
— above all the phrasings that must **not** open the menu or count as a
command — and `useCommandMenu.test.ts` covers the selection behaviour a grammar
test can't reach: the highlight resetting when the rows change under it,
clamping when the list shrinks, and Escape staying dismissed until the text
actually changes.
