/**
 * A generic scope picker: a checkbox-per-item popover where ALL checked reads
 * as "no scope" (everything) and NONE checked as "nothing" — the same
 * None/[] semantics the callers carry. Used for two scopes in the assistant
 * panel: which uploaded **sources** the assistant may search, and which
 * already-played **lectures** the researcher folds into its context. The copy
 * (icon, noun, hints) comes in via `labels`; the item shape is just
 * `{id, title}`, so both scopes fit.
 *
 * The popover's open state is CONTROLLED (`open`/`onOpenChange`) so the
 * parent can keep the two pickers mutually exclusive — with it component-local
 * both popovers could be open at once and overlapped illegibly. Closes via
 * the ✕ in the popover header or by re-clicking the trigger.
 */

/** One selectable item — a source or a lecture, reduced to what the picker shows. */
export interface ScopeItem {
  id: string
  title: string
}

/** The picker's display copy, so one component serves sources and lectures. */
export interface ScopeLabels {
  /** Leading emoji on the trigger button (`📚` sources, `🎓` lectures). */
  icon: string
  /** Singular noun for the count/empty label ("source" → "All sources"). */
  unit: string
  /** The popover's heading ("Search in", "Feed to answers"). */
  heading: string
  /** Footer hint when everything is checked. */
  allHint: string
  /** Footer hint when a subset is checked. */
  someHint: string
  /** Footer hint when nothing is checked. */
  noneHint: string
  /** The trigger button's tooltip. */
  buttonTitle: string
}

/**
 * Render a scope picker: a trigger button showing the current selection, and a
 * checkbox popover to change it.
 *
 * @param items The selectable items (`{id, title}`).
 * @param checkedIds The ids currently checked.
 * @param open Whether the popover is shown (state lives in the parent, which
 *             keeps sibling pickers mutually exclusive).
 * @param onOpenChange Report the popover's next open state (trigger click, ✕).
 * @param onToggle Flip one item's checked state.
 * @param onSelectAll Check every item.
 * @param onDeselectAll Uncheck every item.
 * @param labels The display copy (icon, noun, heading, hints) — what makes one
 *               component serve both the sources and lectures scopes.
 * @param dataTour Optional `data-tour` anchor for the guided tour, so its
 *                 steps can tell the two picker instances apart.
 * @returns The collapsible checkbox list.
 */
export default function ScopePicker({
  items,
  checkedIds,
  open,
  onOpenChange,
  onToggle,
  onSelectAll,
  onDeselectAll,
  labels,
  dataTour,
}: {
  items: ScopeItem[]
  checkedIds: string[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onToggle: (id: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  labels: ScopeLabels
  dataTour?: string
}) {
  const all = checkedIds.length === items.length
  const buttonLabel = all
    ? `All ${labels.unit}s`
    : checkedIds.length === 0
      ? `No ${labels.unit}s`
      : `${checkedIds.length} ${labels.unit}${checkedIds.length > 1 ? 's' : ''}`
  return (
    <div className="scope-wrap" data-tour={dataTour}>
      <button
        type="button"
        className={`scope-btn ${all ? '' : 'on'}`}
        onClick={() => onOpenChange(!open)}
        title={labels.buttonTitle}
      >
        {labels.icon} {buttonLabel}
      </button>
      {open && (
        <div className="scope-pop">
          <div className="scope-pop-head">
            <span>{labels.heading}</span>
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
              <button
                className="link-btn"
                onClick={() => onOpenChange(false)}
                aria-label={`Close the ${labels.unit} picker`}
              >
                ✕
              </button>
            </span>
          </div>
          {items.map((item) => (
            <label key={item.id} className="scope-item">
              <input
                type="checkbox"
                checked={checkedIds.includes(item.id)}
                onChange={() => onToggle(item.id)}
              />
              <span className="scope-item-title" title={item.title}>
                {item.title}
              </span>
            </label>
          ))}
          <div className="scope-hint">
            {all ? labels.allHint : checkedIds.length === 0 ? labels.noneHint : labels.someHint}
          </div>
        </div>
      )}
    </div>
  )
}
