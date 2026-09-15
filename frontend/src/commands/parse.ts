/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The `/`-command grammar, as pure functions: the command registry, finding the
 * command being typed, inserting a pick, and reading a finished message back
 * out as an invocation.
 *
 * This is `mentions/parse.ts`'s sibling, and the two differ in one deliberate
 * way. An `@`-mention is a *reference inside* a message — it can sit anywhere,
 * so it opens at any `@` that starts a word. A command is what the message
 * **is**, so it is anchored to the start of the composer and nowhere else.
 * That anchoring is what makes `/` safe as a prefix: a URL's slashes, a date
 * like `9/13` and a fraction are all mid-message, so none of them can open the
 * menu.
 *
 * Kept out of the composer for the same reason the mention grammar is: these
 * rules decide what a message means, and rules that consequential should be
 * readable and testable without rendering a textarea.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/** The character that opens a command, at the start of the message only. */
export const COMMAND_PREFIX = '/'

/** One value a command accepts, offered as its own row once the command is typed. */
export interface CommandArgument {
  /** The word the reader types, and what the backend is given. */
  value: string
  /** How the row reads — capitalised, because it is a label not a token. */
  label: string
  /** One line saying what picking it does. */
  hint: string
}

/** A command the composer offers. */
export interface Command {
  /** The name after the `/`, lowercase and single-word. */
  name: string
  /** One line saying what the command does, shown under its row. */
  hint: string
  /**
   * The values it accepts. A command with arguments inserts its name plus a
   * space and leaves the menu open on them, so the reader never has to know
   * what the options were called.
   */
  args: CommandArgument[]
  /** Which argument a bare `/name` means, so the command works without one. */
  defaultArg: string
}

/**
 * Every command the composer knows.
 *
 * One entry, deliberately. A command *system* invites a dozen (`/clear`,
 * `/sources`, `/filters` — every control in the panel has a name), but the
 * shape has to earn that first: one real command, used, before the menu
 * becomes a second UI to maintain alongside the buttons.
 */
export const COMMANDS: Command[] = [
  {
    name: 'lecture',
    // This line carries more weight than a tooltip normally would. The panel
    // used to explain lectures in a paragraph above the button — what they
    // cover is *your* choice, made by filtering or selecting rather than
    // picked from a menu — and deleting the section deleted the paragraph. So
    // the one fact that has to survive into one line is that second half:
    // without it a reader reasonably assumes the lecture decides its own
    // subject. The rest of the old paragraph lives in the tour's lecture step.
    hint: 'Narrate the papers you have on screen — filter or select to choose which',
    args: [
      // Said in the second person and without the word "scoped": the row above
      // has just told them the scope is theirs, and these two only have to say
      // how the same set gets told.
      {
        value: 'summary',
        label: 'Summary',
        hint: 'Group them into their key themes',
      },
      {
        value: 'history',
        label: 'History',
        hint: 'Tell them oldest to newest, as one story',
      },
    ],
    defaultArg: 'summary',
  },
]

/** The command being typed, as found by {@link activeCommand}. */
export interface ActiveCommand {
  /**
   * Which half of the command the caret is in: the name itself, or the
   * argument after it. The menu shows commands for one and that command's
   * values for the other.
   */
  stage: 'name' | 'argument'
  /** The command whose argument is being typed. Only set at the `argument` stage. */
  command?: Command
  /** The text being matched — the partial name, or the partial argument. */
  query: string
  /** Where the replacement starts (the `/` itself, or the argument's first character). */
  start: number
  /** Index just past the caret — where the replacement ends. */
  end: number
}

/**
 * The command the caret sits inside, or null when the message isn't one.
 *
 * Leading whitespace is allowed and ignored — a stray space before `/` is a
 * typo, not a decision — but the `/` must be the first non-blank character of
 * the message. Everything after the caret is left alone, so editing back into
 * a finished command re-opens the menu on the part being edited.
 *
 * @param text     The full composer text.
 * @param caret    The caret position (selectionStart).
 * @param commands The commands on offer, which may be fewer than
 *                 {@link COMMANDS} when the panel can't run them all.
 * @returns The active command, or null.
 */
export function activeCommand(
  text: string,
  caret: number,
  commands: Command[] = COMMANDS,
): ActiveCommand | null {
  const leading = text.length - text.trimStart().length
  if (text.trimStart()[0] !== COMMAND_PREFIX) return null
  const before = text.slice(0, caret)
  // A newline ends a command: the first line is the invocation, anything after
  // it is prose the reader has moved on to.
  if (before.includes('\n')) return null
  const typed = before.slice(leading + 1)
  const space = typed.indexOf(' ')
  if (space === -1) {
    return { stage: 'name', query: typed, start: leading, end: caret }
  }
  const command = commands.find((entry) => entry.name === typed.slice(0, space))
  if (!command || command.args.length === 0) return null
  const argument = typed.slice(space + 1)
  // A second space means the reader is writing a sentence, not an argument —
  // no command takes two, so stop offering values for one.
  if (argument.includes(' ')) return null
  return {
    stage: 'argument',
    command,
    query: argument,
    start: leading + 1 + space + 1,
    end: caret,
  }
}

