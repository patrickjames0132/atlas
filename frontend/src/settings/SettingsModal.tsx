/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The settings modal — a config-file editor in the style of Claude Desktop's
 * settings: a left sidebar (search + grouped nav) and a right content pane of
 * label-left / control-right rows.
 *
 * Rows are **data** (`ROW_DEFS`): each carries its section, an optional group
 * heading, label + hint text, and a control renderer. That one registry
 * drives rendering *and* the PyCharm-style search — typing filters the nav to
 * sections with a matching row and the pane to the matching rows themselves.
 *
 * The modal loads the active config file on open, edits a local draft, and
 * writes the whole draft back on Save — the server validates before writing
 * anything, applies accepted writes to the running app live, and returns the
 * exact field error on a rejection (shown red in the footer). General's
 * config-file row is the one hand-rendered control (a path field plus a 📁
 * button that opens the OS file chooser via the backend — a browser's own
 * picker never reveals absolute paths); a missing default config.json is
 * auto-created from the example server-side.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useState } from 'react'
import {
  dropCache,
  getAgentModels,
  type AgentModels,
  getSettings,
  pickSettingsFile,
  putSettings,
  putSettingsLocation,
  SettingsError,
  type SettingsFieldError,
  type AtlasConfig,
  type SettingsPayload,
} from '../api'
import { DEFAULT_SHAPE, setBuildShape, useBuildShape } from '../graph/buildShape'
import './settings.css'

/** Bounds for the band-shape inputs, mirroring the backend's own clamps. */
const CURRENT_YEAR = new Date().getFullYear()
const MAX_BANDS = 50
const MAX_PER_BAND = 200 // OpenAlex's page cap — no query can return more.

/** The sidebar's sections, in display order.
 *
 *  A section with `pages` is navigated as sub-pages in the nav tree rather
 *  than as tabs inside the pane: Agents holds two unrelated jobs — vendor
 *  credentials and per-agent tuning — and a tab strip framed them as two views
 *  of one thing. */
const SECTIONS = [
  {
    id: 'general',
    icon: '⚙',
    label: 'General',
    blurb:
      'App-wide preferences: which citation source new graphs open on, the colour theme, how long cached graph snapshots stay fresh, and a button to drop that cache.',
  },
  {
    id: 'graph',
    icon: '🕸',
    label: 'Graph',
    blurb:
      "How big a graph comes back and how its Latest Publications are banded. Left automatic, Atlas sizes each graph from the seed's own citation pool; turn that off to set the bands yourself.",
  },
  {
    id: 'providers',
    icon: '🌐',
    label: 'Data Providers',
    blurb:
      'Where the papers and citations come from — Semantic Scholar and OpenAlex. Both work without a key, just on tighter public rate limits. Also where the optional offline S2 citations corpus is pointed.',
  },
  {
    id: 'agents',
    icon: '🎓',
    label: 'Agents',
    blurb:
      'The AI teacher: the crew that writes lectures, answers questions, and scouts papers and the web. Two halves — which vendors Atlas can reach, and which model each agent runs on. Every agent picks its own, so running the lecturer on a free local model while the web scout stays on a cloud one is a normal setup.',
    pages: [
      { id: 'providers', label: 'Model Providers' },
      { id: 'agents', label: 'Agent Settings' },
    ],
  },
] as const

/** A section id from {@link SECTIONS}. */
type SectionId = (typeof SECTIONS)[number]['id']

/** Apply a mutation to a draft config clone (the `edit` callback's shape). */
type Edit = (mutate: (next: AtlasConfig) => void) => void

/**
 * One agent entry from `llm.agents`, found (or created) by id so a knob can
 * be edited even when the config file never listed that agent's extras.
 *
 * @param draft The draft config to look in / add to.
 * @param id The agent id (e.g. "lecturer").
 * @returns The agent entry, guaranteed to have an extras object.
 */
function agentEntry(
  draft: AtlasConfig,
  id: string,
): { model: string; extras: Record<string, number> } {
  let entry = draft.llm.agents.find((candidate) => candidate.id === id)
  if (!entry) {
    entry = { id, model: '', extras: {} }
    draft.llm.agents.push(entry)
  }
  entry.extras ??= {}
  return entry as { model: string; extras: Record<string, number> }
}

/**
 * A number input that can't produce a value its config field would reject.
 *
 * The server validates every save regardless — this is the second line, so a
 * bounded knob (a `PositiveInt` budget, a `NonNegativeInt` count) can't reach
 * the save bar looking valid: the spinner stops at `min`, and a typed-in
 * lower value is clamped on the way into the draft.
 *
 * @returns The input element.
 */
