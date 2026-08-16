/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Hand Markdown to remark-math with its dollars already sorted out: real math
 * in the delimiters remark-math understands, and every *literal* dollar
 * escaped so it cannot open a formula.
 *
 * The bug this exists for: an answer wrote "companies raised $3.77 billion …"
 * and, further down the same paragraph, "$1.8 billion in 2024". remark-math
 * paired those two dollars and rendered everything between them — prose, a
 * URL, punctuation — as one inline formula. It came out italic and
 * letter-spaced nonsense, and because KaTeX output cannot wrap, the 500px
 * result scrolled the docked assistant panel sideways.
 *
 * We already had the right rule for this: {@link splitMath} applies the
 * CommonMark boundary rules (an opener isn't followed by whitespace, a closer
 * isn't preceded by whitespace or followed by a digit), which is what makes
 * "costs $5 and $10" prose rather than a formula. This module makes that
 * verdict *binding* on remark-math — splitMath decides what is math, and
 * everything it left as text gets its dollars escaped, so the two can no
 * longer disagree. Math runs are re-emitted in `$…$` / `$$…$$`, which also
 * teaches answers the `\(…\)` and `\[…\]` forms that remark-math ignores.
 *
 * Code is left completely alone — a fenced block or an inline span may say
 * `$HOME`, and inside code a backslash is a backslash, not an escape.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { splitMath } from './splitMath'

/**
 * A run of code, fenced or inline — the parts of the document this module
 * must not touch. The unterminated-fence alternative matters mid-stream: an
 * answer that is still typing its code block should not have the rest of the
 * answer treated as prose the instant the fence opens.
 */
const CODE_RUN = /(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g

/**
 * Escape the dollars in one run of non-code, non-math text.
 *
 * A dollar already carrying its own backslash is left as it is — escaping it
 * again would produce `\\$`, a literal backslash followed by a live math
 * opener, which is the very thing being prevented.
 *
 * @param text The text run.
 * @returns The run with every literal `$` escaped.
 */
function escapeDollars(text: string): string {
  return text.replace(/(^|[^\\])\$/g, '$1\\$')
}

/**
 * Normalise one code-free stretch: math re-delimited, literal dollars escaped.
 *
 * @param markdown The stretch of Markdown between two code runs.
 * @returns The stretch, safe to hand to remark-math.
 */
function prepareStretch(markdown: string): string {
  return splitMath(markdown)
    .map((segment) => {
      if (segment.kind === 'text') return escapeDollars(segment.value)
      const fence = segment.display ? '$$' : '$'
      return `${fence}${segment.value}${fence}`
    })
    .join('')
}

/**
 * Prepare an agent's Markdown for remark-math.
 *
 * @param markdown The raw answer/beat text, as the agent wrote it.
 * @returns The same Markdown with only genuine math left in dollar
 *          delimiters.
 */
export function prepareMath(markdown: string): string {
  // One capture group, so `split` alternates text, code, text, code… and the
  // odd indices are exactly the code runs to pass through untouched.
  return markdown
    .split(CODE_RUN)
    .map((part, index) => (index % 2 === 1 ? part : prepareStretch(part)))
    .join('')
}
