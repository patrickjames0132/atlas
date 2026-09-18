// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The settings modal: loading the active config into a draft, dirty
 * detection + the Save/Discard bar, a rejected save surfacing the server's
 * field error in the footer, the PyCharm-style search reaching individual
 * rows, agent-extras editing, the native-picker config-file switch, the
 * Library section's landing switch and sub-page fields, a vendor's one-click
 * crew button, and the modal's own tour (auto-run once, then the ?).
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import SettingsModal from '../../src/settings/SettingsModal'
import type { AtlasConfig } from '../../src/api'

/** A minimal but complete-enough config the modal's sections can render. */
function makeConfig(): AtlasConfig {
  return {
    storage: { data_dir: 'data', s2_corpus: null },
    providers: {
      default_provider: 's2',
      s2: {
        api_key: '',
        graph_url: 'https://s2.example/graph',
        recs_url: 'https://s2.example/recs',
        timeout: 30,
        min_interval: 1.1,
      },
      openalex: {
        api_key: '',
        mailto: 'me@example.org',
        base_url: 'https://openalex.example',
        timeout: 30,
        min_interval: 0.1,
      },
    },
    graph: { cache_ttl: 86400 },
    ui: { default_theme: 'dark' },
    sources: {
      semantic_enabled: true,
      embedding: {
        model: 'sentence-transformers/all-MiniLM-L6-v2',
        dim: 384,
        query_prefix: '',
        device: 'auto',
      },
      chunking: { chars: 900, overlap: 150 },
      retrieval: { search_k: 6, hybrid: true, rrf_k: 60, chat_k: 8 },
    },
    llm: {
      providers: {
        anthropic: { api_key: 'sk-test' },
        ollama: { base_url: 'http://localhost:11434/v1' },
      },
      agents: [
        { id: 'summarizer', model: 'anthropic:claude-haiku-4-5', extras: {} },
        // Unique among the agents, so a display-value query lands on it.
        { id: 'lecturer', model: 'anthropic:claude-sonnet-4-6', extras: {} },
        { id: 'researcher', model: 'anthropic:claude-opus-4-8', extras: { max_steps: 20 } },
        // The scouts complete the real crew — the Agents tab renders a card
        // per configured agent, so a short fixture would under-test it.
        { id: 'paper_scout', model: 'anthropic:claude-haiku-4-5', extras: { searches: 4 } },
        { id: 'web_scout', model: 'anthropic:claude-haiku-4-5', extras: { max_uses: 2 } },
      ],
    },
    untouched_section: { keep: 'me' },
  }
}

/** The fetch stub's programmable state for one test. */
const fetchState = {
  config: makeConfig(),
  path: '/repo/config.json',
  failPutWith: null as string | null,
  lastPutBody: null as unknown,
  pickAnswer: null as string | null,
}

beforeEach(() => {
  // The settings tour auto-runs once ever; every test but the tour's own
  // starts with it already seen, or its bubble text lands in the queries.
  localStorage.setItem('atlas.tour.settings', '1')
  fetchState.config = makeConfig()
  fetchState.path = '/repo/config.json'
  fetchState.failPutWith = null
  fetchState.lastPutBody = null
  fetchState.pickAnswer = null
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (!init?.method && String(url).endsWith('/api/settings/models')) {
      return new Response(
        JSON.stringify({
          models: { anthropic: ['claude-opus-4-8'], ollama: ['qwen3:8b', 'llama3.2:1b'] },
          vendors: ['anthropic', 'ollama'],
          known: ['anthropic', 'openai', 'google', 'ollama'],
          tiers: {
            anthropic: { advanced: 'claude-opus-4-8', light: 'claude-opus-4-8' },
            ollama: { advanced: 'qwen3:8b', light: 'llama3.2:1b' },
          },
        }),
        { status: 200 },
      )
    }
    if (init?.method === 'POST' && String(url).endsWith('/api/settings/pick')) {
      return new Response(JSON.stringify({ path: fetchState.pickAnswer }), { status: 200 })
    }
    if (init?.method === 'PUT' && String(url).endsWith('/api/settings')) {
      fetchState.lastPutBody = JSON.parse(String(init.body))
      if (fetchState.failPutWith) {
        return new Response(JSON.stringify({ error: fetchState.failPutWith }), { status: 400 })
      }
      fetchState.config = (fetchState.lastPutBody as { config: AtlasConfig }).config
    }
    if (init?.method === 'PUT' && String(url).endsWith('/api/settings/location')) {
      fetchState.path = (JSON.parse(String(init.body)) as { path: string }).path
    }
    return new Response(JSON.stringify({ path: fetchState.path, config: fetchState.config }), {
      status: 200,
    })
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
})