function NumberInput({
  value,
  min,
  step,
  placeholder,
  onChange,
}: {
  /** Current value; `''` renders empty (an unset optional knob). */
  value: number | ''
  /** Smallest value the config field accepts — 1 for positive, 0 for non-negative. */
  min: number
  step?: number
  /** Shown while empty — the code default an unset knob falls back to. */
  placeholder?: string
  /** Receives the clamped number, or `''` when the field was cleared. */
  onChange: (value: number | '') => void
}) {
  return (
    <input
      type="number"
      min={min}
      step={step}
      placeholder={placeholder}
      value={value}
      onChange={(event) =>
        onChange(event.target.value === '' ? '' : Math.max(min, Number(event.target.value)))
      }
    />
  )
}

/**
 * A numeric agent-extras input: shows the config's override when present,
 * else the code default as a placeholder; clearing the field removes the
 * override (back to the code default). Bounded by the same floor the knob's
 * config field enforces.
 *
 * @returns The input element.
 */
function ExtrasNumber({
  draft,
  edit,
  agentId,
  extrasKey,
  fallback,
  min = 1,
}: {
  draft: AtlasConfig
  edit: Edit
  agentId: string
  extrasKey: string
  fallback: number
  /** 1 for a `PositiveInt` knob (the default), 0 where 0 disables the feature. */
  min?: number
}) {
  const entry = draft.llm.agents.find((candidate) => candidate.id === agentId)
  return (
    <NumberInput
      value={entry?.extras?.[extrasKey] ?? ''}
      min={min}
      placeholder={String(fallback)}
      onChange={(value) =>
        edit((next) => {
          const extras = agentEntry(next, agentId).extras
          if (value === '') delete extras[extrasKey]
          else extras[extrasKey] = value
        })
      }
    />
  )
}

/**
 * The "Drop cache" control: a two-step button that empties the derived-data
 * cache (graph snapshots, search results, paper hydration).
 *
 * Two-step rather than a `window.confirm`, for two reasons: a native dialog
 * blocks the whole page (and every automated session driving it), and the
 * warning worth showing here is specific — what goes, what emphatically does
 * NOT go — which a one-line confirm can't say. Saved sessions live in their
 * own store and are untouched; that is the sentence a reader needs before
 * pressing this.
 *
 * @returns The button, its inline confirmation, and the result line.
 */
