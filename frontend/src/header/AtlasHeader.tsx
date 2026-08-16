/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The top bar container: brand, the current seed's title, the data-source
 * dropdown, and the drawer toggles (Library / Assistant / Sessions).
 *
 * The seed-search form used to live here too. It moved into the chat bar in
 * v7.6.0 — one text input for the whole app, with a toggle choosing whether
 * what you type is looked up or asked. Searching and asking were always two
 * ways of saying "find me papers about this", and having them in two boxes
 * meant picking the box before you knew which one you wanted.
 *
 * Purely presentational — drawer visibility lives in Atlas and passes
 * through as props.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { Provider } from '../api'
import type { Theme } from '../ui/theme'
import { PROVIDER_LABEL } from '../api'
import './header.css'

/** Props for {@link AtlasHeader}. */
export interface AtlasHeaderProps {
  /** The academic-data backend graphs are built from (the dropdown value). */
  provider: Provider
  /** Switch the backend — re-seeds the current graph under the new provider. */
  onProviderChange: (provider: Provider) => void
  /** A graph is loading (greys out the provider dropdown mid-build). */
  loadingGraph: boolean
  /** The loaded graph's seed title, shown beside the brand (null = none). */
  seedTitle: string | null
  /** Clear the workspace — back to the page-load default state. */
  onHome: () => void
  onOpenSources: () => void
  /** There's something to assist with — a graph is open or a library exists;
   *  when false the Assistant toggle is hidden. */
  assistantAvailable: boolean
  /** The assistant panel is open (drives the toggle's active state). */
  assistantOpen: boolean
  onToggleAssistant: () => void
  onOpenSessions: () => void
  /** Open the settings modal (config-file editor). */
  onOpenSettings: () => void
  /** The active theme — decides which icon the toggle shows. */
  theme: Theme
  /** Flip between light and dark. */
  onToggleTheme: () => void
  /** Start (or restart) the guided tour for the current phase — the search
   *  surface before a graph is up, the graph tools once one is. */
  onStartTour: () => void
}

/**
 * Render the app's top bar.
 *
 * @returns The header (brand, seed title, provider, drawer toggles).
 */
export default function AtlasHeader({
  loadingGraph,
  provider,
  onProviderChange,
  seedTitle,
  onHome,
  onOpenSources,
  assistantAvailable,
  assistantOpen,
  onToggleAssistant,
  onOpenSessions,
  onOpenSettings,
  theme,
  onToggleTheme,
  onStartTour,
}: AtlasHeaderProps) {
  return (
    <header className="atlas-top">
      <button
        type="button"
        className="brand"
        onClick={onHome}
        title="Clear the graph and start fresh"
      >
        <span>Atlas</span>
      </button>
      {seedTitle && (
        <div className="seed-info" title={seedTitle}>
          {seedTitle}
        </div>
      )}
      <label
        className="provider-select top-right-start"
        data-tour="provider"
        title="Which academic database the graph is built from — references, citations, and the seed all come from this one source"
      >
        <span>Data source</span>
        <select
          value={provider}
          onChange={(event) => onProviderChange(event.target.value as Provider)}
          disabled={loadingGraph}
        >
          {(Object.keys(PROVIDER_LABEL) as Provider[]).map((key) => (
            <option key={key} value={key}>
              {PROVIDER_LABEL[key]}
            </option>
          ))}
        </select>
      </label>
      <button
        className="sources-toggle"
        data-tour="library-btn"
        onClick={onOpenSources}
        title="Your library — books, PDFs, and pages the teacher can search"
      >
        📚 Library
      </button>
      {assistantAvailable && (
        <button
          className={`sources-toggle ${assistantOpen ? 'on' : ''}`}
          data-tour="assistant-btn"
          onClick={onToggleAssistant}
          title="The AI assistant — a lecture and Q&A over the graph, or a chat straight over your uploaded library"
        >
          🎓 Assistant
        </button>
      )}
      <button
        className="sources-toggle"
        data-tour="sessions-btn"
        onClick={onOpenSessions}
        title="Save the current graph + chat, or reopen a saved one"
      >
        🗂 Sessions
      </button>
      <button
        className="sources-toggle icon-toggle"
        onClick={onToggleTheme}
        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {/* The icon shows the ACTION, not the current state — like a play
            button showing ▶ while paused. In dark mode you're offered the
            sun; in light mode, the moon. The U+FE0E on the sun forces text
            presentation: without it the platform renders a colour emoji that
            sizes the whole button differently from the moon. */}
        <span className="theme-glyph">{theme === 'dark' ? '\u2600\uFE0E' : '\u263E'}</span>
      </button>
      <button
        className="sources-toggle icon-toggle"
        data-tour="settings-btn"
        onClick={onOpenSettings}
        title="Settings — the app's configuration, editable in place"
        aria-label="Open settings"
      >
        <span className="settings-gear">⚙</span>
      </button>
      <button
        className="sources-toggle icon-toggle tour-launch"
        onClick={onStartTour}
        title="A quick guided tour of the tools on screen"
        aria-label="Start the guided tour"
      >
        ?
      </button>
    </header>
  )
}
