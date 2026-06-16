import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useMarketStore } from './marketStore'
import type { BrokerQueue, SnapshotPayload, TradeAlert } from '../services/marketFeed'

function snap(symbol: string, tradeDate: string, alerts: TradeAlert[] = [], bq?: BrokerQueue): SnapshotPayload {
  return {
    symbol,
    snapshot: { symbol, name: '测试', price: 1, updatedAt: `${tradeDate}T10:00:00+08:00`, tradeDate },
    minute_bars: [],
    alerts,
    broker_queue: bq ?? { ask: [], bid: [] },
    freshness: { runtime_state: 'WARM', effective_day: tradeDate },
  }
}
function alert(id: string, td: string): TradeAlert {
  return { id, timestamp: `${td}T10:00:00+08:00`, tradeDate: td, sourceDate: td, price: 1, volume: 1, turnover: 1, side: 'buy' }
}

describe('marketStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('setSnapshot 整体覆盖并记录 maxSeq', () => {
    const s = useMarketStore()
    s.setSnapshot('A', snap('A', '20260612'), 5)
    expect(s.records['A'].maxSeq).toBe(5)
  })

  it('applyDelta 丢弃 seq<=maxSeq', () => {
    const s = useMarketStore()
    s.setSnapshot('A', snap('A', '20260612'), 5)
    s.applyDelta('A', { delta_type: 'broker_queue', broker_queue: { ask: [{ id: 'x', side: 'ask', position: 1, gear: 1, price: 1, volume: 1, brokerCount: 0, brokers: [] }], bid: [] } }, 5)
    expect(s.records['A'].brokerQueue.ask.length).toBe(0) // 被丢弃
  })

  it('broker_queue delta 整张覆盖（非累加）', () => {
    const s = useMarketStore()
    const bq: BrokerQueue = { ask: [
      { id: 'a1', side: 'ask', position: 1, gear: 1, price: 1, volume: 1, brokerCount: 0, brokers: [] },
      { id: 'a2', side: 'ask', position: 2, gear: 2, price: 2, volume: 1, brokerCount: 0, brokers: [] },
    ], bid: [] }
    s.setSnapshot('A', snap('A', '20260612', [], bq), 1)
    s.applyDelta('A', { delta_type: 'broker_queue', broker_queue: { ask: [{ id: 'a9', side: 'ask', position: 9, gear: 9, price: 9, volume: 1, brokerCount: 0, brokers: [] }], bid: [] } }, 2)
    expect(s.records['A'].brokerQueue.ask.map(l => l.id)).toEqual(['a9'])
  })

  it('currentAlerts 过滤掉非当日 + 去重 + 倒序', () => {
    const s = useMarketStore()
    s.setSnapshot('A', snap('A', '20260612', [alert('1', '20260612'), alert('2', '20260611'), alert('1', '20260612')]), 1)
    s.setActiveSymbol('A')
    expect(s.currentAlerts.map(a => a.id)).toEqual(['1'])
  })

  it('displayStatus：未连上看连接态，连上看 runtime_state', () => {
    const s = useMarketStore()
    s.setConnectionStatus('connecting')
    expect(s.displayStatus).toBe('Connecting')
    s.setConnectionStatus('open')
    s.setSnapshot('A', snap('A', '20260612'), 1)
    s.setActiveSymbol('A')
    s.records['A'].freshness.runtime_state = 'LIVE'
    expect(s.displayStatus).toBe('Live')
  })
})