function DropCacheButton() {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  /** Empty the cache, then report what happened in place. */
  const drop = async () => {
    setBusy(true)
    try {
      const removed = await dropCache()
      setResult(removed ? `Dropped ${removed.toLocaleString()} cached entries.` : 'Already empty.')
    } catch (error) {
      setResult(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  if (confirming) {
    return (
      <div className="drop-cache confirming">
        <p className="drop-cache-warn">
          This clears every cached graph, search and paper detail. Nothing is lost — it all
          refetches on demand — but the next few graphs will be slow, and a rate-limited provider
          slower still. <strong>Your saved sessions and library are not touched.</strong>
        </p>
        <div className="drop-cache-actions">
          <button type="button" onClick={() => setConfirming(false)} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="danger" onClick={drop} disabled={busy}>
            {busy ? 'Dropping…' : 'Drop it'}
          </button>
        </div>
      </div>
    )
  }
  return (
    <div className="drop-cache">
      <button type="button" onClick={() => setConfirming(true)}>
        Drop cache…
      </button>
      {result && <span className="drop-cache-result">{result}</span>}
    </div>
  )
}

/** One settings row: its home section, search text, and control renderer. */
interface RowDef {
  key: string
  section: SectionId
  /** Optional group heading rendered above the row's cluster (e.g. an agent name). */
  group?: string
  label: string
  hint?: string
  /** Which sub-tab of the Agents section this row belongs to. */
  tab?: AgentTab
  control: (draft: AtlasConfig, edit: Edit, models: AgentModels) => React.ReactNode
}

/** Which sub-page of the Agents section a row belongs to. */
type AgentTab = 'providers' | 'agents'

/**
 * An agent's model, as two controls: which vendor, then which of its models.
 *
 * The single `"vendor:model"` dropdown this replaces made the vendor invisible
 * — it was a prefix inside a long string, and choosing one meant knowing that
 * options were grouped by a heading. Splitting it says the real thing out
 * loud: **each agent picks its own vendor**, so running the lecturer on a free
 * local model while the web scout stays on one that can actually search the
 * web is an obvious move rather than a discovery.
 *
 * Both degrade to text when nothing is listed (no vendor configured, or a
 * server that could not be reached), because a config file the modal cannot
 * describe must still be editable.
 *
 * @returns The vendor select and the model select.
 */
function ModelInput({
  draft,
  edit,
  agentId,
  models,
}: {
  draft: AtlasConfig
  edit: Edit
  agentId: string
  models: AgentModels
}) {
  const current = draft.llm.agents.find((entry) => entry.id === agentId)?.model ?? ''
  const separator = current.indexOf(':')
  const currentVendor = separator === -1 ? '' : current.slice(0, separator)
  const currentModel = separator === -1 ? current : current.slice(separator + 1)

  const apply = (value: string) =>
    edit((next) => {
      agentEntry(next, agentId).model = value
    })

  const usable = models.vendors.filter((vendor) => (models.models[vendor] ?? []).length > 0)
  if (usable.length === 0) {
    return (
      <input
        type="text"
        className="settings-wide"
        value={current}
        onChange={(event) => apply(event.target.value)}
      />
    )
  }

  // A vendor the agent is already on stays offered even when unconfigured —
  // switching vendors must not silently rewrite an entry the user set by hand.
  const vendors = usable.includes(currentVendor) ? usable : [currentVendor, ...usable]
  const forVendor = models.models[currentVendor] ?? []
  // Same rule one level down: keep a model the listing no longer offers.
  const options = forVendor.includes(currentModel) ? forVendor : [currentModel, ...forVendor]

  return (
    <div className="agent-model">
      <select
        aria-label="Vendor"
        value={currentVendor}
        onChange={(event) => {
          const vendor = event.target.value
          const first = models.models[vendor]?.[0]
          apply(first ? `${vendor}:${first}` : `${vendor}:`)
        }}
      >
        {vendors.map((vendor) => (
          <option key={vendor} value={vendor}>
            {VENDOR_LABELS[vendor] ?? (vendor || '(none)')}
          </option>
        ))}
      </select>
      {forVendor.length === 0 ? (
        <input
          type="text"
          aria-label="Model"
          value={currentModel}
          placeholder="model name"
          onChange={(event) => apply(`${currentVendor}:${event.target.value}`)}
        />
      ) : (
        <select
          aria-label="Model"
          value={currentModel}
          onChange={(event) => apply(`${currentVendor}:${event.target.value}`)}
        >
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

/**
 * One credential field for one vendor, creating the vendor's config block on
 * first keystroke if the file predates it.
 *
 * @returns The text input.
 */
function VendorField({
  draft,
  edit,
  vendor,
  field,
}: {
  draft: AtlasConfig
  edit: Edit
  vendor: string
  field: string
}) {
  const block = (draft.llm.providers[vendor] ?? {}) as Record<string, unknown>
  return (
    <input
      type="text"
      className="settings-wide"
      value={(block[field] as string) ?? ''}
      onChange={(event) =>
        edit((next) => {
          const existing = (next.llm.providers[vendor] ?? {}) as Record<string, unknown>
          next.llm.providers[vendor] = { ...existing, [field]: event.target.value }
        })
      }
    />
  )
}

/** What a group's heading badge says, and whether it is the good news.
 *
 *  Cost rides the heading rather than a hint because for the reader this
 *  screen exists for it is the deciding fact: two of these four vendors run
 *  the teacher for nothing. */
const GROUP_BADGES: Record<string, { text: string; free: boolean }> = {
  Anthropic: { text: 'paid', free: false },
  OpenAI: { text: 'paid', free: false },
  Google: { text: 'free tier', free: true },
  Ollama: { text: 'free, local', free: true },
}

/** Display names for the vendors the backend can construct. */
const VENDOR_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google',
  ollama: 'Ollama',
}

/**
 * The adaptive switch — the Graph section's headline control.
 *
 * Unlike every other row here it edits **no config draft**: the build shape
 * belongs to the browser, not the file (see `graph/buildShape.ts`), so it reads
 * and writes the module store directly and applies immediately — the same
 * write-through the config-file location row uses, and the reason neither shows
 * up in the Save bar.
 *
 * @returns The checkbox.
 */
function AdaptiveToggle() {
  const shape = useBuildShape()
  return (
    <label className="settings-switch">
      <input
        type="checkbox"
        checked={shape.adaptive}
        onChange={(event) => setBuildShape({ ...shape, adaptive: event.target.checked })}
        aria-label="Size graphs automatically"
      />
      <span className="settings-switch-track" aria-hidden="true">
        <span className="settings-switch-knob" />
      </span>
    </label>
  )
}

/**
 * One band-shape number, live only while `adaptive` is off.
 *
 * Disabled rather than hidden with adaptive on: the values still describe what
 * turning it off would do, and a row that vanishes mid-search is worse than one
 * that greys out.
 *
 * @returns The number input.
 */
function BandNumber({
  field,
  min,
  max,
  placeholder,
}: {
  field: 'clusterStart' | 'numberOfBands' | 'nodesPerBand'
  min: number
  max: number
  placeholder?: string
}) {
  const shape = useBuildShape()
  const value = shape[field]
  return (
    <input
      type="number"
      min={min}
      max={max}
      disabled={shape.adaptive}
      placeholder={placeholder}
      value={value ?? ''}
      onChange={(event) => {
        const raw = event.target.value
        // Cleared -> null is meaningful for clusterStart ("no start named",
        // i.e. keep the fixed span); the two counts fall back to their default.
        if (raw === '') {
          setBuildShape({
            ...shape,
            [field]: field === 'clusterStart' ? null : DEFAULT_SHAPE[field],
          })
          return
        }
        const parsed = Number(raw)
        if (Number.isNaN(parsed)) return
        setBuildShape({ ...shape, [field]: Math.max(min, Math.min(max, Math.round(parsed))) })
      }}
    />
  )
}

/** Every editable row, in display order — the registry search + render share. */
const ROW_DEFS: RowDef[] = [
  {
    key: 'drop-cache',
    section: 'general',
    label: 'Cached data',
    hint: 'Graph snapshots, search results and paper details are cached for a day so repeat work is instant. Drop them when something is stale — a snapshot built under an older shape, or a search cached before a prompt changed — rather than waiting out the TTL.',
    control: () => <DropCacheButton />,
  },
  {
    key: 'default-provider',
    section: 'general',
    label: 'Default data source',
    hint: 'Which academic database builds a graph when none is chosen; the header dropdown overrides it per graph.',
    control: (draft, edit) => (
      <select
        value={draft.providers.default_provider}
        onChange={(event) =>
          edit((next) => {
            next.providers.default_provider = event.target.value as 's2' | 'openalex'
          })
        }
      >
        <option value="s2">Semantic Scholar</option>
        <option value="openalex">OpenAlex</option>
      </select>
    ),
  },
  {
    key: 'default-theme',
    section: 'general',
    label: 'Colour theme',
    hint: 'What a browser with no saved preference opens in. The header toggle overrides it and remembers the choice locally, so this is the default, not a lock.',
    control: (draft, edit) => (
      <select
        value={draft.ui.default_theme}
        onChange={(event) =>
          edit((next) => {
            next.ui.default_theme = event.target.value as 'dark' | 'light'
          })
        }
      >
        <option value="dark">Dark</option>
        <option value="light">Light</option>
      </select>
    ),
  },
  {
    key: 'cache-ttl',
    section: 'general',
    label: 'Graph cache lifetime',
    hint: 'Seconds a built graph snapshot is reused before rebuilding. Citation data changes slowly — a day keeps exploration instant.',
    control: (draft, edit) => (
      <NumberInput
        value={draft.graph.cache_ttl}
        min={0}
        onChange={(value) =>
          edit((next) => {
            next.graph.cache_ttl = value === '' ? 0 : value
          })
        }
      />
    ),
  },
  {
    key: 'adaptive',
    section: 'graph',
    group: 'Sizing',
    label: 'Size graphs automatically',
    hint: 'On, the app picks how many landmark citers to ship and where the Latest bands start, per seed. Off, it ships everything it can and you size the bands yourself — and the filter chips gain count sliders to trim what you see. Kept in this browser, not the config file.',
    control: () => <AdaptiveToggle />,
  },
  {
    key: 'cluster-start',
    section: 'graph',
    group: 'Latest bands',
    label: 'Cluster start year',
    hint: 'First year the Latest bands cover. Blank falls back to the band count below. Only used while automatic sizing is off.',
    control: () => (
      <BandNumber field="clusterStart" min={1800} max={CURRENT_YEAR} placeholder="auto" />
    ),
  },
  {
    key: 'number-of-bands',
    section: 'graph',
    group: 'Latest bands',
    label: 'Number of bands',
    hint: 'How many one-year bands to cover below the landmark cutoff, when no cluster start year is set.',
    control: () => <BandNumber field="numberOfBands" min={1} max={MAX_BANDS} />,
  },
  {
    key: 'nodes-per-band',
    section: 'graph',
    group: 'Latest bands',
    label: 'Papers per band',
    hint: 'Top-N most-cited papers each one-year band keeps. Capped at 200 — a single provider query can return no more.',
    control: () => <BandNumber field="nodesPerBand" min={1} max={MAX_PER_BAND} />,
  },
  {
    key: 's2-key',
    section: 'providers',
    group: 'Semantic Scholar',
    label: 'API key',
    hint: 'Optional — keyless works, just rate-limited harder.',
    control: (draft, edit) => (
      <input
        type="text"
        className="settings-wide"
        value={draft.providers.s2.api_key}
        onChange={(event) =>
          edit((next) => {
            next.providers.s2.api_key = event.target.value
          })
        }
      />
    ),
  },
  {
    key: 's2-interval',
    section: 'providers',
    group: 'Semantic Scholar',
    label: 'Request interval',
    hint: 'Seconds between S2 requests (even keyed callers get ~1 req/s).',
    control: (draft, edit) => (
      <NumberInput
        value={draft.providers.s2.min_interval}
        min={0}
        step={0.1}
        onChange={(value) =>
          edit((next) => {
            next.providers.s2.min_interval = value === '' ? 0 : value
          })
        }
      />
    ),
  },
  {
    key: 'corpus-path',
    section: 'providers',
    group: 'Semantic Scholar',
    label: 'Citations corpus',
    hint: 'Root directory of the offline S2 citations corpus (shards, Parquet, and the CURRENT pointer). Empty = corpus off — the live S2 citation endpoint serves instead.',
    control: (draft, edit) => (
      <input
        type="text"
        className="settings-wide"
        placeholder="(not configured)"
        value={draft.storage.s2_corpus ?? ''}
        onChange={(event) =>
          edit((next) => {
            next.storage.s2_corpus = event.target.value.trim() || null
          })
        }
      />
    ),
  },
  {
    key: 'openalex-key',
    section: 'providers',
    group: 'OpenAlex',
    label: 'API key',
    hint: 'Optional — grants $1/day of metered usage vs $0.10 keyless.',
    control: (draft, edit) => (
      <input
        type="text"
        className="settings-wide"
        value={draft.providers.openalex.api_key}
        onChange={(event) =>
          edit((next) => {
            next.providers.openalex.api_key = event.target.value
          })
        }
      />
    ),
  },
  {
    key: 'openalex-mailto',
    section: 'providers',
    group: 'OpenAlex',
    label: 'Polite-pool email',
    hint: "Joins OpenAlex's faster polite pool, even keyless.",
    control: (draft, edit) => (
      <input
        type="text"
        className="settings-wide"
        value={draft.providers.openalex.mailto}
        onChange={(event) =>
          edit((next) => {
            next.providers.openalex.mailto = event.target.value
          })
        }
      />
    ),
  },
  {
    key: 'anthropic-key',
    section: 'agents',
    tab: 'providers',
    group: 'Anthropic',
    label: 'API key',
    hint: 'From console.anthropic.com. Used by every agent on an anthropic:* model, and billed per lecture and per question.',
    control: (draft, edit) => (
      <VendorField draft={draft} edit={edit} vendor="anthropic" field="api_key" />
    ),
  },
  {
    key: 'openai-key',
    section: 'agents',
    tab: 'providers',
    group: 'OpenAI',
    label: 'API key',
    hint: 'From platform.openai.com/api-keys.',
    control: (draft, edit) => (
      <VendorField draft={draft} edit={edit} vendor="openai" field="api_key" />
    ),
  },
  {
    key: 'openai-base-url',
    section: 'agents',
    tab: 'providers',
    group: 'OpenAI',
    label: 'Compatible server URL',
    hint: 'Blank = OpenAI itself. Set it to drive any OpenAI-compatible server — Groq, OpenRouter, Together, LM Studio — several of which have free tiers.',
    control: (draft, edit) => (
      <VendorField draft={draft} edit={edit} vendor="openai" field="base_url" />
    ),
  },
  {
    key: 'google-key',
    section: 'agents',
    tab: 'providers',
    group: 'Google',
    label: 'API key',
    hint: 'From aistudio.google.com/apikey. The free tier is quota-limited but costs nothing, making this one of the two ways to run the teacher for free.',
    control: (draft, edit) => (
      <VendorField draft={draft} edit={edit} vendor="google" field="api_key" />
    ),
  },
  {
    key: 'ollama-base-url',
    section: 'agents',
    tab: 'providers',
    group: 'Ollama',
    label: 'Server URL',
    hint: 'Normally http://localhost:11434/v1 — keep the /v1. No key, no signup, and nothing leaves this machine. Local models cannot search the web, so the web scout goes quiet rather than inventing sources.',
    control: (draft, edit) => (
      <VendorField draft={draft} edit={edit} vendor="ollama" field="base_url" />
    ),
  },
  {
    key: 'summarizer-model',
    section: 'agents',
    tab: 'agents',
    group: 'Summarizer',
    label: 'Model',
    hint: "Writes the detail panel's on-demand paper TL;DR (cached per paper forever).",
    control: (draft, edit, models) => (
      <ModelInput draft={draft} edit={edit} agentId="summarizer" models={models} />
    ),
  },
  {
    key: 'lecturer-model',
    section: 'agents',
    tab: 'agents',
    group: 'Lecturer',
    label: 'Model',
    hint: 'PydanticAI "<vendor>:<model>" shorthand, e.g. anthropic:claude-sonnet-4-6.',
    control: (draft, edit, models) => (
      <ModelInput draft={draft} edit={edit} agentId="lecturer" models={models} />
    ),
  },
  {
    key: 'lecturer-frontier-window',
    section: 'agents',
    tab: 'agents',
    group: 'Lecturer',
    label: 'Frontier window (months)',
    hint: 'How far back "The current frontier" lecture reaches. Empty = the code default.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="lecturer"
        extrasKey="frontier_window_months"
        fallback={60}
      />
    ),
  },
  {
    key: 'lecturer-min-beats',
    section: 'agents',
    tab: 'agents',
    group: 'Lecturer',
    label: 'Minimum beats',
    hint: 'The shortest lecture, in beats. Empty = the code default.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="lecturer"
        extrasKey="min_beats"
        fallback={7}
      />
    ),
  },
  {
    key: 'lecturer-max-beats',
    section: 'agents',
    tab: 'agents',
    group: 'Lecturer',
    label: 'Maximum beats',
    hint: 'The longest lecture, in beats — raising this materially lengthens (and slows) every lecture.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="lecturer"
        extrasKey="max_beats"
        fallback={12}
      />
    ),
  },
  {
    key: 'researcher-model',
    section: 'agents',
    tab: 'agents',
    group: 'Researcher',
    label: 'Model',
    hint: 'PydanticAI "<vendor>:<model>" shorthand.',
    control: (draft, edit, models) => (
      <ModelInput draft={draft} edit={edit} agentId="researcher" models={models} />
    ),
  },
  {
    key: 'researcher-max-steps',
    section: 'agents',
    tab: 'agents',
    group: 'Researcher',
    label: 'Step budget',
    hint: 'Total tool calls per question — the hard stop on a research run. Empty = the code default.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="researcher"
        extrasKey="max_steps"
        fallback={12}
      />
    ),
  },
  {
    key: 'researcher-full-reads',
    section: 'agents',
    tab: 'agents',
    group: 'Researcher',
    label: 'Full-text reads',
    hint: 'Whole-paper reads per question (the priciest tokens).',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="researcher"
        extrasKey="full_reads"
        fallback={4}
        min={0}
      />
    ),
  },
  {
    key: 'researcher-hops',
    section: 'agents',
    tab: 'agents',
    group: 'Researcher',
    label: 'Graph hops',
    hint: 'expand_node calls per question — bounds how far the graph grows per answer.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="researcher"
        extrasKey="hops"
        fallback={5}
        min={0}
      />
    ),
  },
  {
    key: 'researcher-searches',
    section: 'agents',
    tab: 'agents',
    group: 'Researcher',
    label: 'Topic searches',
    hint: 'find_papers calls per question — bounds off-graph reach.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="researcher"
        extrasKey="searches"
        fallback={3}
        min={0}
      />
    ),
  },
  {
    key: 'researcher-figures',
    section: 'agents',
    tab: 'agents',
    group: 'Researcher',
    label: 'Inline figures',
    hint: 'show_source_figure calls per answer.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="researcher"
        extrasKey="figures"
        fallback={3}
        min={0}
      />
    ),
  },
  {
    key: 'paper-scout-model',
    section: 'agents',
    tab: 'agents',
    group: 'Paper scout',
    label: 'Model',
    hint: "Finds papers by free-text search, on the researcher's behalf and from the search bar. A small fast model earns its keep here.",
    control: (draft, edit, models) => (
      <ModelInput draft={draft} edit={edit} agentId="paper_scout" models={models} />
    ),
  },
  {
    key: 'paper-scout-searches',
    section: 'agents',
    tab: 'agents',
    group: 'Paper scout',
    label: 'Searches per run',
    hint: 'Queries one scouting run may issue before it must report. Empty = the code default.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="paper_scout"
        extrasKey="searches"
        fallback={4}
      />
    ),
  },
  {
    key: 'paper-scout-search-limit',
    section: 'agents',
    tab: 'agents',
    group: 'Paper scout',
    label: 'Hits per query',
    hint: 'How many results each query fetches. Empty = the code default.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="paper_scout"
        extrasKey="search_limit"
        fallback={8}
      />
    ),
  },
  {
    key: 'web-scout-model',
    section: 'agents',
    tab: 'agents',
    group: 'Web scout',
    label: 'Model',
    hint: 'Searches the open web. The search runs provider-side, so this is the one agent a local Ollama model cannot do — point it at a cloud vendor to keep web grounding.',
    control: (draft, edit, models) => (
      <ModelInput draft={draft} edit={edit} agentId="web_scout" models={models} />
    ),
  },
  {
    key: 'web-scout-max-uses',
    section: 'agents',
    tab: 'agents',
    group: 'Web scout',
    label: 'Searches per run',
    hint: 'Web searches one run may make, enforced provider-side. Empty = the code default.',
    control: (draft, edit) => (
      <ExtrasNumber
        draft={draft}
        edit={edit}
        agentId="web_scout"
        extrasKey="max_uses"
        fallback={4}
      />
    ),
  },
]

