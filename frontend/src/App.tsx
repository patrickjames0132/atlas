import { useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchPapers,
  fetchSummary,
  fetchCategories,
  saveCategories,
  refresh,
  searchPapers,
  notebookLmExportUrl,
  type Paper,
  type CategoryGroup,
} from './api'
import CategoryPicker from './CategoryPicker'
import CategoryFilter, { type FilterOption } from './CategoryFilter'
import './App.css'

const PAGE_SIZE = 20

// Local-time YYYY-MM-DD (so the date picker matches the user's calendar day).
function todayISO(): string {
  const now = new Date()
  const tz = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - tz).toISOString().slice(0, 10)
}

// The calendar day before `iso` (YYYY-MM-DD), computed in local time. Built from
// numeric parts so we never trip over UTC parsing shifting the date.
function prevDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  dt.setDate(dt.getDate() - 1)
  const mm = String(dt.getMonth() + 1).padStart(2, '0')
  const dd = String(dt.getDate()).padStart(2, '0')
  return `${dt.getFullYear()}-${mm}-${dd}`
}

// Every day in [start, end] inclusive, newest first (so the table grows
// newest→oldest, matching the stored ordering).
function daysDescending(start: string, end: string): string[] {
  const days: string[] = []
  for (let cur = end; cur >= start; cur = prevDay(cur)) days.push(cur)
  return days
}

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
  const today = todayISO()
  const [papers, setPapers] = useState<Paper[]>([])
  const [pulledDates, setPulledDates] = useState<string[]>([])
  const [followed, setFollowed] = useState<string[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [startDate, setStartDate] = useState<string>(today)
  const [endDate, setEndDate] = useState<string>(today)
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Paper[]>([])
  const [searchMode, setSearchMode] = useState<'hybrid' | 'lexical'>('lexical')
  const [searching, setSearching] = useState(false)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  // Day-by-day pull progress (null when idle): which day we're on of how many,
  // and how many papers have streamed into the table so far.
  const [progress, setProgress] = useState<{
    done: number
    total: number
    papers: number
  } | null>(null)
  const [status, setStatus] = useState<string>('')
  const [page, setPage] = useState(1)
  const [catGroups, setCatGroups] = useState<CategoryGroup[]>([])
  const [catOpen, setCatOpen] = useState(false)
  const [catSaving, setCatSaving] = useState(false)

  // A single day shows as "2026-06-26"; a span as "2026-06-24 → 2026-06-26".
  const rangeLabel =
    startDate === endDate ? startDate : `${startDate} → ${endDate}`

  // Mirror the active range in a ref so async loads/pulls can drop stale results
  // from a range the user has since navigated away from.
  const rangeKey = (s: string, e: string) => `${s}|${e}`
  const activeRangeRef = useRef(rangeKey(startDate, endDate))
  useEffect(() => {
    activeRangeRef.current = rangeKey(startDate, endDate)
  }, [startDate, endDate])

  async function load(start: string, end: string): Promise<Paper[]> {
    const key = rangeKey(start, end)
    setLoading(true)
    try {
      const data = await fetchPapers(start, end)
      if (activeRangeRef.current !== key) return data.papers // stale; don't apply
      setPapers(data.papers)
      setPulledDates(data.dates)
      setFollowed(data.followed_categories ?? [])
      return data.papers
    } catch (e) {
      if (activeRangeRef.current === key) setStatus(String(e))
      return []
    } finally {
      if (activeRangeRef.current === key) setLoading(false)
    }
  }

  // Pull the range one day at a time, streaming each day's papers into the table
  // as it arrives so a wide range fills in progressively instead of blocking on
  // one giant request. Aborts cleanly if the user changes the range mid-pull.
  async function pull(start: string, end: string) {
    const key = rangeKey(start, end)
    const span = start === end ? start : `${start} → ${end}`
    const days = daysDescending(start, end)
    setBusy(true)
    setPage(1)
    setPapers([]) // rebuild from scratch as days stream in (newest first)
    setProgress({ done: 0, total: days.length, papers: 0 })
    setStatus(`Fetching papers submitted ${span} from arXiv…`)
    try {
      const acc: Paper[] = []
      for (let i = 0; i < days.length; i++) {
        const day = days[i]
        const result = await refresh(day, day)
        if (activeRangeRef.current !== key) return // user navigated away; abort
        if (!result.ok) {
          setStatus(`Error on ${day}: ${result.error}`)
          return
        }
        const data = await fetchPapers(day, day)
        if (activeRangeRef.current !== key) return
        acc.push(...data.papers)
        setPapers([...acc])
        setPulledDates(data.dates)
        setProgress({ done: i + 1, total: days.length, papers: acc.length })
      }
      setStatus(
        acc.length > 0
          ? `Pulled ${acc.length} paper(s) for ${span}.`
          : `No papers found on arXiv for ${span} in your followed categories.`,
      )
    } catch (e) {
      if (activeRangeRef.current === key) setStatus(String(e))
    } finally {
      if (activeRangeRef.current === key) {
        setBusy(false)
        setProgress(null)
      }
    }
  }

  // Load whatever's already stored for the selected range. Empty ranges are not
  // auto-pulled — the user pulls explicitly via the ↻ button (or the empty
  // state's "Pull papers" button).
  useEffect(() => {
    load(startDate, endDate)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate])

  // Load the taxonomy once so filter chips can show natural-language names.
  useEffect(() => {
    fetchCategories()
      .then((d) => {
        setCatGroups(d.groups)
        setFollowed(d.followed)
      })
      .catch(() => {})
  }, [])

  // Full-text search, debounced. Runs whenever the query or date range changes;
  // an empty query clears results (reverting to the range view). searchSeq drops
  // responses from a superseded keystroke so results never arrive out of order.
  const searchSeq = useRef(0)
  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setSearchResults([])
      setSearching(false)
      return
    }
    const seq = ++searchSeq.current
    setSearching(true)
    const timer = setTimeout(async () => {
      try {
        const data = await searchPapers(q, startDate, endDate)
        if (searchSeq.current === seq) {
          setSearchResults(data.papers)
          setSearchMode(data.mode)
        }
      } catch {
        if (searchSeq.current === seq) setSearchResults([])
      } finally {
        if (searchSeq.current === seq) setSearching(false)
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [query, startDate, endDate])

  // The list everything downstream (filters, table, pagination, footer) renders
  // from: search results when searching, otherwise the range-loaded papers.
  const searchActive = query.trim().length > 0
  const basePapers = searchActive ? searchResults : papers

  function onStartChange(date: string) {
    if (!date || date === startDate) return
    setStartDate(date)
    // Keep the range valid: never let start run past end.
    if (date > endDate) setEndDate(date)
    setSelected([])
    setPage(1)
    setStatus('')
  }

  function onEndChange(date: string) {
    if (!date || date === endDate) return
    setEndDate(date)
    // Keep the range valid: never let end fall before start.
    if (date < startDate) setStartDate(date)
    setSelected([])
    setPage(1)
    setStatus('')
  }

  // Map every category code to its natural-language name (from the taxonomy),
  // so filters read "Machine Learning" rather than "cs.LG".
  const nameMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of catGroups) for (const c of g.categories) m.set(c.code, c.name)
    return m
  }, [catGroups])

  // Map each paper's tags to natural-language names; the names dedupe codes that
  // mean the same subject (e.g. cs.LG + stat.ML → "Machine Learning").
  function paperNames(p: Paper): string[] {
    return p.categories
      .split(/\s+/)
      .filter(Boolean)
      .map((c) => nameMap.get(c) ?? c)
  }

  // Filter options = the subjects present in the loaded day, grouped by name
  // (mirrored tags merged into one), each with a deduped paper count and the
  // underlying codes, most common first.
  const categoryOptions = useMemo<FilterOption[]>(() => {
    const counts = new Map<string, number>()
    const codes = new Map<string, Set<string>>()
    for (const p of basePapers) {
      const names = new Set<string>()
      for (const c of p.categories.split(/\s+/).filter(Boolean)) {
        const name = nameMap.get(c) ?? c
        names.add(name)
        let set = codes.get(name)
        if (!set) {
          set = new Set()
          codes.set(name, set)
        }
        set.add(c)
      }
      for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1)
    }
    return [...counts.entries()]
      .map(([name, count]) => ({
        key: name,
        label: name,
        codes: [...(codes.get(name) ?? [])].sort(),
        count,
      }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  }, [basePapers, nameMap])

  const presentCategories = useMemo(
    () => categoryOptions.map((o) => o.key),
    [categoryOptions],
  )

  // Drop any active filter that's no longer present in the loaded day.
  useEffect(() => {
    setSelected((cur) => {
      const next = cur.filter((c) => presentCategories.includes(c))
      return next.length === cur.length ? cur : next
    })
  }, [presentCategories])

  function toggleCategory(cat: string) {
    setPage(1)
    setSelected((cur) =>
      cur.includes(cat) ? cur.filter((c) => c !== cat) : [...cur, cat],
    )
  }

  async function openCategories() {
    try {
      const data = await fetchCategories()
      setCatGroups(data.groups)
      setFollowed(data.followed)
      setCatOpen(true)
    } catch (e) {
      setStatus(String(e))
    }
  }

  async function onSaveCategories(codes: string[]) {
    setCatSaving(true)
    try {
      const saved = await saveCategories(codes)
      setFollowed(saved)
      setCatOpen(false)
      await pull(startDate, endDate)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e))
    } finally {
      setCatSaving(false)
    }
  }

  // Show papers carrying at least one selected subject (by name); none = all.
  const visiblePapers =
    selected.length === 0
      ? basePapers
      : basePapers.filter((p) => {
          const names = new Set(paperNames(p))
          return selected.some((n) => names.has(n))
        })

  const totalPages = Math.max(1, Math.ceil(visiblePapers.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const pageStart = (safePage - 1) * PAGE_SIZE
  const pagePapers = visiblePapers.slice(pageStart, pageStart + PAGE_SIZE)

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
          <label className="date-field">
            <span>From</span>
            <input
              type="date"
              value={startDate}
              max={today}
              list="pulled-dates"
              onChange={(e) => onStartChange(e.target.value)}
            />
          </label>
          <label className="date-field">
            <span>To</span>
            <input
              type="date"
              value={endDate}
              min={startDate}
              max={today}
              list="pulled-dates"
              onChange={(e) => onEndChange(e.target.value)}
            />
          </label>
          <datalist id="pulled-dates">
            {pulledDates.map((d) => (
              <option key={d} value={d} />
            ))}
          </datalist>
          <button
            className={`icon-btn${busy ? ' spinning' : ''}`}
            onClick={() => pull(startDate, endDate)}
            disabled={busy}
            title={`Re-pull ${rangeLabel} from arXiv`}
            aria-label={`Re-pull ${rangeLabel} from arXiv`}
          >
            ↻
          </button>
          <button className="btn secondary" onClick={openCategories}>
            Categories{followed.length > 0 ? ` (${followed.length})` : ''}
          </button>
          <a
            className="btn secondary"
            href={notebookLmExportUrl(startDate, endDate)}
          >
            Export for NotebookLM
          </a>
        </div>
      </header>

      <div className="search-bar">
        <span className="search-icon" aria-hidden>
          ⌕
        </span>
        <input
          className="search-input"
          type="text"
          value={query}
          placeholder={`Search by meaning or keywords in ${rangeLabel}…`}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        {searching ? (
          <span className="search-meta muted">Searching…</span>
        ) : searchActive ? (
          <span className="search-meta muted">
            {searchResults.length} result{searchResults.length === 1 ? '' : 's'}
            {searchResults.length > 0 && (
              <span className="search-mode" title={
                searchMode === 'hybrid'
                  ? 'Keyword (BM25) + semantic (embeddings), rank-fused'
                  : 'Keyword only — semantic index unavailable'
              }>
                {' '}· {searchMode === 'hybrid' ? 'hybrid' : 'keyword'}
              </span>
            )}
          </span>
        ) : null}
        {query && (
          <button
            className="search-clear"
            onClick={() => {
              setQuery('')
              setPage(1)
            }}
            aria-label="Clear search"
            title="Clear search"
          >
            ×
          </button>
        )}
      </div>

      {catOpen && (
        <CategoryPicker
          groups={catGroups}
          followed={followed}
          saving={catSaving}
          dateLabel={rangeLabel}
          onSave={onSaveCategories}
          onClose={() => setCatOpen(false)}
        />
      )}

      {status && <div className="status">{status}</div>}

      {basePapers.length > 0 && categoryOptions.length > 0 && (
        <CategoryFilter
          options={categoryOptions}
          selected={selected}
          onToggle={toggleCategory}
          onClear={() => setSelected([])}
        />
      )}

      {busy && progress && (
        <div className="progress">
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{
                width: `${Math.round((progress.done / progress.total) * 100)}%`,
              }}
            />
          </div>
          <p className="progress-text muted">
            Fetching from arXiv — day {progress.done}/{progress.total} ·{' '}
            {progress.papers} paper{progress.papers === 1 ? '' : 's'} loaded
          </p>
        </div>
      )}

      {basePapers.length > 0 ? (
        <>
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
              {pagePapers.map((p) => (
                <PaperRow key={p.arxiv_id} paper={p} />
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn secondary"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
              >
                ← Prev
              </button>
              <span className="page-info">
                Page {safePage} of {totalPages}
              </span>
              <button
                className="btn secondary"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
              >
                Next →
              </button>
            </div>
          )}
        </>
      ) : searchActive ? (
        searching ? (
          <p className="muted">Searching…</p>
        ) : (
          <div className="empty">
            <p>No papers match “{query.trim()}”.</p>
            <p className="muted">
              Searching your saved papers for {rangeLabel}. Try different terms,
              or widen the date range to search more of what you've pulled.
            </p>
          </div>
        )
      ) : loading && !busy ? (
        <p className="muted">Loading…</p>
      ) : busy ? null : (
        <div className="empty">
          <p>No papers for {rangeLabel}.</p>
          <p className="muted">
            Nothing was found on arXiv for this range in your followed
            categories. Try another range, broaden your{' '}
            <button className="link-btn inline" onClick={openCategories}>
              categories
            </button>
            , or pull again.
          </p>
          <button
            className="btn"
            onClick={() => pull(startDate, endDate)}
            disabled={busy}
          >
            Pull papers for {rangeLabel}
          </button>
        </div>
      )}

      <footer>
        <span>
          {visiblePapers.length}
          {selected.length > 0 ? ` of ${basePapers.length}` : ''} papers
        </span>
        <span> · {rangeLabel}</span>
        {searchActive && <span> · matching “{query.trim()}”</span>}
      </footer>
    </div>
  )
}
