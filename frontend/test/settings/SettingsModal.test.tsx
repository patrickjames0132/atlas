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
        { id: 'query_analyst', model: 'anthropic:claude-haiku-4-5', extras: {} },
        { id: 'summarizer', model: 'anthropic:claude-haiku-4-5', extras: {} },
        { id: 'librarian', model: 'anthropic:claude-haiku-4-5', extras: {} },
        // Unique among the agents, so a display-value query lands on it.
        { id: 'lecturer', model: 'anthropic:claude-sonnet-4-6', extras: {} },
        { id: 'researcher', model: 'anthropic:claude-opus-4-8', extras: { max_steps: 20 } },
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
      return new Response(JSON.stringify({ models: ['claude-opus-4-8'] }), { status: 200 })
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
    fireEvent.click(screen.getByText('Agents'))
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

  it('the model dropdown lists fetched models plus the current value', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Agents'))
    const [lecturerModel] = await screen.findAllByDisplayValue('anthropic:claude-sonnet-4-6')
    // The config's current model is kept even though the fetched list lacks it
    // — a hand-set or since-retired id must never be silently dropped.
    expect([...lecturerModel.querySelectorAll('option')].map((option) => option.value)).toEqual([
      'anthropic:claude-sonnet-4-6',
      'anthropic:claude-opus-4-8',
    ])
  })

  it('picking a model from the dropdown edits llm.agents', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Agents'))
    const [lecturerModel] = await screen.findAllByDisplayValue('anthropic:claude-sonnet-4-6')
    fireEvent.change(lecturerModel, { target: { value: 'anthropic:claude-opus-4-8' } })
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
    fireEvent.click(screen.getByText('Agents'))
    const stepBudget = await screen.findByDisplayValue('20') // researcher max_steps
    expect(stepBudget.getAttribute('min')).toBe('1')
    fireEvent.change(stepBudget, { target: { value: '-3' } })
    expect(await screen.findByDisplayValue('1')).toBeTruthy()
  })

  it('lists every configured agent, not just the ones with knobs', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Agents'))
    for (const agent of ['Query analyst', 'Summarizer', 'Librarian', 'Lecturer', 'Researcher']) {
      expect(await screen.findByText(agent)).toBeTruthy()
    }
  })

  it('the Anthropic key edits llm.providers', async () => {
    await renderOpen()
    fireEvent.click(screen.getByText('Agents'))
    const keyInput = await screen.findByDisplayValue('sk-test')
    fireEvent.change(keyInput, { target: { value: 'sk-new' } })
    fireEvent.click(await screen.findByText('Save'))
    await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
    const body = fetchState.lastPutBody as { config: AtlasConfig }
    expect(body.config.llm.providers.anthropic?.api_key).toBe('sk-new')
  })
})
