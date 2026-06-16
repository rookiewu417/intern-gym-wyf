import type { MarketBar } from '../services/marketFeed'

// 从 ISO timestamp 推导 YYYYMMDD 交易日。
// 约定：feed 的 timestamp 带交易所时区偏移（如 +08:00），其日期部分即交易日；
// 故直接截取字符串日期部分，切勿转 UTC（会把 23:xx 收盘错移到前一天）。
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
