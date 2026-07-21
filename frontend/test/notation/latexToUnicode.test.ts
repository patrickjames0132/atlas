/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The canvas-only LaTeX → Unicode approximation for node labels: delimiters
 * stripped, Greek and scripts mapped, everything unmappable left readable.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import { latexToUnicode } from '../../src/notation/latexToUnicode'

describe('latexToUnicode', () => {
  it('renders the canonical example: $\\beta_2$-VAE → β₂-VAE', () => {
    expect(latexToUnicode('$\\beta_2$-VAE')).toBe('β₂-VAE')
  })

  it('leaves plain titles untouched', () => {
    expect(latexToUnicode('Attention Is All You Need')).toBe('Attention Is All You Need')
  })

  it('strips all four delimiter styles', () => {
    expect(latexToUnicode('$$x$$ \\(y\\) \\[z\\]')).toBe('x y z')
  })

  it('maps control words to symbols and leaves unknown ones as source', () => {
    expect(latexToUnicode('\\alpha \\to \\omega')).toBe('α → ω')
    expect(latexToUnicode('\\mathbb{R}')).toBe('\\mathbbR')
  })

  it('maps sub/superscript groups character by character', () => {
    expect(latexToUnicode('x_{12}')).toBe('x₁₂')
    expect(latexToUnicode('x^2')).toBe('x²')
  })

  it('gives up on a whole script group rather than half-converting it', () => {
    // 'm' has no Unicode subscript glyph, so "max" stays plain — "σmax"
    // reads better than a half-converted "σₘax".
    expect(latexToUnicode('\\sigma_{max}')).toBe('σmax')
  })
})
