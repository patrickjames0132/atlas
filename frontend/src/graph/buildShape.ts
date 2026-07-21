/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The build shape — how much of a seed's neighborhood the backend ships.
 *
 * A module-level store behind `useSyncExternalStore`, the same shape as
 * `ui/theme.ts` and for the same reason: its consumers sit at opposite ends of
 * the tree (the settings modal writes it, the graph controls read it to decide
 * whether the count sliders exist, and `loadGraph` reads it *outside* React
 * entirely to put it on the request).
 *
 * **Why this isn't a config setting.** Every other knob in the app lives in
 * `config.json`. This one belongs to the person exploring, not to the
 * deployment, and it changes between one build and the next — so it's carried
 * by the browser and sent per request. The v6.0.0 purge deleted the old file
 * toggles for exactly this reason; this deliberately does not bring them back.
 *
 * **Why it isn't a Redux slice either.** The workspace slice holds `provider`,
 * which is the closest analogue — but `provider` is part of a *saved session*,
 * and the shape isn't: reopening a saved graph should rebuild it the way *you*
 * currently size graphs, not the way whoever saved it did. localStorage, like
 * the theme, is the honest home for that.
 *
 * `adaptive` is the headline. ON (the default) means the app sizes itself and
 * the other three fields are inert — the backend ignores them, and the controls
 * hide the per-chip count sliders. OFF hands sizing to the user.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useSyncExternalStore } from 'react'

/** The user's graph-sizing preferences, as sent to the backend. */
export interface BuildShape {
  /** App-sized (true) or user-sized (false) — see the module docstring. */
  adaptive: boolean
  /** First year the Latest bands cover; null keeps the fixed band span. */
  clusterStart: number | null
  /** How many one-year Latest bands the fixed span covers. */
  numberOfBands: number
  /** Top-N most-cited citers each one-year band keeps. */
  nodesPerBand: number
}

/**
 * The shipped defaults, mirroring the backend's `integrations/caps.py`.
 *
 * Duplicated rather than fetched because they're only ever *shown* — an
 * adaptive build ignores them, and a non-adaptive one sends whatever's here, so
 * a drift between the two costs a wrong number in a disabled input, not a
 * wrongly-sized graph.
 */
export const DEFAULT_SHAPE: BuildShape = {
  adaptive: true,
  clusterStart: null,
  numberOfBands: 5,
  nodesPerBand: 50,
}

const STORAGE_KEY = 'atlas.buildShape'

/**
 * The stored shape, or the adaptive default.
 *
 * Every field is re-validated rather than trusted: a stored blob can outlive
 * the version that wrote it, and a half-parsed shape would silently mis-size
 * every graph the user builds from then on.
 *
 * @returns The shape to start with.
 */
function readStored(): BuildShape {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SHAPE
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return DEFAULT_SHAPE
    const stored = parsed as Partial<BuildShape>
    return {
      adaptive: stored.adaptive !== false,
      clusterStart: typeof stored.clusterStart === 'number' ? stored.clusterStart : null,
      numberOfBands:
        typeof stored.numberOfBands === 'number'
          ? stored.numberOfBands
          : DEFAULT_SHAPE.numberOfBands,
      nodesPerBand:
        typeof stored.nodesPerBand === 'number' ? stored.nodesPerBand : DEFAULT_SHAPE.nodesPerBand,
    }
  } catch {
    return DEFAULT_SHAPE // private mode, disabled storage, or corrupt JSON
  }
}

let current: BuildShape = readStored()
const listeners = new Set<() => void>()

/**
 * Replace the build shape: persists it and notifies subscribers.
 *
 * Does **not** rebuild the graph — the caller decides whether a change is worth
 * a refetch, because the modal writes on every keystroke of a number field and
 * rebuilding on each would hammer the provider.
 *
 * @param shape The new shape.
 */
export function setBuildShape(shape: BuildShape): void {
  current = shape
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(shape))
  } catch {
    // Persistence is a nicety; the shape still applies for this session.
  }
  for (const listener of listeners) listener()
}

/**
 * The current shape, for non-React readers (`loadGraph` building a request).
 *
 * @returns The active build shape.
 */
export function getBuildShape(): BuildShape {
  return current
}

/**
 * Subscribe to shape changes (the `useSyncExternalStore` contract).
 *
 * @param listener Called after every change.
 * @returns The unsubscribe function.
 */
function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/**
 * The active build shape, re-rendering the caller whenever it changes.
 *
 * @returns The current shape.
 */
export function useBuildShape(): BuildShape {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => DEFAULT_SHAPE,
  )
}

/**
 * Whether two shapes would produce the same graph from the backend.
 *
 * Two adaptive shapes always match however their band fields differ — the
 * backend ignores those while adaptive is on, so comparing them would trigger
 * rebuilds that return a byte-identical graph.
 *
 * @param one The first shape.
 * @param other The second shape.
 * @returns True when a rebuild would be pointless.
 */
export function sameBuild(one: BuildShape, other: BuildShape): boolean {
  if (one.adaptive && other.adaptive) return true
  return (
    one.adaptive === other.adaptive &&
    one.clusterStart === other.clusterStart &&
    one.numberOfBands === other.numberOfBands &&
    one.nodesPerBand === other.nodesPerBand
  )
}

/**
 * The shape as `/api/graph` query parameters.
 *
 * An adaptive shape contributes **nothing** — the backend's own default — so
 * the common request URL stays exactly what it was before shapes existed.
 *
 * @param shape The shape to serialize.
 * @returns Entries to append to the request's query string.
 */
export function shapeParams(shape: BuildShape): [string, string][] {
  if (shape.adaptive) return []
  const params: [string, string][] = [
    ['adaptive', '0'],
    ['bands', String(shape.numberOfBands)],
    ['per_band', String(shape.nodesPerBand)],
  ]
  if (shape.clusterStart !== null) params.push(['cluster_start', String(shape.clusterStart)])
  return params
}
