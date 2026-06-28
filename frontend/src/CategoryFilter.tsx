import { useEffect, useRef, useState } from 'react'

export interface FilterOption {
  key: string // the natural-language name; the selection identifier
  label: string
  codes: string[] // the underlying tag(s) merged under this name, e.g. cs.LG + stat.ML
  count: number
}

// A compact, clutter-free filter: the bar shows only the active filters; a
// "Filter ▾" button opens a searchable, counted checklist of every category
// present in the current day. Everything is click-to-activate.
export default function CategoryFilter({
  options,
  selected,
  onToggle,
  onClear,
}: {
  options: FilterOption[]
  selected: string[]
  onToggle: (code: string) => void
  onClear: () => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  // Close the popover when clicking outside it.
  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const q = query.trim().toLowerCase()
  const shown = q
    ? options.filter(
        (o) =>
          o.label.toLowerCase().includes(q) ||
          o.codes.some((c) => c.toLowerCase().includes(q)),
      )
    : options

  const labelOf = (key: string) =>
    options.find((o) => o.key === key)?.label ?? key

  return (
    <div className="filterbar">
      <div className="filter-picker" ref={ref}>
        <button
          className={`btn secondary${selected.length > 0 ? ' has-active' : ''}`}
          onClick={() => setOpen((o) => !o)}
        >
          Filter{selected.length > 0 ? ` (${selected.length})` : ''} ▾
        </button>
        {open && (
          <div className="filter-pop">
            <input
              className="cat-search"
              type="search"
              placeholder="Search categories…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
            <div className="filter-list">
              {shown.map((o) => (
                <label key={o.key} className="cat-option">
                  <input
                    type="checkbox"
                    checked={selected.includes(o.key)}
                    onChange={() => onToggle(o.key)}
                  />
                  <span className="cat-name">{o.label}</span>
                  <span className="filter-codes">{o.codes.join(', ')}</span>
                  <span className="filter-count">{o.count}</span>
                </label>
              ))}
              {shown.length === 0 && <p className="muted">No matches.</p>}
            </div>
            {selected.length > 0 && (
              <div className="filter-pop-foot">
                <button className="link-btn" onClick={onClear}>
                  Clear {selected.length} filter{selected.length > 1 ? 's' : ''}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {selected.map((key) => (
        <button
          key={key}
          className="filter-chip active"
          onClick={() => onToggle(key)}
          title="Remove filter"
        >
          {labelOf(key)} ×
        </button>
      ))}
      {selected.length > 0 ? (
        <button className="link-btn" onClick={onClear}>
          clear
        </button>
      ) : (
        <span className="muted filter-hint">showing all papers</span>
      )}
    </div>
  )
}
