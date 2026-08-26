// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The settings modal: loading the active config into a draft, dirty
 * detection + the Save/Discard bar, a rejected save surfacing the server's
 * field error in the footer, the PyCharm-style search reaching individual
 * rows, agent-extras editing, and the native-picker config-file switch.
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
    llm: {
      providers: { anthropic: { api_key: 'sk-test' } },
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
  fetchState.config = makeConfig()
  fetchState.path = '/repo/config.json'
  fetchState.failPutWith = null
  fetchState.lastPutBody = null
  fetchState.pickAnswer = null
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (!init?.method && String(url).endsWith('/api/settings/models')) {
      return new Response(
        JSON.stringify({
          models: { anthropic: ['claude-opus-4-8'], ollama: ['qwen3:8b'] },
          vendors: ['anthropic', 'ollama'],
          known: ['anthropic', 'openai', 'google', 'ollama'],
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
    // Each vendor is its own foldable group, and the heading badge carries the
    // cost — the deciding fact for the reader this list exists for.
    expect(await screen.findByRole('button', { name: /Ollama/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Google/ })).toBeTruthy()
    // The cost rides the heading as a badge.
    expect(screen.getByText('free, local')).toBeTruthy()
    expect(screen.getByText('free tier')).toBeTruthy()
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
})