/** One row in the command menu — a command or one of its values, flattened so
 *  the menu renders both the same way. */
export interface CommandChoice {
  /** Stable key, and what the keyboard selection is remembered by. */
  id: string
  /** How the row reads. */
  label: string
  /** One line under the label saying what it does. */
  hint: string
  /** The text that replaces {@link ActiveCommand.query} when this is picked. */
  insert: string
  /** Whether picking this leaves the menu open on the next stage. */
  continues: boolean
}

/**
 * The rows to offer for what is being typed.
 *
 * Matching is a **prefix** test, not the substring test a paper search uses: a
 * command's name is a short token the reader is part-way through typing, so
 * `lec` should find `lecture` while `ture` should not. Prefix matching also
 * keeps the order stable, which is what lets the keyboard selection be tracked
 * by index here (see `useCommandMenu`) rather than by id the way the mention
 * dropdown has to.
 *
 * @param active   The command being typed.
 * @param commands The commands on offer.
 * @returns The matching rows, in registry order.
 */
export function commandChoices(
  active: ActiveCommand,
  commands: Command[] = COMMANDS,
): CommandChoice[] {
  const query = active.query.toLowerCase()
  if (active.stage === 'argument') {
    const command = active.command
    if (!command) return []
    return command.args
      .filter((argument) => argument.value.startsWith(query))
      .map((argument) => ({
        id: `${command.name}:${argument.value}`,
        label: argument.label,
        hint: argument.hint,
        insert: `${argument.value} `,
        continues: false,
      }))
  }
  return commands
    .filter((command) => command.name.startsWith(query))
    .map((command) => ({
      id: command.name,
      label: `${COMMAND_PREFIX}${command.name}`,
      hint: command.hint,
      // A command with values inserts its name and a space, which re-opens the
      // menu on those values — so the reader is walked through the whole
      // invocation instead of having to remember what it accepts.
      insert:
        command.args.length > 0
          ? `${COMMAND_PREFIX}${command.name} `
          : `${COMMAND_PREFIX}${command.name}`,
      continues: command.args.length > 0,
    }))
}

/**
 * Splice a picked row into the composer text.
 *
 * @param text   The full composer text.
 * @param active The command being typed.
 * @param choice The picked row.
 * @returns The new text and where to put the caret.
 */
export function insertCommand(
  text: string,
  active: ActiveCommand,
  choice: CommandChoice,
): { text: string; caret: number } {
  return {
    text: text.slice(0, active.start) + choice.insert + text.slice(active.end),
    caret: active.start + choice.insert.length,
  }
}

/** A finished command, ready to run — see {@link readCommand}. */
export interface CommandCall {
  command: Command
  /** The chosen value, or the command's default when none was typed. */
  arg: string
}

/**
 * What a finished message invokes, or null when it invokes nothing.
 *
 * The rule is strict on purpose: the name must match exactly, and what follows
 * must be either nothing or one of the command's own values. **Anything else
 * is not a command** — `/lecture on transformers` returns null and the message
 * goes down the ordinary path, where the v7.20.0 router reads it as words and
 * will almost certainly route it to the lecturer anyway. That degrades far
 * better than the alternatives: silently ignoring the words the reader typed,
 * or inventing a topic argument the lecturer has no way to honour (it narrates
 * the scoped graph, and a topic isn't a scope).
 *
 * @param text     The composer text, trimmed or not.
 * @param commands The commands on offer. A command the panel can't currently
 *                 run is absent, so typing it falls through to the router
 *                 rather than firing something that would no-op.
 * @returns The invocation, or null.
 */
export function readCommand(text: string, commands: Command[] = COMMANDS): CommandCall | null {
  const message = text.trim()
  if (message[0] !== COMMAND_PREFIX) return null
  if (message.includes('\n')) return null
  const [name, ...rest] = message.slice(1).split(/\s+/)
  const command = commands.find((entry) => entry.name === name.toLowerCase())
  if (!command) return null
  if (rest.length === 0) return { command, arg: command.defaultArg }
  if (rest.length > 1) return null
  const argument = command.args.find((entry) => entry.value === rest[0].toLowerCase())
  return argument ? { command, arg: argument.value } : null
}
