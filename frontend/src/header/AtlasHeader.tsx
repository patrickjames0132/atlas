/**
 * The top bar container: brand, the seed-search form (composed from
 * search/Search), the current seed's title, the drawer toggles
 * (Sources / Assistant / Sessions), and the Claude credit.
 *
 * Purely presentational — search state and drawer visibility live in Atlas
 * and pass through as props.
 */

import type { FormEvent } from 'react'
import type { SearchFilters } from '../api'
import Search from '../search/Search'
import './header.css'

/** Props for {@link AtlasHeader}. */
export interface AtlasHeaderProps {
  /** The controlled search box value (passed through to Search). */
  query: string
  onQueryChange: (q: string) => void
  /** Submit the search form (routes to graph-load or keyword search). */
  onSubmit: (e: FormEvent) => void
  /** A search is in flight. */
  searching: boolean
  /** A graph is loading. */
  loadingGraph: boolean
  /** The optional search filters (passed through to Search). */
  filters: SearchFilters
  onFilters: (f: SearchFilters) => void
  /** The loaded graph's seed title, shown beside the form (null = none). */
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
}

/** Render the app's top bar. */
export default function AtlasHeader({
  query,
  onQueryChange,
  onSubmit,
  searching,
  loadingGraph,
  filters,
  onFilters,
  seedTitle,
  onHome,
  onOpenSources,
  assistantAvailable,
  assistantOpen,
  onToggleAssistant,
  onOpenSessions,
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
      <Search
        query={query}
        onQueryChange={onQueryChange}
        onSubmit={onSubmit}
        searching={searching}
        loadingGraph={loadingGraph}
        filters={filters}
        onFilters={onFilters}
      />
      {seedTitle && (
        <div className="seed-info" title={seedTitle}>
          {seedTitle}
        </div>
      )}
      <button
        className="sources-toggle top-right-start"
        onClick={onOpenSources}
        title="Your sources — books, PDFs, and pages the teacher can search"
      >
        📚 Sources
      </button>
      {assistantAvailable && (
        <button
          className={`sources-toggle ${assistantOpen ? 'on' : ''}`}
          onClick={onToggleAssistant}
          title="The AI assistant — a lecture and Q&A over the graph, or a chat straight over your uploaded library"
        >
          🎓 Assistant
        </button>
      )}
      <button
        className="sources-toggle"
        onClick={onOpenSessions}
        title="Save the current graph + chat, or reopen a saved one"
      >
        🗂 Sessions
      </button>
      <a
        className="cc-credit"
        href="https://www.anthropic.com/claude"
        target="_blank"
        rel="noreferrer"
        title="The AI teacher runs on Claude"
      >
        <svg className="cc-credit-mark" viewBox="0 0 24 24" aria-hidden="true">
          <g stroke="#D97757" strokeWidth="1.7" strokeLinecap="round">
            <line x1="15" y1="12" x2="22" y2="12" />
            <line x1="14.6" y1="13.5" x2="20.66" y2="17" />
            <line x1="13.5" y1="14.6" x2="17" y2="20.66" />
            <line x1="12" y1="15" x2="12" y2="22" />
            <line x1="10.5" y1="14.6" x2="7" y2="20.66" />
            <line x1="9.4" y1="13.5" x2="3.34" y2="17" />
            <line x1="9" y1="12" x2="2" y2="12" />
            <line x1="9.4" y1="10.5" x2="3.34" y2="7" />
            <line x1="10.5" y1="9.4" x2="7" y2="3.34" />
            <line x1="12" y1="9" x2="12" y2="2" />
            <line x1="13.5" y1="9.4" x2="17" y2="3.34" />
            <line x1="14.6" y1="10.5" x2="20.66" y2="7" />
          </g>
        </svg>
        Powered by Claude
      </a>
    </header>
  )
}
