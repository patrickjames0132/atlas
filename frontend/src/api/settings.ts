/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The settings modal's backend: read the active config file, write it back
 * validated, and repoint the app at a different file. The modal is a
 * config-file editor — the file stays the single source of truth, and the
 * server applies accepted writes to the running app without a restart.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/**
 * The config file's parsed contents. Only the sections the modal edits are
 * typed; everything else rides along untouched (the whole object round-trips
 * back to the server on save, so unknown sections must be preserved).
 */
export interface AtlasConfig {
  storage: { data_dir: string; s2_corpus: string | null; [key: string]: unknown }
  providers: {
    default_provider: 's2' | 'openalex'
    s2: {
      api_key: string
      graph_url: string
      recs_url: string
      timeout: number
      min_interval: number
    }
    openalex: {
      api_key: string
      mailto: string
      base_url: string
      timeout: number
      min_interval: number
    }
  }
  graph: { cache_ttl: number; [key: string]: unknown }
  ui: { default_theme: 'dark' | 'light'; [key: string]: unknown }
  llm: {
    providers: {
      anthropic?: { api_key: string; [key: string]: unknown }
      openai?: { api_key: string; base_url: string; [key: string]: unknown }
      google?: { api_key: string; [key: string]: unknown }
      ollama?: { base_url: string; [key: string]: unknown }
      [key: string]: unknown
    }
    agents: { id: string; model: string; extras?: Record<string, number>; [key: string]: unknown }[]
    [key: string]: unknown
  }
  [section: string]: unknown
}

/** What the settings endpoints return: the active file and its contents. */
export interface SettingsPayload {
  /** Absolute path of the config file the app is running on. */
  path: string
  config: AtlasConfig
}

/** One rejected setting: where it is in the config, and what's wrong with it. */
export interface SettingsFieldError {
  /** Dotted config path, e.g. "llm.agents.3.extras.min_beats". */
  path: string
  message: string
}

/**
 * A failed settings write. `message` is a one-line summary; `fields` carries
 * the per-setting detail the modal renders as a list.
 */
export class SettingsError extends Error {
  fields: SettingsFieldError[]

  constructor(message: string, fields: SettingsFieldError[] = []) {
    super(message)
    this.fields = fields
  }
}

/**
 * Parse a settings response, raising {@link SettingsError} on a 400.
 *
 * @param res The fetch response from any settings endpoint.
 * @returns The settings payload.
 */
async function parse(res: Response): Promise<SettingsPayload> {
  const body = (await res.json()) as SettingsPayload & {
    error?: string
    fields?: SettingsFieldError[]
  }
  if (!res.ok) {
    throw new SettingsError(
      body.error ?? `settings request failed (${res.status})`,
      body.fields ?? [],
    )
  }
  return body
}

/**
 * Fetch the active config file's path and contents.
 *
 * @returns The settings payload.
 */
export async function getSettings(): Promise<SettingsPayload> {
  return parse(await fetch('/api/settings'))
}

/**
 * Write a complete config back to the active file and apply it live.
 *
 * @param config The full config object (the edited copy of what GET returned).
 * @returns The fresh settings payload.
 */
export async function putSettings(config: AtlasConfig): Promise<SettingsPayload> {
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  })
  return parse(res)
}

/**
 * Repoint the app at a different config file — or back to the default.
 *
 * @param path The new config file's absolute path; an empty string returns to
 *   the repo's default config.json.
 * @returns The fresh settings payload (already loaded from the new file).
 */
export async function putSettingsLocation(path: string): Promise<SettingsPayload> {
  const res = await fetch('/api/settings/location', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return parse(res)
}

/**
 * Open the OS file chooser on the server's machine (same machine as the
 * browser in this app's model) and report the picked path — a browser's own
 * file input never reveals absolute paths, and the config sidecar needs one.
 *
 * @returns The chosen file's absolute path, or null when cancelled.
 */
export async function pickSettingsFile(): Promise<string | null> {
  const res = await fetch('/api/settings/pick', { method: 'POST' })
  const body = (await res.json()) as { path: string | null }
  return body.path
}

/** Model ids per configured vendor, plus which vendors exist and which work. */
export interface AgentModels {
  /** Vendor name -> its model ids. A vendor present with an empty list is
   *  configured but could not be listed (offline, bad key) — still selectable. */
  models: Record<string, string[]>
  /** Configured vendors, in config declaration order. Empty = no LLM set up. */
  vendors: string[]
  /** Every vendor the backend can build, configured or not — what the modal
   *  offers, so the free ones are discoverable before they are set up. */
  known: string[]
}

/**
 * The model ids available per configured LLM vendor.
 *
 * Every failure degrades to "nothing known" rather than throwing: the model
 * field is a text input with suggestions, so an unreachable vendor costs the
 * user autocomplete, never the ability to configure one by hand.
 *
 * @returns The per-vendor listing, empty when no vendor is configured.
 */
export async function getAgentModels(): Promise<AgentModels> {
  try {
    const res = await fetch('/api/settings/models')
    const body = (await res.json()) as Partial<AgentModels>
    return { models: body.models ?? {}, vendors: body.vendors ?? [], known: body.known ?? [] }
  } catch {
    return { models: {}, vendors: [], known: [] }
  }
}

/**
 * Empty the derived-data cache: graph snapshots, search results, paper
 * hydration.
 *
 * Safe by construction — everything in it can be refetched, and saved
 * sessions live in a different store — so this never asks the backend for
 * confirmation. The confirming happens in the UI, because the *cost* is real
 * (a slow next few minutes against a rate-limited provider) even though the
 * risk isn't.
 *
 * @returns How many entries were removed.
 * @throws When the request fails — the modal shows it rather than claiming a
 *         success it can't vouch for.
 */
export async function dropCache(): Promise<number> {
  const res = await fetch('/api/settings/drop_cache', { method: 'POST' })
  if (!res.ok) throw new Error(`Couldn't drop the cache (${res.status})`)
  const body = (await res.json()) as { removed: number }
  return body.removed ?? 0
}
