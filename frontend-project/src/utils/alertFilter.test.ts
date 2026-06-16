import { describe, expect, it } from 'vitest'
import { filterAlertsByTradeDate, dedupeAlertsById } from './alertFilter'
import type { TradeAlert } from '../services/marketFeed'

function a(id: string, tradeDate: string, sourceDate = tradeDate): TradeAlert {
  return { id, timestamp: `${tradeDate}T10:00:00+08:00`, tradeDate, sourceDate, price: 1, volume: 1, turnover: 1, side: 'buy' }
}

describe('filterAlertsByTradeDate', () => {
  it('只保留 tradeDate 与 sourceDate 都等于当日', () => {
    const alerts = [a('1', '20260612'), a('2', '20260611'), a('3', '20260612', '20260611')]
    expect(filterAlertsByTradeDate(alerts, '20260612').map(x => x.id)).toEqual(['1'])
  })
  it('tradeDate 为空时返回空（隔离优先）', () => {
    expect(filterAlertsByTradeDate([a('1', '20260612')], '').length).toBe(0)
  })
})

describe('dedupeAlertsById', () => {
  it('同 id 只保留第一条（保留首条内容）', () => {
    const first = a('1', '20260612'); first.price = 11
    const dup = a('1', '20260612'); dup.price = 22
    const out = dedupeAlertsById([first, dup, a('2', '20260612')])
    expect(out.map(x => x.id)).toEqual(['1', '2'])
    expect(out[0].price).toBe(11)
  })
})
