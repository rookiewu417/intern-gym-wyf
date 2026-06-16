import type { MarketBar } from '../services/marketFeed'

// 从 ISO timestamp 推导 YYYYMMDD 交易日。
export function barTradeDate(bar: MarketBar): string {
  return String(bar.timestamp).slice(0, 10).replaceAll('-', '')
}

// 按 timestamp upsert，时间升序，最多保留 cap 根。
export function upsertBar(bars: MarketBar[], bar: MarketBar, cap = 420): MarketBar[] {
  const next = bars.filter((item) => item.timestamp !== bar.timestamp)
  next.push(bar)
  next.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  return next.slice(-cap)
}
