/**
 * The app's light/dark theme: a tiny module-level store, not a context.
 *
 * Two very different consumers need the current theme — the header's toggle
 * button and the graph canvas (which paints with JS, so it can't just read a
 * CSS variable in a stylesheet) — and they sit at opposite ends of the tree.
 * A module store with `useSyncExternalStore` gets both without threading a
 * provider through everything in between.
 *
 * The palette itself stays in CSS (`index.css`): dark is the `:root` default,
 * light is a `:root[data-theme='light']` override. This module only decides
 * *which* is active by stamping `data-theme` on the document element — so
 * adding a themed color is a stylesheet edit, not a TypeScript one.
 */

import { useSyncExternalStore } from 'react'

/** The two themes. Dark is the default and the app's native look. */
export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'atlas.theme'

/**
 * The stored preference, or dark.
 *
 * Deliberately **not** `prefers-color-scheme`: Atlas is a dark-first app, and
 * a light OS setting shouldn't silently hand a first-time user the theme we
 * treat as the alternative. An explicit toggle is the only way into light.
 *
 * @returns The theme to start in.
 */
function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark' // private mode / storage disabled — dark is the safe default
  }
}

let current: Theme = readStored()
const listeners = new Set<() => void>()

/**
 * Whether the user has ever picked a theme in this browser.
 *
 * Distinguishes "dark because that's the fallback" from "dark because they
 * chose it" — the configured default may only fill the former.
 *
 * @returns True when a choice is stored.
 */
export function hasStoredChoice(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== null
  } catch {
    return false
  }
}

/**
 * Stamp the theme onto the document element, where the CSS override hangs off.
 *
 * No-ops without a document: this module is imported (transitively, via
 * `graph/theme`) by pure logic that the test suite runs in a node
 * environment, and a store shouldn't demand a DOM just to be loaded.
 *
 * @param theme The theme to apply.
 */
function paint(theme: Theme): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = theme
}

paint(current)

/**
 * Switch themes: applies it, persists it, and notifies subscribers.
 *
 * @param theme The theme to switch to.
 */
export function setTheme(theme: Theme): void {
  if (theme === current) return
  current = theme
  paint(theme)
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Persistence is a nicety; the toggle still works for this session.
  }
  for (const listener of listeners) listener()
}

/**
 * Adopt the config's default theme — for a browser that has never chosen one.
 *
 * Deliberately does **not** persist: writing it would turn a config default
 * into the user's own stored choice, and then changing the config would stop
 * reaching browsers that had merely visited. A no-op once a real choice
 * exists, so the toggle always wins.
 *
 * @param theme The configured default.
 */
export function applyConfiguredDefault(theme: Theme): void {
  if (hasStoredChoice() || theme === current) return
  current = theme
  paint(theme)
  for (const listener of listeners) listener()
}

/**
 * Subscribe to theme changes (the `useSyncExternalStore` contract).
 *
 * @param listener Called after every change.
 * @returns The unsubscribe function.
 */
function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/**
 * The active theme, re-rendering the caller whenever it changes.
 *
 * @returns The current theme.
 */
export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => 'dark' as Theme,
  )
}
