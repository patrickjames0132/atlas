/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * A generic scope picker: a checkbox-per-item popover where ALL checked reads
 * as "no scope" (everything) and NONE checked as "nothing" — the same
 * None/[] semantics the callers carry. The copy (icon, noun, hints) comes in
 * via `labels`; the item shape is just `{id, title}`.
 *
 * **One caller as of v7.21.0**: which uploaded **sources** the assistant may
 * search. It served a second scope — the 🎓 picker deciding whether a played
 * lecture was fed to the researcher — until lectures became chat turns and
 * there was nothing left to opt out of. It stays parameterised rather than
 * being folded back into the composer: the generic shape costs nothing, and
 * the next scope (an agent's reach, a filter set) arrives configured.
 *
 * That history explains the CONTROLLED open state (`open`/`onOpenChange`),
 * which would otherwise look like ceremony: with two pickers side by side and
 * the state component-local, both popovers could be open at once and
 * overlapped illegibly, so the parent arbitrates. Closes via the ✕ in the
 * popover header or by re-clicking the trigger.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/** One selectable item, reduced to what the picker shows. */
export interface ScopeItem {
  id: string
  title: string
}

/** The picker's display copy, so the component is not tied to one scope. */
export interface ScopeLabels {
  /** Leading emoji on the trigger button (`📚` for sources). */
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
 * @param labels The display copy (icon, noun, heading, hints) — what keeps
 *               the component independent of the scope it is showing.
 * @param dataTour Optional `data-tour` anchor for the guided tour.
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
  // `all` still drives the trigger's styling (an off-default scope lights it
  // up), but it can't drive the *wording* on its own: "All sources" claims a
  // breadth a one-source library hasn't got, and the label is often the only
  // thing the reader sees — the ask bar hides it down to its tooltip. With a
  // single item the honest label is just what it is: "1 source" / "No sources".
  const buttonLabel =
    all && items.length > 1
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
        // The label is hidden where the picker sits inside the ask bar (see
        // teacher.css), so the current state has to survive in the tooltip.
        title={`${buttonLabel} — ${labels.buttonTitle}`}
      >
        <span className="scope-btn-icon">{labels.icon}</span>
        <span className="scope-btn-label">{buttonLabel}</span>
      </button>
      {open && (
        <div className="scope-pop">
          <div className="scope-pop-head">
            <span>{labels.heading}</span>
            {/* Compact "All / None" (not "Select all / Deselect all"): with a
                subset checked BOTH show at once, and the long labels overflowed
                the 240px popover — heading wrapped, ✕ pushed out of view, a
                horizontal scrollbar underneath. */}
            <span className="scope-pop-actions">
              {/* Bulk actions need something to act on in bulk: with one item
                  "All"/"None" duplicate the checkbox sitting directly beneath
                  them, so they're just two more things to read. */}
              {items.length > 1 && checkedIds.length < items.length && (
                <button
                  className="link-btn"
                  onClick={onSelectAll}
                  title={`Check every ${labels.unit}`}
                >
                  All
                </button>
              )}
              {items.length > 1 && checkedIds.length > 0 && (
                <button
                  className="link-btn"
                  onClick={onDeselectAll}
                  title={`Uncheck every ${labels.unit}`}
                >
                  None
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
