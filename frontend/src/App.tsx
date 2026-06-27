import { useEffect, useState } from 'react'
import {
  fetchPapers,
  fetchSummary,
  refresh,
  notebookLmExportUrl,
  type Paper,
} from './api'
import './App.css'

function PaperRow({ paper }: { paper: Paper }) {
  const [open, setOpen] = useState(false)
  const [summary, setSummary] = useState<string | null>(paper.summary)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function getSummary() {
    setLoading(true)
    setError('')
    try {
      setSummary(await fetchSummary(paper.arxiv_id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <tr>
      <td className="title-cell">
        <a href={paper.url} target="_blank" rel="noreferrer">
          {paper.title}
        </a>
        <div className="authors">{paper.authors}</div>
      </td>
      <td className="cats">
        {paper.categories
          .split(/\s+/)
          .filter(Boolean)
          .map((c) => (
            <span className="cat-chip" key={c}>
              {c}
            </span>
          ))}
      </td>
      <td className="summary-cell">
        {summary ? (
          summary
        ) : (
          <button className="btn small" onClick={getSummary} disabled={loading}>
            {loading ? 'Summarizing…' : 'Get summary'}
          </button>
        )}
        {error && <div className="error-text">{error}</div>}
        {paper.abstract && (
          <button className="link-btn" onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide abstract' : 'Show abstract'}
          </button>
        )}
        {open && <div className="abstract">{paper.abstract}</div>}
      </td>
      <td className="link-col">
        <a href={paper.url} target="_blank" rel="noreferrer">
          abs
        </a>
        <a
          href={paper.url.replace('/abs/', '/pdf/')}
          target="_blank"
          rel="noreferrer"
        >
          pdf
        </a>
      </td>
    </tr>
  )
}

export default function App() {
  const [papers, setPapers] = useState<Paper[]>([])
  const [dates, setDates] = useState<string[]>([])
  const [followed, setFollowed] = useState<string[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [activeDate, setActiveDate] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string>('')

  async function load(date?: string) {
    setLoading(true)
    try {
      const data = await fetchPapers(date)
      setPapers(data.papers)
      setDates(data.dates)
      setFollowed(data.followed_categories ?? [])
      setActiveDate(data.date ?? undefined)
    } catch (e) {
      setStatus(String(e))
    } finally {
      setLoading(false)
    }
  }

  function toggleCategory(cat: string) {
    setSelected((cur) =>
      cur.includes(cat) ? cur.filter((c) => c !== cat) : [...cur, cat],
    )
  }

  // Show papers that carry at least one selected category; no selection = all.
  const visiblePapers =
    selected.length === 0
      ? papers
      : papers.filter((p) =>
          p.categories.split(/\s+/).some((c) => selected.includes(c)),
        )

  useEffect(() => {
    load()
  }, [])

  async function onRefresh() {
    setBusy(true)
    setStatus('Fetching latest papers from arXiv…')
    try {
      const result = await refresh() // fetch only — summaries are per-row
      if (!result.ok) {
        setStatus(`Error: ${result.error}`)
      } else {
        await load()
        setStatus(`Done — ${result.papers_new} new paper(s) added.`)
      }
    } catch (e) {
      setStatus(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>arXiv Digest</h1>
          <p className="subtitle">
            Your daily CS/ML papers, summarized by Claude.
          </p>
        </div>
        <div className="controls">
          {dates.length > 0 && (
            <select
              value={activeDate}
              onChange={(e) => {
                setActiveDate(e.target.value)
                load(e.target.value)
              }}
            >
              {dates.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          )}
          <a className="btn secondary" href={notebookLmExportUrl(activeDate)}>
            Export for NotebookLM
          </a>
          <button className="btn" onClick={onRefresh} disabled={busy}>
            {busy ? 'Fetching…' : 'Refresh papers'}
          </button>
        </div>
      </header>

      {status && <div className="status">{status}</div>}

      {followed.length > 0 && papers.length > 0 && (
        <div className="filters">
          <span className="filters-label">Filter:</span>
          {followed.map((cat) => (
            <button
              key={cat}
              className={`filter-chip${selected.includes(cat) ? ' active' : ''}`}
              onClick={() => toggleCategory(cat)}
            >
              {cat}
            </button>
          ))}
          {selected.length > 0 && (
            <button className="link-btn" onClick={() => setSelected([])}>
              clear
            </button>
          )}
        </div>
      )}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : papers.length === 0 ? (
        <div className="empty">
          <p>No papers yet.</p>
          <p className="muted">
            Click <strong>Refresh</strong> to pull today's arXiv emails, parse
            the papers, and generate AI summaries.
          </p>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title &amp; authors</th>
              <th>Categories</th>
              <th>AI summary</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            {visiblePapers.map((p) => (
              <PaperRow key={p.arxiv_id} paper={p} />
            ))}
          </tbody>
        </table>
      )}

      <footer>
        <span>
          {visiblePapers.length}
          {selected.length > 0 ? ` of ${papers.length}` : ''} papers
        </span>
        {activeDate && <span> · {activeDate}</span>}
      </footer>
    </div>
  )
}
