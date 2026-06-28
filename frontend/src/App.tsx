import { useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchPapers,
  fetchSummary,
  fetchCategories,
  saveCategories,
  refresh,
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
  const [activeDate, setActiveDate] = useState<string>(today)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string>('')
  const [page, setPage] = useState(1)
  const [catGroups, setCatGroups] = useState<CategoryGroup[]>([])
  const [catOpen, setCatOpen] = useState(false)
  const [catSaving, setCatSaving] = useState(false)

  // Dates we've already auto-pulled this session (so empty days aren't re-pulled
  // every time you revisit them). Re-pull is always available via the ↻ button.
  const autoPulled = useRef<Set<string>>(new Set())
  // Mirror activeDate in a ref so async loads/pulls can drop stale results from
  // a date the user has since navigated away from.
  const activeDateRef = useRef(activeDate)
  useEffect(() => {
    activeDateRef.current = activeDate
  }, [activeDate])

  async function load(date: string): Promise<Paper[]> {
    setLoading(true)
    try {
      const data = await fetchPapers(date)
      if (activeDateRef.current !== date) return data.papers // stale; don't apply
      setPapers(data.papers)
      setPulledDates(data.dates)
      setFollowed(data.followed_categories ?? [])
      return data.papers
    } catch (e) {
      if (activeDateRef.current === date) setStatus(String(e))
      return []
    } finally {
      if (activeDateRef.current === date) setLoading(false)
    }
  }

  async function pull(date: string) {
    setBusy(true)
    setStatus(`Fetching papers submitted on ${date} from arXiv…`)
    try {
      const result = await refresh(date)
      if (activeDateRef.current !== date) return
      if (!result.ok) {
        setStatus(`Error: ${result.error}`)
        return
      }
      const got = await load(date)
      if (activeDateRef.current !== date) return
      setPage(1)
      setStatus(
        got.length > 0
          ? `Pulled ${result.papers_new} new paper(s) for ${date}.`
          : `No papers found on arXiv for ${date} in your followed categories.`,
      )
    } catch (e) {
      if (activeDateRef.current === date) setStatus(String(e))
    } finally {
      if (activeDateRef.current === date) setBusy(false)
    }
  }

  // Load the selected date; if it has no papers (and we haven't tried yet this
  // session), auto-pull it from arXiv after a short debounce so scrubbing
  // through dates doesn't fire a request per date.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    ;(async () => {
      const found = await load(activeDate)
      if (cancelled) return
      if (found.length === 0 && !autoPulled.current.has(activeDate)) {
        autoPulled.current.add(activeDate)
        timer = setTimeout(() => {
          if (!cancelled) pull(activeDate)
        }, 500)
      }
    })()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDate])

  // Load the taxonomy once so filter chips can show natural-language names.
  useEffect(() => {
    fetchCategories()
      .then((d) => {
        setCatGroups(d.groups)
        setFollowed(d.followed)
      })
      .catch(() => {})
  }, [])

  function onDateChange(date: string) {
    if (!date || date === activeDate) return
    setActiveDate(date)
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
    for (const p of papers) {
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
  }, [papers, nameMap])

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

  async function onSaveCategories(codes: string[], alsoPull: boolean) {
    setCatSaving(true)
    try {
      const saved = await saveCategories(codes)
      setFollowed(saved)
      setCatOpen(false)
      if (alsoPull) {
        autoPulled.current.add(activeDate) // we're pulling now; don't double-fire
        await pull(activeDate)
      } else {
        setStatus(
          `Categories updated (${saved.length} followed). ` +
            `Re-pull ${activeDate} (↻) to apply them.`,
        )
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e))
    } finally {
      setCatSaving(false)
    }
  }

  // Show papers carrying at least one selected subject (by name); none = all.
  const visiblePapers =
    selected.length === 0
      ? papers
      : papers.filter((p) => {
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
            <span>Date</span>
            <input
              type="date"
              value={activeDate}
              max={today}
              list="pulled-dates"
              onChange={(e) => onDateChange(e.target.value)}
            />
            <datalist id="pulled-dates">
              {pulledDates.map((d) => (
                <option key={d} value={d} />
              ))}
            </datalist>
          </label>
          <button
            className={`icon-btn${busy ? ' spinning' : ''}`}
            onClick={() => pull(activeDate)}
            disabled={busy}
            title={`Re-pull ${activeDate} from arXiv`}
            aria-label={`Re-pull ${activeDate} from arXiv`}
          >
            ↻
          </button>
          <button className="btn secondary" onClick={openCategories}>
            Categories{followed.length > 0 ? ` (${followed.length})` : ''}
          </button>
          <a className="btn secondary" href={notebookLmExportUrl(activeDate)}>
            Export for NotebookLM
          </a>
        </div>
      </header>

      {catOpen && (
        <CategoryPicker
          groups={catGroups}
          followed={followed}
          saving={catSaving}
          dateLabel={activeDate}
          onSave={onSaveCategories}
          onClose={() => setCatOpen(false)}
        />
      )}

      {status && <div className="status">{status}</div>}

      {papers.length > 0 && categoryOptions.length > 0 && (
        <CategoryFilter
          options={categoryOptions}
          selected={selected}
          onToggle={toggleCategory}
          onClear={() => setSelected([])}
        />
      )}

      {loading || busy ? (
        <p className="muted">
          {busy ? `Fetching ${activeDate} from arXiv…` : 'Loading…'}
        </p>
      ) : papers.length === 0 ? (
        <div className="empty">
          <p>No papers for {activeDate}.</p>
          <p className="muted">
            Nothing was found on arXiv for this date in your followed
            categories. Try another date, broaden your{' '}
            <button className="link-btn inline" onClick={openCategories}>
              categories
            </button>
            , or pull again.
          </p>
          <button className="btn" onClick={() => pull(activeDate)} disabled={busy}>
            Pull papers for {activeDate}
          </button>
        </div>
      ) : (
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
      )}

      <footer>
        <span>
          {visiblePapers.length}
          {selected.length > 0 ? ` of ${papers.length}` : ''} papers
        </span>
        <span> · {activeDate}</span>
      </footer>
    </div>
  )
}