/** The config-file row's search text — it lives in General and renders
 *  custom (a path field + native picker), not through ROW_DEFS. */
const FILE_ROW_TEXT = 'Config file location choose file explorer finder json'

/**
 * Render the settings modal.
 *
 * @returns The modal, or null while closed.
 */
export default function SettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [payload, setPayload] = useState<SettingsPayload | null>(null)
  const [draft, setDraft] = useState<AtlasConfig | null>(null)
  const [section, setSection] = useState<SectionId>('general')
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [errorFields, setErrorFields] = useState<SettingsFieldError[]>([])
  const [saving, setSaving] = useState(false)
  const [locationDraft, setLocationDraft] = useState('')
  const [models, setModels] = useState<AgentModels>({ models: {}, vendors: [], known: [] })
  // '' is the section's own landing page. A section with sub-pages opens
  // there rather than dropping you into an arbitrary first child.
  const [page, setPage] = useState<AgentTab | ''>('')
  // Which group headings the reader has folded away. Tracked as the negative
  // so everything is open on arrival: folding is for tidying a section you are
  // done with, not a wall you have to dismantle before you can read anything.
  const [foldedGroups, setFoldedGroups] = useState<ReadonlySet<string>>(new Set())

  const refresh = useCallback(async () => {
    try {
      const fresh = await getSettings()
      setPayload(fresh)
      setDraft(structuredClone(fresh.config))
      setLocationDraft(fresh.path)
      setError(null)
      setErrorFields([])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    if (open) {
      void refresh()
      void getAgentModels().then(setModels)
    }
  }, [open, refresh])

  const query = filter.trim().toLowerCase()

  /**
   * Whether any of the texts matches the search query (empty query = all).
   *
   * @param texts Candidate strings (labels, hints, group names).
   * @returns True when visible under the current filter.
   */
  const matches = useCallback(
    (...texts: (string | undefined)[]) =>
      query === '' || texts.some((text) => text?.toLowerCase().includes(query)),
    [query],
  )

  /**
   * Whether a section has at least one visible row under the filter.
   *
   * @param id The section to check.
   * @returns True when the section (or any of its rows) matches the query.
   */
  const sectionHasHits = (id: SectionId): boolean => {
    const label = SECTIONS.find((entry) => entry.id === id)?.label
    if (matches(label) && query !== '') return true
    if (id === 'general' && matches(FILE_ROW_TEXT)) return true
    return ROW_DEFS.some((row) => row.section === id && matches(row.label, row.hint, row.group))
  }

  const visibleSections = SECTIONS.filter((entry) => query === '' || sectionHasHits(entry.id))

  // When the filter hides the active section, jump to the first one with hits.
  useEffect(() => {
    if (query !== '' && !sectionHasHits(section) && visibleSections.length > 0) {
      setSection(visibleSections[0].id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recompute on filter change only
  }, [query])

  if (!open) return null

  const dirty =
    payload !== null && draft !== null && JSON.stringify(draft) !== JSON.stringify(payload.config)

  const edit: Edit = (mutate) => {
    setDraft((prev) => {
      if (!prev) return prev
      const next = structuredClone(prev)
      mutate(next)
      return next
    })
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const fresh = await putSettings(draft)
      setPayload(fresh)
      setDraft(structuredClone(fresh.config))
      setError(null)
      setErrorFields([])
    } catch (err) {
      setError(err instanceof SettingsError ? err.message : 'Save failed — is the server up?')
      setErrorFields(err instanceof SettingsError ? err.fields : [])
    } finally {
      setSaving(false)
    }
  }

  const switchLocation = async (path: string) => {
    setSaving(true)
    try {
      const fresh = await putSettingsLocation(path)
      setPayload(fresh)
      setDraft(structuredClone(fresh.config))
      setLocationDraft(fresh.path)
      setError(null)
      setErrorFields([])
    } catch (err) {
      setError(err instanceof SettingsError ? err.message : 'Switch failed — is the server up?')
      setErrorFields(err instanceof SettingsError ? err.fields : [])
    } finally {
      setSaving(false)
    }
  }

  const chooseConfigFile = async () => {
    try {
      const chosen = await pickSettingsFile()
      if (chosen) await switchLocation(chosen)
    } catch {
      setError('Could not open the file chooser — is the server up?')
      setErrorFields([])
    }
  }

  // A search reaches across both sub-tabs — hiding a matching row behind an
  // unselected tab is the thing search exists to avoid.
  // A search reaches across sub-pages and ignores folding — hiding a matching
  // row behind either is the thing search exists to avoid.
  const searching = query !== ''

  const activeSection = SECTIONS.find((entry) => entry.id === section)
  const pages = activeSection && 'pages' in activeSection ? activeSection.pages : undefined
  const pageLabel = searching ? undefined : pages?.find((sub) => sub.id === page)?.label
  // The landing page has no rows of its own — its whole job is to say what the
  // section is before you pick a side of it.
  const onLanding = pages !== undefined && page === '' && !searching

  /** The active section's rows under the current filter, grouped for headings. */
  const rows = ROW_DEFS.filter(
    (row) =>
      row.section === section &&
      (searching || row.tab === undefined || row.tab === page) &&
      matches(row.label, row.hint, row.group),
  )

  /** The rows above, cut into consecutive same-heading runs. */
  const groups: { name?: string; rows: RowDef[] }[] = []
  for (const row of rows) {
    const last = groups.at(-1)
    if (last && last.name === row.group) last.rows.push(row)
    else groups.push({ name: row.group, rows: [row] })
  }

  const toggleGroup = (name: string) =>
    setFoldedGroups((previous) => {
      const next = new Set(previous)
      if (!next.delete(name)) next.add(name)
      return next
    })

  return (
    <div className="settings-backdrop" onClick={onClose}>
      <div
        className="settings-modal"
        role="dialog"
        aria-label="Settings"
        onClick={(event) => event.stopPropagation()}
      >
        <aside className="settings-sidebar">
          <input
            className="settings-search"
            placeholder="Search settings"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <div className="settings-nav-group">Settings</div>
          {visibleSections.map((entry) => {
            const pages = 'pages' in entry ? entry.pages : undefined
            const here = section === entry.id
            return (
              <div key={entry.id}>
                <button
                  className={`settings-nav-item ${here && (!pages || page === '') ? 'active' : ''}`}
                  onClick={() => {
                    setSection(entry.id)
                    setPage('')
                  }}
                >
                  <span className="settings-nav-icon">{entry.icon}</span>
                  {entry.label}
                </button>
                {/* Sub-pages show only for the section you are in — the nav is
                    a place to navigate, not an outline of everything. */}
                {pages &&
                  here &&
                  pages.map((sub) => (
                    <button
                      key={sub.id}
                      className={`settings-nav-item sub ${page === sub.id ? 'active' : ''}`}
                      onClick={() => setPage(sub.id)}
                    >
                      {sub.label}
                    </button>
                  ))}
              </div>
            )
          })}
        </aside>

        <div className="settings-content">
          <button className="settings-close" onClick={onClose} aria-label="Close settings">
            ✕
          </button>
          <div className="settings-scroll">
            {!draft && !error && <div className="settings-loading">Loading…</div>}

            {draft && (
              <>
                <h2>
                  {SECTIONS.find((entry) => entry.id === section)?.label}
                  {pageLabel && (
                    <>
                      <span className="settings-crumb-sep">›</span>
                      {pageLabel}
                    </>
                  )}
                </h2>

                {activeSection?.blurb && !searching && !pageLabel && (
                  <p className="settings-blurb">{activeSection.blurb}</p>
                )}
                {onLanding &&
                  pages.map((sub) => (
                    <button
                      key={sub.id}
                      type="button"
                      className="settings-landing-link"
                      onClick={() => setPage(sub.id)}
                    >
                      {sub.label}
                    </button>
                  ))}

                {groups.map((group) => {
                  // A search opens everything it matched: the reader asked for
                  // exactly these rows and should not have to unfold them.
                  const open =
                    group.name === undefined || searching || !foldedGroups.has(group.name)
                  return (
                    <div key={group.name ?? group.rows[0].key}>
                      {group.name !== undefined && (
                        <button
                          type="button"
                          className="settings-group-head"
                          aria-expanded={open}
                          onClick={() => toggleGroup(group.name as string)}
                        >
                          {group.name}
                          {GROUP_BADGES[group.name] && (
                            <span
                              className={`settings-group-badge${
                                GROUP_BADGES[group.name].free ? ' free' : ''
                              }`}
                            >
                              {GROUP_BADGES[group.name].text}
                            </span>
                          )}
                          <span className="settings-group-rule" />
                          <span className="settings-group-caret">{open ? '▾' : '▸'}</span>
                        </button>
                      )}
                      {open &&
                        group.rows.map((row) => (
                          <div key={row.key} className="settings-row">
                            <div className="settings-row-label">
                              <span>{row.label}</span>
                              {row.hint && <span className="settings-hint">{row.hint}</span>}
                            </div>
                            <div className="settings-row-control">
                              {row.control(draft, edit, models)}
                            </div>
                          </div>
                        ))}
                    </div>
                  )
                })}
                {rows.length === 0 && query !== '' && (
                  <div className="settings-loading">No matching settings here.</div>
                )}
              </>
            )}

            {draft && section === 'general' && matches(FILE_ROW_TEXT) && (
              <>
                <div className="settings-row">
                  <div className="settings-row-label">
                    <span>Location</span>
                    <span className="settings-hint">
                      The config file this app runs on — every setting above reads from and saves to
                      it. Type a path and press Enter, or browse with 📁.
                    </span>
                  </div>
                  <div className="settings-row-control settings-locationbar">
                    <input
                      type="text"
                      className="settings-wide"
                      value={locationDraft}
                      onChange={(event) => setLocationDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && locationDraft !== payload?.path) {
                          void switchLocation(locationDraft)
                        }
                      }}
                    />
                    <button
                      className="settings-filepick"
                      disabled={saving}
                      onClick={() => void chooseConfigFile()}
                    >
                      📁 Change
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="settings-footer">
            {error && (
              <div className="settings-error">
                <strong>{error}</strong>
                {errorFields.length > 0 && (
                  <ul>
                    {errorFields.map((field) => (
                      <li key={field.path}>
                        <code>{field.path}</code> — {field.message}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {dirty && (
              <div className="settings-savebar">
                <span>Unsaved changes</span>
                <button
                  className="settings-discard"
                  disabled={saving}
                  onClick={() => payload && setDraft(structuredClone(payload.config))}
                >
                  Discard
                </button>
                <button className="settings-save" disabled={saving} onClick={() => void save()}>
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
