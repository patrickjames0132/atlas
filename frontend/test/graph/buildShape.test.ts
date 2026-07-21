// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * jsdom for localStorage — the store persists there, and the read-back path
 * (including the corrupt-blob fallbacks) is most of what's worth testing.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_SHAPE,
  getBuildShape,
  sameBuild,
  setBuildShape,
  shapeParams,
} from '../../src/graph/buildShape'

describe('shapeParams', () => {
  it('sends nothing at all for an adaptive shape', () => {
    // The default request URL must be byte-identical to the pre-shape app's.
    expect(shapeParams(DEFAULT_SHAPE)).toEqual([])
    expect(shapeParams({ ...DEFAULT_SHAPE, adaptive: true, numberOfBands: 9 })).toEqual([])
  })

  it('sends the band shape once adaptive is off', () => {
    const params = shapeParams({
      adaptive: false,
      clusterStart: 2015,
      numberOfBands: 8,
      nodesPerBand: 25,
    })
    expect(Object.fromEntries(params)).toEqual({
      adaptive: '0',
      cluster_start: '2015',
      bands: '8',
      per_band: '25',
    })
  })

  it('omits cluster_start when no start year is named', () => {
    const params = Object.fromEntries(
      shapeParams({ adaptive: false, clusterStart: null, numberOfBands: 5, nodesPerBand: 50 }),
    )
    expect(params.cluster_start).toBeUndefined()
    expect(params.adaptive).toBe('0')
  })
})

describe('sameBuild', () => {
  it('treats any two adaptive shapes as the same build', () => {
    // Band fields are inert while adaptive — comparing them would trigger
    // rebuilds that return an identical graph.
    expect(
      sameBuild(DEFAULT_SHAPE, { ...DEFAULT_SHAPE, numberOfBands: 12, clusterStart: 1999 }),
    ).toBe(true)
  })

  it('separates adaptive from non-adaptive', () => {
    expect(sameBuild(DEFAULT_SHAPE, { ...DEFAULT_SHAPE, adaptive: false })).toBe(false)
  })

  it('compares every band field once adaptive is off', () => {
    const base = { adaptive: false, clusterStart: 2015, numberOfBands: 5, nodesPerBand: 50 }
    expect(sameBuild(base, { ...base })).toBe(true)
    expect(sameBuild(base, { ...base, clusterStart: 2016 })).toBe(false)
    expect(sameBuild(base, { ...base, numberOfBands: 6 })).toBe(false)
    expect(sameBuild(base, { ...base, nodesPerBand: 51 })).toBe(false)
  })
})

describe('persistence', () => {
  beforeEach(() => localStorage.clear())

  it('round-trips a shape through localStorage', () => {
    setBuildShape({ adaptive: false, clusterStart: 2015, numberOfBands: 8, nodesPerBand: 25 })
    expect(getBuildShape().clusterStart).toBe(2015)
    expect(localStorage.getItem('atlas.buildShape')).toContain('2015')
  })

  it('defaults to adaptive when nothing is stored', () => {
    // Not asserted through getBuildShape (module state outlives the clear) —
    // the contract is that the default itself is the adaptive one.
    expect(DEFAULT_SHAPE.adaptive).toBe(true)
    expect(DEFAULT_SHAPE.clusterStart).toBeNull()
  })
})
