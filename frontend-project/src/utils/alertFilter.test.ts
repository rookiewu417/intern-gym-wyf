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
})

describe('dedupeAlertsById', () => {
  it('同 id 只保留第一条', () => {
    expect(dedupeAlertsById([a('1', '20260612'), a('1', '20260612'), a('2', '20260612')]).map(x => x.id)).toEqual(['1', '2'])
  })
})
