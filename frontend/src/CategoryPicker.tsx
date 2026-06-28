import { useMemo, useState } from 'react'
import type { CategoryGroup } from './api'

// A searchable, grouped checkbox picker for the full arXiv taxonomy (~155
// categories). The chosen set is what we pull from arXiv *and* filter on.
export default function CategoryPicker({
  groups,
  followed,
  saving,
  dateLabel,
  onSave,
  onClose,
}: {
  groups: CategoryGroup[]
  followed: string[]
  saving: boolean
  dateLabel: string
  onSave: (codes: string[], pull: boolean) => void
  onClose: () => void
}) {
  const [picked, setPicked] = useState<Set<string>>(new Set(followed))
  const [query, setQuery] = useState('')

  const q = query.trim().toLowerCase()
  const filteredGroups = useMemo(
    () =>
      groups
        .map((g) => ({
          group: g.group,
          categories: g.categories.filter(
            (c) =>
              !q ||
              c.code.toLowerCase().includes(q) ||
              c.name.toLowerCase().includes(q),
          ),
        }))
        .filter((g) => g.categories.length > 0),
    [groups, q],
  )

  function toggle(code: string) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  function setMany(codes: string[], on: boolean) {
    setPicked((prev) => {
      const next = new Set(prev)
      for (const c of codes) {
        if (on) next.add(c)
        else next.delete(c)
      }
      return next
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label="Manage categories"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2>Categories</h2>
            <p className="muted">
              Pick the subjects to pull from arXiv and filter by.
            </p>
          </div>
          <button className="link-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <input
          className="cat-search"
          type="search"
          placeholder="Search code or name (e.g. cs.LG, robotics)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />

        <div className="cat-groups">
          {filteredGroups.map((g) => {
            const codes = g.categories.map((c) => c.code)
            const allOn = codes.every((c) => picked.has(c))
            return (
              <section key={g.group} className="cat-group">
                <div className="cat-group-head">
                  <span className="cat-group-name">{g.group}</span>
                  <button
                    className="link-btn"
                    onClick={() => setMany(codes, !allOn)}
                  >
                    {allOn ? 'clear all' : 'select all'}
                  </button>
                </div>
                <div className="cat-grid">
                  {g.categories.map((c) => (
                    <label key={c.code} className="cat-option">
                      <input
                        type="checkbox"
                        checked={picked.has(c.code)}
                        onChange={() => toggle(c.code)}
                      />
                      <span className="cat-code">{c.code}</span>
                      <span className="cat-name">{c.name}</span>
                    </label>
                  ))}
                </div>
              </section>
            )
          })}
          {filteredGroups.length === 0 && (
            <p className="muted">No categories match “{query}”.</p>
          )}
        </div>

        <div className="modal-foot">
          <span className="muted">{picked.size} selected</span>
          <div className="modal-actions">
            <button className="btn secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button
              className="btn secondary"
              onClick={() => onSave([...picked], false)}
              disabled={saving || picked.size === 0}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              className="btn"
              onClick={() => onSave([...picked], true)}
              disabled={saving || picked.size === 0}
            >
              {saving ? 'Saving…' : `Save & pull ${dateLabel}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
