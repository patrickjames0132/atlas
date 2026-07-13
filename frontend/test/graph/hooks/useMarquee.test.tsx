// @vitest-environment jsdom
/**
 * The alt-drag marquee: Alt arms the overlay, a drag commits the enclosed
 * visible nodes to the selection (screen-space hit-testing against a fake
 * `graph2ScreenCoords`), shift-drag unions onto the pick, and a negligible
 * alt-click clears it.
 */

import { createElement } from 'react'
import type { ReactNode, MouseEvent as ReactMouseEvent, RefObject } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore } from '@reduxjs/toolkit'
import workspace, { nodeSelectionSet } from '../../../src/store/workspace'
import { useMarquee } from '../../../src/graph/hooks/useMarquee'
import type { VNode } from '../../../src/graph/model'

/** A visible node placed at a sim position; its screen coords equal x/y here. */
function node(id: string, x: number, y: number): VNode {
  return {
    id,
    arxiv_id: null,
    title: id,
    year: 2020,
    citation_count: 0,
    url: null,
    rels: ['reference'],
    is_seed: false,
    x,
    y,
  }
}

// Three nodes on a line: two inside a top-left box, one far away.
const VIEW = { nodes: [node('a', 10, 10), node('b', 40, 40), node('c', 500, 500)], links: [] }

/** A fake ForceGraph ref whose screen coords are the node's own x/y (the wrap
 *  sits at the origin, so no offset). */
const fgRef = { current: { graph2ScreenCoords: (x: number, y: number) => ({ x, y }) } }

/** A wrap element whose bounding box is the viewport origin. */
function makeWrapRef(): RefObject<HTMLDivElement | null> {
  return {
    current: {
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
    } as unknown as HTMLDivElement,
  }
}

/** A fresh store per test so selections don't bleed across cases. */
function freshStore() {
  return configureStore({ reducer: { workspace } })
}

/** Render the hook inside a Provider bound to `store`. */
function renderMarquee(store: ReturnType<typeof freshStore>) {
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(Provider, { store }, children)
  return renderHook(() => useMarquee({ view: VIEW, fgRef, wrapRef: makeWrapRef() }), { wrapper })
}

/** A synthetic React mousedown at (clientX, clientY) with the given modifiers. */
function armMouseDown(clientX: number, clientY: number, mods: Partial<MouseEvent> = {}) {
  return {
    altKey: true,
    shiftKey: false,
    clientX,
    clientY,
    preventDefault: () => {},
    ...mods,
  } as unknown as ReactMouseEvent
}

/** Fire a window-level mouse move/up the drag listeners receive. */
function fireMouse(type: 'mousemove' | 'mouseup', clientX: number, clientY: number) {
  window.dispatchEvent(new MouseEvent(type, { clientX, clientY }))
}

afterEach(() => {
  // Nothing global to reset — each test builds its own store and refs.
})

describe('useMarquee', () => {
  it('arms while Alt is held and disarms on keyup', () => {
    const { result } = renderMarquee(freshStore())
    expect(result.current.armed).toBe(false)
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Alt' }))
    })
    expect(result.current.armed).toBe(true)
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keyup', { key: 'Alt' }))
    })
    expect(result.current.armed).toBe(false)
  })

  it('adds the nodes enclosed by an alt-drag, unioning onto any prior pick', () => {
    const store = freshStore()
    store.dispatch(nodeSelectionSet(['z'])) // an existing pick the drag adds onto
    const { result } = renderMarquee(store)

    // Drag a box from (0,0) to (100,100): catches 'a' (10,10) and 'b' (40,40),
    // not 'c' (500,500) — and keeps 'z' (additive, not replace).
    act(() => result.current.onArmMouseDown(armMouseDown(0, 0)))
    act(() => fireMouse('mousemove', 100, 100))
    act(() => fireMouse('mouseup', 100, 100))

    expect([...store.getState().workspace.selectedNodeIds].sort()).toEqual(['a', 'b', 'z'])
    expect(result.current.rect).toBeNull()
  })

  it('builds one scope from several sweeps', () => {
    const store = freshStore()
    const { result } = renderMarquee(store)

    // First sweep grabs 'a' and 'b'.
    act(() => result.current.onArmMouseDown(armMouseDown(0, 0)))
    act(() => fireMouse('mousemove', 100, 100))
    act(() => fireMouse('mouseup', 100, 100))
    // Second sweep, over 'c' far away, adds it rather than replacing.
    act(() => result.current.onArmMouseDown(armMouseDown(450, 450)))
    act(() => fireMouse('mousemove', 550, 550))
    act(() => fireMouse('mouseup', 550, 550))

    expect([...store.getState().workspace.selectedNodeIds].sort()).toEqual(['a', 'b', 'c'])
  })

  it('treats a negligible alt-drag as a click that clears the selection', () => {
    const store = freshStore()
    store.dispatch(nodeSelectionSet(['a', 'b']))
    const { result } = renderMarquee(store)

    act(() => result.current.onArmMouseDown(armMouseDown(200, 200)))
    act(() => fireMouse('mouseup', 201, 201)) // 1px move → below the click slop
    expect(store.getState().workspace.selectedNodeIds).toEqual([])
  })

  it('ignores a mousedown without the Alt modifier', () => {
    const store = freshStore()
    const { result } = renderMarquee(store)
    act(() => result.current.onArmMouseDown(armMouseDown(0, 0, { altKey: false })))
    expect(result.current.rect).toBeNull()
  })
})
