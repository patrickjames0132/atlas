/**
 * The source-scope picker: which of the user's sources the assistant may
 * search. Checkbox-per-source, where ALL checked means "no scope" (search
 * everything) and NONE checked means "search nothing" — the same None/[]
 * semantics the backend carries end to end. Only rendered when the library
 * has more than one source to pick between.
 */

import { useState } from 'react'
import type { Source } from '../api'

export default function ScopePicker({
  items,
  checkedIds,
  onToggle,
  onSelectAll,
  onDeselectAll,
}: {
  items: Source[]
  checkedIds: string[]
  onToggle: (id: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
}) {
  const [open, setOpen] = useState(false)
  const all = checkedIds.length === items.length
  return (
    <div className="scope-wrap">
      <button
        type="button"
        className={`scope-btn ${all ? '' : 'on'}`}
        onClick={() => setOpen((o) => !o)}
        title="Choose which of your sources the assistant may search"
      >
        📚{' '}
        {all
          ? 'All sources'
          : checkedIds.length === 0
            ? 'No sources'
            : `${checkedIds.length} source${checkedIds.length > 1 ? 's' : ''}`}
      </button>
      {open && (
        <div className="scope-pop">
          <div className="scope-pop-head">
            <span>Search in</span>
            <span className="scope-pop-actions">
              {checkedIds.length < items.length && (
                <button className="link-btn" onClick={onSelectAll}>
                  Select all
                </button>
              )}
              {checkedIds.length > 0 && (
                <button className="link-btn" onClick={onDeselectAll}>
                  Deselect all
                </button>
              )}
            </span>
          </div>
          {items.map((s) => (
            <label key={s.id} className="scope-item">
              <input
                type="checkbox"
                checked={checkedIds.includes(s.id)}
                onChange={() => onToggle(s.id)}
              />
              <span className="scope-item-title" title={s.title}>
                {s.title}
              </span>
            </label>
          ))}
          <div className="scope-hint">
            {all
              ? 'All sources are searched.'
              : checkedIds.length === 0
                ? "No sources selected — the assistant won't search your library."
                : 'Only the checked sources are searched.'}
          </div>
        </div>
      )}
    </div>
  )
}
