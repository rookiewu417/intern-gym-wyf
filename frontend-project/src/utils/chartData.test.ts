import { describe, expect, it } from 'vitest'
import { timeToEpochSec, toCandles, toVolumes } from './chartData'
import type { MarketBar } from '../services/marketFeed'

const bars: MarketBar[] = [
  { timestamp: '2026-06-12T10:00:00.000+08:00', price: 11, open: 10, high: 12, low: 9, close: 11, volume: 100, turnover: 1 },
  { timestamp: '2026-06-12T10:01:00.000+08:00', price: 10, open: 11, high: 11, low: 9, close: 10, volume: 200, turnover: 1 },
]

describe('timeToEpochSec', () => {
  it('分钟级 timestamp 转 UTC epoch 秒（不塌成 date-only）', () => {
    const t0 = timeToEpochSec(bars[0].timestamp)
    const t1 = timeToEpochSec(bars[1].timestamp)
    expect(t1 - t0).toBe(60)
  })
})

describe('toCandles', () => {
  it('映射 OHLC + epoch time', () => {
    expect(toCandles(bars)[0]).toMatchObject({ open: 10, high: 12, low: 9, close: 11 })
    expect(typeof toCandles(bars)[0].time).toBe('number')
  })
})

describe('toVolumes', () => {
  it('涨用蓝、跌用红', () => {
    expect(toVolumes(bars)[0].color).toBe('#0f62fe33')  // close>=open
    expect(toVolumes(bars)[1].color).toBe('#da1e2833')  // close<open
  })
})
