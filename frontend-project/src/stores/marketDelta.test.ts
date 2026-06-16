import { describe, expect, it } from 'vitest'
import { barTradeDate, upsertBar } from './marketDelta'
import type { MarketBar } from '../services/marketFeed'

function bar(ts: string, close = 1): MarketBar {
  return { timestamp: ts, price: close, open: close, high: close, low: close, close, volume: 1, turnover: 1 }
}

describe('barTradeDate', () => {
  it('从 ISO timestamp 取 YYYYMMDD', () => {
    expect(barTradeDate(bar('2026-06-12T10:31:00.000+08:00'))).toBe('20260612')
  })
})

describe('upsertBar', () => {
  it('同 timestamp 覆盖，按时间排序', () => {
    const out = upsertBar([bar('2026-06-12T10:00:00+08:00', 1)], bar('2026-06-12T10:00:00+08:00', 2))
    expect(out.length).toBe(1)
    expect(out[0].close).toBe(2)
  })
  it('新 timestamp 追加并保持有序', () => {
    const out = upsertBar([bar('2026-06-12T10:01:00+08:00')], bar('2026-06-12T10:00:00+08:00'))
    expect(out.map(b => b.timestamp)).toEqual(['2026-06-12T10:00:00+08:00', '2026-06-12T10:01:00+08:00'])
  })
})
