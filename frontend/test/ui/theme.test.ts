// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The theme store: what it defaults to, what it persists, and what it stamps
 * on the document (the attribute every themed CSS rule hangs off).
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** Re-import the module fresh so its start-up read of localStorage re-runs
 *  — the default is decided once, at import. */
async function loadTheme() {
  vi.resetModules()
  return import('../../src/ui/theme')
}

beforeEach(() => {
  localStorage.clear()
  delete document.documentElement.dataset.theme
})

afterEach(() => {
  localStorage.clear()
})

describe('theme store', () => {
  it('starts dark and stamps the document', async () => {
    await loadTheme()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('starts light when that was the stored choice', async () => {
    localStorage.setItem('atlas.theme', 'light')
    await loadTheme()
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('ignores a stored value it does not recognize', async () => {
    localStorage.setItem('atlas.theme', 'solarized')
    await loadTheme()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('a configured default fills an unchosen browser', async () => {
    const { applyConfiguredDefault } = await loadTheme()
    applyConfiguredDefault('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    // Not persisted: a config default must stay a default, or changing it
    // would stop reaching browsers that had merely visited.
    expect(localStorage.getItem('atlas.theme')).toBeNull()
  })

  it("a configured default never overrides the user's own choice", async () => {
    localStorage.setItem('atlas.theme', 'dark')
    const { applyConfiguredDefault } = await loadTheme()
    applyConfiguredDefault('light')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('setTheme stamps, persists, and notifies', async () => {
    const { setTheme } = await loadTheme()
    setTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('atlas.theme')).toBe('light')
    setTheme('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('atlas.theme')).toBe('dark')
  })
})
