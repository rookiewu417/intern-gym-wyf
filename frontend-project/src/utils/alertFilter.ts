import type { TradeAlert } from '../services/marketFeed'

// 大额交易只能进入当前 effective day 视图：tradeDate 与 sourceDate 都需等于当日。
export function filterAlertsByTradeDate(alerts: TradeAlert[], tradeDate: string): TradeAlert[] {
  if (!tradeDate) return alerts
  return alerts.filter((x) => x.tradeDate === tradeDate && x.sourceDate === tradeDate)
}

export function dedupeAlertsById(alerts: TradeAlert[]): TradeAlert[] {
  const seen = new Set<string>()
  const out: TradeAlert[] = []
  for (const x of alerts) {
    if (seen.has(x.id)) continue
    seen.add(x.id)
    out.push(x)
  }
  return out
}
