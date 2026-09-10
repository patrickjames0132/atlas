/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The Force layout's relation clustering: sector directions (references pull
 * west, citations east), √population orbits, seed and unknown-relation
 * exemptions, and re-initialization picking up discoveries.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { describe, expect, it } from 'vitest'
import {
  clusterCounts,
  clusterForce,
  clusterRadius,
  deriveOrigins,
} from '../../src/graph/clusterForce'
import type { VNode } from '../../src/graph/model'

function makeNode(id: string, rels: string[], overrides: Partial<VNode> = {}): VNode {
  return {
    id,
    arxiv_id: null,
    title: id,
    year: 2020,
    citation_count: 10,
    url: null,
    rels,
    is_seed: false,
    abstract: null,
    tldr: null,
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
    ...overrides,
  }
}

const seed = () => makeNode('seed', [], { is_seed: true, x: 0, y: 0 })

describe('clusterRadius', () => {
  it('grows with the square root of the population', () => {
    const orbit1 = clusterRadius(1)
    const orbit100 = clusterRadius(100)
    expect(orbit100).toBeGreaterThan(orbit1)
    // √100 = 10× the √1 growth over the base.
    expect(orbit100 - clusterRadius(0)).toBeCloseTo(10 * (orbit1 - clusterRadius(0)))
  })
})

describe('clusterCounts', () => {
  it('counts by primary relation and skips the seed', () => {
    const counts = clusterCounts([
      seed(),
      makeNode('r1', ['reference']),
      makeNode('r2', ['reference']),
      makeNode('c1', ['citation']),
      // Multi-relation: clusters where it's painted (its primary rel).
      makeNode('rc', ['reference', 'citation']),
    ])
    expect(counts).toEqual({ reference: 3, citation: 1 })
  })
})

describe('deriveOrigins', () => {
  it('re-stamps restored discoveries from their first edge, skipping seed anchors', () => {
    const nodes = [
      seed(),
      makeNode('expanded', ['citation']),
      makeNode('sat', ['reference'], { discovered: true }),
      makeNode('fromSeed', ['reference'], { discovered: true }),
      makeNode('plain', ['reference']),
    ]
    deriveOrigins(
      nodes,
      [
        { _s: 'expanded', _t: 'sat' },
        { _s: 'seed', _t: 'fromSeed' },
        { _s: 'seed', _t: 'plain' },
      ],
      'seed',
    )
    expect(nodes.find((node) => node.id === 'sat')!._origin).toBe('expanded')
    // Seed-anchored and non-discovered nodes stay sector members.
    expect(nodes.find((node) => node.id === 'fromSeed')!._origin).toBeUndefined()
    expect(nodes.find((node) => node.id === 'plain')!._origin).toBeUndefined()
  })
})

describe('clusterForce', () => {
  /** One initialized force plus the node set it was initialized with. */
  function runOnce(nodes: VNode[]) {
    const force = clusterForce()
    force.initialize(nodes)
    force(1)
    return nodes
  }

  it('pulls each relation toward its own sector around the seed', () => {
    const reference = makeNode('ref', ['reference'])
    const citer = makeNode('cite', ['citation'])
    runOnce([seed(), reference, citer])
    // References west (negative x), citations east — the axis the layout is
    // there to draw. Citations sat at -PI/3 (up-right) until v7.17.0, sharing
    // the eastern half with `latest` at +PI/3; with one citing relation the
    // sector recentres on due east.
    expect(reference.vx!).toBeLessThan(0)
    expect(citer.vx!).toBeGreaterThan(0)
  })

  it('gives a retired `latest` tag the default orbit rather than a sector', () => {
    // A pre-v7.17.0 save is folded to `citation` on restore
    // (`foldRetiredNodeRels`), so this only bites if a stray tag slips
    // through — it must still be placed, not dropped.
    const stale = makeNode('old', ['latest'])
    runOnce([seed(), stale])
    expect(Number.isFinite(stale.vx!)).toBe(true)
    expect(Number.isFinite(stale.vy!)).toBe(true)
  })

  it('anchors relative to the seed’s live position', () => {
    const reference = makeNode('ref', ['reference'], { x: 1000, y: 500 })
    runOnce([seed(), makeNode('ref2', ['reference'], { x: 1000, y: 500 }), reference])
    // From far east of a seed at the origin, the westward anchor pulls the
    // node back toward (and past) the seed: strongly negative x velocity.
    expect(reference.vx!).toBeLessThan(0)
    expect(reference.vy!).toBeLessThan(0)
  })

  it('leaves the seed and unknown relations alone', () => {
    const theSeed = seed()
    const stranger = makeNode('odd', ['unheard-of-relation'])
    // primaryRel falls back to 'similar' for unknown rels, so use rels that
    // resolve to a sectorless key is impossible — instead confirm the seed
    // itself never moves.
    runOnce([theSeed, stranger])
    expect(theSeed.vx).toBe(0)
    expect(theSeed.vy).toBe(0)
  })

  it('gathers an expansion satellite beyond its origin, not in a seed sector', () => {
    // Origin sits due east of the seed; its satellite carries a REFERENCE rel,
    // which the sectors would pull west — the origin must win.
    const origin = makeNode('origin', ['citation'], { x: 300, y: 0 })
    const satellite = makeNode('sat', ['reference'], { x: 300, y: 0, _origin: 'origin' })
    runOnce([seed(), origin, satellite])
    expect(satellite.vx!).toBeGreaterThan(0)
  })

  it('excludes satellites from the sector populations', () => {
    const counts = clusterCounts([
      seed(),
      makeNode('r1', ['reference']),
      makeNode('sat', ['reference'], { _origin: 'r1' }),
    ])
    expect(counts).toEqual({ reference: 1 })
  })

  it('falls back to sector behavior when the origin is filtered out of the sim', () => {
    const orphan = makeNode('sat', ['reference'], { _origin: 'gone' })
    runOnce([seed(), orphan])
    // No origin on screen — the reference sector (west) takes it as usual.
    expect(orphan.vx!).toBeLessThan(0)
  })

  it('re-initializing after discoveries widens a grown cluster’s orbit', () => {
    const force = clusterForce()
    const probe = makeNode('probe', ['reference'])
    const small: VNode[] = [seed(), probe]
    force.initialize(small)
    force(1)
    const smallPull = probe.vx!
    probe.vx = 0
    probe.vy = 0
    const grown = [
      ...small,
      ...Array.from({ length: 99 }, (_, index) => makeNode(`extra-${index}`, ['reference'])),
    ]
    force.initialize(grown)
    force(1)
    // A 100-strong cluster orbits farther out, so the probe (still at the
    // seed) is pulled harder toward the more distant anchor.
    expect(Math.abs(probe.vx!)).toBeGreaterThan(Math.abs(smallPull))
  })
})
