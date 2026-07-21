/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Best-effort LaTeX → Unicode for graph node titles, which are painted on a
 * canvas (`ctx.fillText`) where KaTeX/HTML can't reach. This is an
 * approximation, not a renderer: it strips the math delimiters, maps Greek
 * letters and simple sub/superscripts to their Unicode equivalents, and leaves
 * anything it can't map as readable source. The goal is only that a title like
 * `$\beta_2$-VAE` reads as "β₂-VAE" on the canvas instead of showing raw `$`.
 *
 * HTML surfaces get real KaTeX via {@link MathText}; this is the canvas-only
 * fallback.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/** LaTeX control words for Greek letters and a few common math symbols. */
const SYMBOLS: Readonly<Record<string, string>> = {
  alpha: 'α',
  beta: 'β',
  gamma: 'γ',
  delta: 'δ',
  epsilon: 'ε',
  varepsilon: 'ε',
  zeta: 'ζ',
  eta: 'η',
  theta: 'θ',
  vartheta: 'ϑ',
  iota: 'ι',
  kappa: 'κ',
  lambda: 'λ',
  mu: 'μ',
  nu: 'ν',
  xi: 'ξ',
  pi: 'π',
  rho: 'ρ',
  sigma: 'σ',
  tau: 'τ',
  upsilon: 'υ',
  phi: 'φ',
  varphi: 'φ',
  chi: 'χ',
  psi: 'ψ',
  omega: 'ω',
  Gamma: 'Γ',
  Delta: 'Δ',
  Theta: 'Θ',
  Lambda: 'Λ',
  Xi: 'Ξ',
  Pi: 'Π',
  Sigma: 'Σ',
  Phi: 'Φ',
  Psi: 'Ψ',
  Omega: 'Ω',
  times: '×',
  cdot: '·',
  pm: '±',
  mp: '∓',
  infty: '∞',
  rightarrow: '→',
  to: '→',
  leftarrow: '←',
  leq: '≤',
  geq: '≥',
  neq: '≠',
  approx: '≈',
  sim: '∼',
  ell: 'ℓ',
  nabla: '∇',
  partial: '∂',
  sum: '∑',
  prod: '∏',
}

/** Unicode subscript glyphs, for the characters that actually have one. */
const SUBSCRIPTS: Readonly<Record<string, string>> = {
  '0': '₀',
  '1': '₁',
  '2': '₂',
  '3': '₃',
  '4': '₄',
  '5': '₅',
  '6': '₆',
  '7': '₇',
  '8': '₈',
  '9': '₉',
  '+': '₊',
  '-': '₋',
  '=': '₌',
  '(': '₍',
  ')': '₎',
  a: 'ₐ',
  e: 'ₑ',
  i: 'ᵢ',
  j: 'ⱼ',
  o: 'ₒ',
  x: 'ₓ',
  n: 'ₙ',
}

/** Unicode superscript glyphs, for the characters that actually have one. */
const SUPERSCRIPTS: Readonly<Record<string, string>> = {
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹',
  '+': '⁺',
  '-': '⁻',
  '=': '⁼',
  '(': '⁽',
  ')': '⁾',
  n: 'ⁿ',
  i: 'ⁱ',
}

/**
 * Map the characters of a sub/superscript group to Unicode. If any character
 * lacks a glyph in the target table, give up on the whole group and return the
 * plain characters — a half-converted "x₂z" reads worse than "x2z".
 *
 * @param group The script group's characters (without the `_`/`^` marker).
 * @param table The subscript or superscript glyph table.
 * @returns The mapped glyphs, or the group unchanged.
 */
function mapScript(group: string, table: Readonly<Record<string, string>>): string {
  let mapped = ''
  for (const char of group) {
    const glyph = table[char]
    if (glyph === undefined) return group
    mapped += glyph
  }
  return mapped
}

/**
 * Convert the LaTeX in `input` to an approximate Unicode string for canvas
 * display. Never throws; unmapped constructs are left as readable text.
 *
 * @param input The raw title text, possibly containing LaTeX.
 * @returns The approximate Unicode rendering.
 */
export function latexToUnicode(input: string): string {
  let text = input

  // Drop the math delimiters — we render the content inline regardless of mode.
  text = text.replace(/\$\$|\$|\\\(|\\\)|\\\[|\\\]/g, '')

  // Control words first: `\beta` → β. This has to precede the sub/superscript
  // pass, or an unmappable script group (`\sigma_{max}` → `\sigmamax`) would
  // glue onto the control word and hide it from this replacement.
  text = text.replace(/\\([A-Za-z]+)/g, (match, name: string) => SYMBOLS[name] ?? match)

  // `_{…}` / `^{…}` groups and their single-character `_x` / `^x` forms.
  text = text.replace(/([_^])\{([^{}]*)\}/g, (_match, marker: string, group: string) =>
    mapScript(group, marker === '_' ? SUBSCRIPTS : SUPERSCRIPTS),
  )
  text = text.replace(/([_^])([A-Za-z0-9+\-=()])/g, (_match, marker: string, group: string) =>
    mapScript(group, marker === '_' ? SUBSCRIPTS : SUPERSCRIPTS),
  )

  // Any leftover single braces from groups we mapped.
  text = text.replace(/[{}]/g, '')

  return text
}
