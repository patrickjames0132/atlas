/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Split a string into ordered text and math segments so the surrounding UI can
 * render the text plainly and hand each math run to KaTeX.
 *
 * We recognise the four LaTeX delimiters that show up in paper text (S2
 * abstracts, Claude's lecture beats and answers): display `$$…$$` and `\[…\]`,
 * inline `$…$` and `\(…\)`. Only *delimited* math is treated as math — bare
 * plain-text like "CO2" is left untouched on purpose (auto-subscripting arbitrary
 * digits misfires on "GPT4", "COVID19", "Section 2").
 *
 * The inline `$…$` rule is the tricky one, because prose says "costs $5 and $10".
 * We use the CommonMark math-extension boundary rule: an opening `$` must not be
 * followed by whitespace, a closing `$` must not be preceded by whitespace, and a
 * closing `$` must not be immediately followed by a digit. Currency runs fail all
 * three and fall back to text. Unclosed delimiters (common mid-stream while an
 * answer is still typing) also fall back to text, so nothing crashes.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/** One run of the input: literal text, or a math expression for KaTeX. */
export type MathSegment =
  | { readonly kind: 'text'; readonly value: string }
  | { readonly kind: 'math'; readonly value: string; readonly display: boolean }

/**
 * True when the character is whitespace (or absent, i.e. string edge).
 *
 * @param char The character to test, or undefined at a string edge.
 * @returns Whether it counts as a whitespace boundary.
 */
function isWhitespace(char: string | undefined): boolean {
  return char === undefined || /\s/.test(char)
}

/**
 * Find the closing `$` of an inline math run opened at `openIndex`, applying the
 * CommonMark boundary rules.
 *
 * @param input     The whole string being split.
 * @param openIndex The index of the candidate opening `$`.
 * @returns The index of the closing `$`, or -1 when this `$` doesn't open a
 *          valid inline run (so it should be treated as text).
 */
function findInlineClose(input: string, openIndex: number): number {
  // An opening `$` immediately followed by whitespace (or end of string) is not
  // a math opener — "$ 5" reads as currency/prose, never a formula.
  if (isWhitespace(input[openIndex + 1])) return -1
  for (let cursor = openIndex + 1; cursor < input.length; cursor++) {
    // Skip an escaped character so `\$` inside the run isn't read as a closer.
    if (input[cursor] === '\\') {
      cursor++
      continue
    }
    if (input[cursor] === '$') {
      // A closer can't sit right after whitespace ("and $10" → the space rules
      // it out) or right before a digit ("$5" currency).
      if (isWhitespace(input[cursor - 1])) return -1
      if (/\d/.test(input[cursor + 1] ?? '')) continue
      return cursor
    }
  }
  return -1
}

/**
 * Locate the matching closer for a `\[…\]` or `\(…\)` run.
 *
 * @param input        The whole string being split.
 * @param contentStart The index just past the opening delimiter.
 * @param closer       The closing delimiter to look for.
 * @returns The closer's index, or -1 if unterminated.
 */
function findBracketClose(input: string, contentStart: number, closer: string): number {
  const closeIndex = input.indexOf(closer, contentStart)
  return closeIndex
}

/**
 * Break `input` into text and math segments. A string with no delimited math
 * comes back as a single text segment, so callers can cheaply skip KaTeX.
 *
 * @param input The raw text (prose, possibly with LaTeX runs).
 * @returns The ordered text/math segments.
 */
export function splitMath(input: string): MathSegment[] {
  const segments: MathSegment[] = []
  let buffer = ''
  let index = 0

  const flushText = () => {
    if (buffer) {
      segments.push({ kind: 'text', value: buffer })
      buffer = ''
    }
  }

  while (index < input.length) {
    const char = input[index]
    const next = input[index + 1]

    // Display `$$…$$` — checked before inline `$…$` so it wins the longer match.
    if (char === '$' && next === '$') {
      const closeIndex = input.indexOf('$$', index + 2)
      if (closeIndex !== -1) {
        flushText()
        segments.push({ kind: 'math', value: input.slice(index + 2, closeIndex), display: true })
        index = closeIndex + 2
        continue
      }
    }

    // Display `\[…\]`.
    if (char === '\\' && next === '[') {
      const closeIndex = findBracketClose(input, index + 2, '\\]')
      if (closeIndex !== -1) {
        flushText()
        segments.push({ kind: 'math', value: input.slice(index + 2, closeIndex), display: true })
        index = closeIndex + 2
        continue
      }
    }

    // Inline `\(…\)`.
    if (char === '\\' && next === '(') {
      const closeIndex = findBracketClose(input, index + 2, '\\)')
      if (closeIndex !== -1) {
        flushText()
        segments.push({ kind: 'math', value: input.slice(index + 2, closeIndex), display: false })
        index = closeIndex + 2
        continue
      }
    }

    // Inline `$…$`, subject to the CommonMark boundary rules.
    if (char === '$') {
      const closeIndex = findInlineClose(input, index)
      if (closeIndex !== -1) {
        flushText()
        segments.push({ kind: 'math', value: input.slice(index + 1, closeIndex), display: false })
        index = closeIndex + 1
        continue
      }
    }

    buffer += char
    index++
  }

  flushText()
  return segments
}