/** Render the modal open and wait for the config to load. */
async function renderOpen() {
  const onClose = vi.fn()
  render(<SettingsModal open onClose={onClose} />)
  await screen.findByText('Default data source')
  return onClose
}

describe('SettingsModal', () => {
  it('renders nothing while closed', () => {
    render(<SettingsModal open={false} onClose={() => {}} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('loads the active config and shows its values', async () => {
    await renderOpen()
    expect(screen.getByDisplayValue('86400')).toBeTruthy()
  })

  it('editing raises the save bar; discard clears it', async () => {
    await renderOpen()
    fireEvent.change(screen.getByDisplayValue('86400'), { target: { value: '123' } })
    expect(await screen.findByText('Unsaved changes')).toBeTruthy()
    fireEvent.click(screen.getByText('Discard'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    expect(screen.getByDisplayValue('86400')).toBeTruthy()
  })

  it('save PUTs the whole config, unknown sections included', async () => {
    await renderOpen()
    fireEvent.change(screen.getByDisplayValue('86400'), { target: { value: '123' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.graph.cache_ttl).toBe(123)
    expect(body.config.untouched_section).toEqual({ keep: 'me' })
  })

  it('a rejected save shows the server field error and keeps the draft', async () => {
    fetchState.failPutWith = 'cache_ttl: input should be ≥ 0'
    await renderOpen()
    fireEvent.change(screen.getByDisplayValue('86400'), { target: { value: '-1' } })
    fireEvent.click(await screen.findByText('Save'))
    expect(await screen.findByText(/cache_ttl/)).toBeTruthy()
    expect(screen.getByText('Unsaved changes')).toBeTruthy() // still dirty
  })

  it('search reaches individual rows, not just section labels', async () => {
    await renderOpen()
    fireEvent.change(screen.getByPlaceholderText('Search settings'), {
      target: { value: 'beats' },
    })
    // The nav narrows to Agents (the only section with a matching row) and
    // the pane auto-switches to it, showing only the matching rows.
    expect(await screen.findByText('Minimum beats')).toBeTruthy()
    expect(screen.getByText('Maximum beats')).toBeTruthy()
    expect(screen.queryByText('Default data source')).toBeNull()
    expect(screen.queryByText('Citations corpus')).toBeNull()
  })

  it('agent extras edit into llm.agents, and clearing removes the override', async () => {
    await renderOpen()
    openAgentTuning()
    const stepBudget = await screen.findByDisplayValue('20') // researcher max_steps override
    fireEvent.change(stepBudget, { target: { value: '8' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    let body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.llm.agents.find((agent) => agent.id === 'researcher')?.extras).toEqual({
      max_steps: 8,
    })
    // Clearing the field deletes the override (back to the code default).
    fireEvent.change(screen.getByDisplayValue('8'), { target: { value: '' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.llm.agents.find((agent) => agent.id === 'researcher')?.extras).toEqual({})
  })

  it('the 📁 button picks a file natively and switches to it', async () => {
    fetchState.pickAnswer = '/elsewhere/config.json'
    await renderOpen()
    expect(await screen.findByDisplayValue('/repo/config.json')).toBeTruthy()
    fireEvent.click(screen.getByText(/Change/))
    expect(await screen.findByDisplayValue('/elsewhere/config.json')).toBeTruthy()
  })

  it('a typed path applies on Enter', async () => {
    await renderOpen()
    const pathInput = await screen.findByDisplayValue('/repo/config.json')
    fireEvent.change(pathInput, { target: { value: '/typed/config.json' } })
    fireEvent.keyDown(pathInput, { key: 'Enter' })
    expect(await screen.findByDisplayValue('/typed/config.json')).toBeTruthy()
  })

  it('a cancelled pick changes nothing', async () => {
    fetchState.pickAnswer = null
    await renderOpen()
    fireEvent.click(screen.getByText(/Change/))
    expect(await screen.findByDisplayValue('/repo/config.json')).toBeTruthy()
  })

  /** Enter the Agents section and open its "Agent settings" sub-page.
   *
   *  The section opens on Model providers, so anything about an agent's model
   *  or knobs is one nav click away.
   */
  function openAgentTuning() {
    fireEvent.click(screen.getByText('Agents'))
    openSubPage('Agent Settings')
  }

  /** Click a sub-page by name, from the nav rather than the landing page.
   *
   *  Both offer the same label while the landing page is showing, so the
   *  first match — the sidebar, which renders before the content pane — is
   *  the unambiguous one to drive.
   */
  function openSubPage(label: string) {
    const [navItem] = screen.getAllByText(label)
    fireEvent.click(navItem)
  }

  /** Enter the Agents section and open its "Model Providers" sub-page.
   *
   *  The section opens on its own landing page — a description and links —
   *  so vendor credentials are one further click away.
   */
  function openModelProviders() {
    fireEvent.click(screen.getByText('Agents'))
    openSubPage('Model Providers')
  }

  it("the model dropdown lists the agent's own vendor plus its current value", async () => {
    await renderOpen()
    openAgentTuning()
    // The model select is scoped to the vendor chosen beside it, so it offers
    // Anthropic's models only — picking Ollama is the vendor select's job.
    const [lecturerModel] = await screen.findAllByDisplayValue('claude-sonnet-4-6')
    // The config's current model is kept even though the fetched list lacks it
    // — a hand-set or since-retired id must never be silently dropped.
    expect([...lecturerModel.querySelectorAll('option')].map((option) => option.value)).toEqual([
      'claude-sonnet-4-6',
      'claude-opus-4-8',
    ])
  })

  it('every vendor is listed, including ones not set up yet', async () => {
    // The whole point: the free options are exactly the ones a newcomer has
    // not set up, so a list of working vendors would hide them.
    await renderOpen()
    openModelProviders()
    // Each vendor is its own foldable group; the free ones say so in their
    // key-field hints rather than in a heading badge.
    expect(await screen.findByRole('button', { name: /Ollama/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Google/ })).toBeTruthy()
    expect(screen.queryByText('free tier')).toBeNull()
  })

  it('a group heading folds its own rows away', async () => {
    await renderOpen()
    openModelProviders()
    // Open on arrival — folding is for tidying, not for dismantling a wall.
    expect(await screen.findByText('Server URL')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Ollama/ }))
    expect(screen.queryByText('Server URL')).toBeNull()
    // Folding one leaves the others alone.
    expect(screen.getAllByText('API key').length).toBeGreaterThan(0)
  })

  it('switching an agent to another vendor rewrites both halves', async () => {
    await renderOpen()
    openAgentTuning()
    // First Vendor select on the page is the summarizer's — the agent rows are
    // rendered in config order.
    const [summarizerVendor] = await screen.findAllByLabelText('Vendor')
    fireEvent.change(summarizerVendor, { target: { value: 'ollama' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    // The model must move with the vendor — an anthropic model name under an
    // ollama prefix would be a config that cannot run.
    expect(body.config.llm.agents.find((agent) => agent.id === 'summarizer')?.model).toBe(
      'ollama:qwen3:8b',
    )
  })

  it('picking a model from the dropdown edits llm.agents', async () => {
    await renderOpen()
    openAgentTuning()
    const [lecturerModel] = await screen.findAllByDisplayValue('claude-sonnet-4-6')
    fireEvent.change(lecturerModel, { target: { value: 'claude-opus-4-8' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.llm.agents.find((agent) => agent.id === 'lecturer')?.model).toBe(
      'anthropic:claude-opus-4-8',
    )
  })

  it('number fields clamp to the floor their config field enforces', async () => {
    await renderOpen()
    // Graph cache lifetime is a NonNegativeInt: a typed -5 lands as 0, and
    // the input advertises the same floor to the browser.
    const cacheTtl = screen.getByDisplayValue('86400')
    expect(cacheTtl.getAttribute('min')).toBe('0')
    fireEvent.change(cacheTtl, { target: { value: '-5' } })
    expect(await screen.findByDisplayValue('0')).toBeTruthy()
  })

  it('a positive-only agent knob cannot be driven below 1', async () => {
    await renderOpen()
    openAgentTuning()
    const stepBudget = await screen.findByDisplayValue('20') // researcher max_steps
    expect(stepBudget.getAttribute('min')).toBe('1')
    fireEvent.change(stepBudget, { target: { value: '-3' } })
    expect(await screen.findByDisplayValue('1')).toBeTruthy()
  })

  it('a section with sub-pages opens on its own landing page', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Agents'))
    // Neither sub-page's rows yet — the landing page says what the section is
    // before dropping the reader into one side of it.
    expect(screen.queryByDisplayValue('sk-test')).toBeNull()
    expect(screen.queryByLabelText('Vendor')).toBeNull()
    expect(await screen.findByText(/The AI teacher/)).toBeTruthy()
    // And both ways in are offered.
    expect(screen.getAllByText('Model Providers').length).toBe(2)
  })

  it('lists every configured agent, not just the ones with knobs', async () => {
    await renderOpen()
    openAgentTuning()
    for (const agent of ['Summarizer', 'Lecturer', 'Researcher', 'Paper scout', 'Web scout']) {
      expect(await screen.findByText(agent)).toBeTruthy()
    }
  })

  it('folding an agent hides its model and knobs together', async () => {
    await renderOpen()
    openAgentTuning()
    // Every configured agent shows a vendor select without any unfolding.
    expect((await screen.findAllByLabelText('Vendor')).length).toBe(5)
    expect(screen.getByDisplayValue('20')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Researcher/ }))
    expect(screen.queryByDisplayValue('20')).toBeNull()
    // The other agents are untouched — folding is per group.
    expect(screen.getAllByLabelText('Vendor').length).toBe(4)
  })

  it('the Anthropic key edits llm.providers', async () => {
    await renderOpen()
    openModelProviders()
    const keyInput = await screen.findByDisplayValue('sk-test')
    fireEvent.change(keyInput, { target: { value: 'sk-new' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.llm.providers.anthropic?.api_key).toBe('sk-new')
  })

  it('the dead frontier-window knob is gone from the lecturer', async () => {
    // LecturerExtras dropped `frontier_window_months` in v7.17.0 and forbids
    // unknown keys, so the row it left behind could only produce a rejected save.
    await renderOpen()
    openAgentTuning()
    await screen.findAllByLabelText('Vendor')
    expect(screen.queryByText(/Frontier window/)).toBeNull()
  })

  it("a vendor's button puts the crew on its picks and shows the result", async () => {
    await renderOpen()
    openModelProviders()
    // A button under every vendor; only the two the backend listed are live.
    const buttons = await screen.findAllByText('Apply Default Models')
    expect(buttons.length).toBe(4)
    expect(buttons.filter((button) => !(button as HTMLButtonElement).disabled).length).toBe(2)
    // Clearing a key in the draft greys its button out at once — the listing
    // was fetched on open and would otherwise vouch for a vendor that is gone.
    const keyField = screen.getByDisplayValue('sk-test')
    fireEvent.change(keyField, { target: { value: '' } })
    expect((screen.getAllByText('Apply Default Models')[0] as HTMLButtonElement).disabled).toBe(
      true,
    )
    fireEvent.change(keyField, { target: { value: 'sk-test' } })
    // The picks are spelled out in the tooltip before pressing.
    expect(buttons[3].getAttribute('title')).toMatch(
      /qwen3:8b for the lecturer and researcher; llama3.2:1b for/,
    )
    fireEvent.click(buttons[3]) // Ollama's — the groups follow VENDOR_LABELS order
    // The modal moves to Agent Settings — the per-agent Vendor selects only
    // render there — where every agent now shows the new vendor.
    const vendors = (await screen.findAllByLabelText('Vendor')) as HTMLSelectElement[]
    expect(vendors.length).toBe(5)
    expect(new Set(vendors.map((select) => select.value))).toEqual(new Set(['ollama']))
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    const model = (id: string) => body.config.llm.agents.find((agent) => agent.id === id)?.model
    expect(model('lecturer')).toBe('ollama:qwen3:8b')
    expect(model('researcher')).toBe('ollama:qwen3:8b')
    expect(model('summarizer')).toBe('ollama:llama3.2:1b')
    expect(model('paper_scout')).toBe('ollama:llama3.2:1b')
    expect(model('web_scout')).toBe('ollama:llama3.2:1b')
    // The knobs are untouched — this changes who runs, not how.
    expect(body.config.llm.agents.find((agent) => agent.id === 'researcher')?.extras).toEqual({
      max_steps: 20,
    })
  })

  it('Library opens on its four ways in; the master switch is on General', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Library'))
    expect(await screen.findByText(/Your library/)).toBeTruthy()
    expect(screen.getAllByText('Retrieval').length).toBe(2) // nav + landing link
    expect(screen.queryByText('Passages per search')).toBeNull()
    expect(screen.queryByLabelText('Semantic search over your library')).toBeNull()
    // General (the sub-page, not the top-level section) holds the switch —
    // second match, since the section's own nav item renders first.
    fireEvent.click(screen.getAllByText('General')[1])
    expect(await screen.findByLabelText('Semantic search over your library')).toBeTruthy()
    openSubPage('Retrieval')
    expect(await screen.findByText('Passages per search')).toBeTruthy()
    expect(screen.queryByLabelText('Semantic search over your library')).toBeNull()
  })

  it('the master switch and a retrieval count edit config.sources', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Library'))
    fireEvent.click(screen.getAllByText('General')[1])
    fireEvent.click(await screen.findByLabelText('Semantic search over your library'))
    openSubPage('Retrieval')
    fireEvent.change(await screen.findByDisplayValue('6'), { target: { value: '9' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.sources.semantic_enabled).toBe(false)
    expect(body.config.sources.retrieval.search_k).toBe(9)
    // Everything else in the block rode along untouched.
    expect(body.config.sources.chunking).toEqual({ chars: 900, overlap: 150 })
  })

  it('a library count refuses to be cleared — the file always carries a value', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Library'))
    openSubPage('Chunking')
    fireEvent.change(await screen.findByDisplayValue('150'), { target: { value: '' } })
    expect(screen.getByDisplayValue('150')).toBeTruthy()
    expect(screen.queryByText('Unsaved changes')).toBeNull()
  })

  it('the ? runs the settings tour, which walks the nav for its stops', async () => {
    await renderOpen()
    expect(screen.queryByRole('dialog', { name: 'Guided tour' })).toBeNull()
    fireEvent.click(screen.getByLabelText('Tour the settings'))
    const tour = await screen.findByRole('dialog', { name: 'Guided tour' })
    expect(tour.textContent).toContain('Find any setting')
    // Two Nexts in: the config-file stop, which stages General (already
    // there); a third stages Graph and the pane follows the tour.
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Next'))
    await waitFor(() => expect(tour.textContent).toContain('Graph size'))
    expect(screen.getByLabelText('Size graphs automatically')).toBeTruthy()
  })

  it('the settings tour auto-runs once on first open, then stays behind the ?', async () => {
    localStorage.removeItem('atlas.tour.settings')
    await renderOpen()
    expect(await screen.findByRole('dialog', { name: 'Guided tour' })).toBeTruthy()
    fireEvent.click(screen.getByText('Skip tips'))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Guided tour' })).toBeNull())
    expect(localStorage.getItem('atlas.tour.settings')).toBe('1')
  })
})
