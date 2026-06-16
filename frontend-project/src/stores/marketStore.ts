import { defineStore } from 'pinia'
import type { BrokerQueue, DeltaPayload, Gear, MarketBar, SnapshotInner, SnapshotPayload, TradeAlert, WsStatus } from '../services/marketFeed'
import { barTradeDate, upsertBar } from './marketDelta'
import { dedupeAlertsById, filterAlertsByTradeDate } from '../utils/alertFilter'
import { filterLevelsByGear } from '../utils/brokerQueueFilter'

function cloneQueue(q: BrokerQueue): BrokerQueue {
  return { ...q, ask: q.ask.slice(), bid: q.bid.slice() }
}

const MAX_VISIBLE_ALERTS = 8

export interface SymbolRecord {
  snapshot: SnapshotInner
  minuteBars: MarketBar[]
  alerts: TradeAlert[]
  brokerQueue: BrokerQueue
  freshness: SnapshotPayload['freshness']
  maxSeq: number
}

interface State {
  records: Record<string, SymbolRecord>
  activeSymbol: string
  wsStatus: WsStatus
  brokerQueueGear: Gear
  expandedCells: Set<string>
}

export const useMarketStore = defineStore('market', {
  state: (): State => ({
    records: {},
    activeSymbol: '',
    wsStatus: 'connecting',
    brokerQueueGear: 10,
    expandedCells: new Set<string>(),
  }),

  getters: {
    activeRecord: (s): SymbolRecord | undefined => s.records[s.activeSymbol],
    effectiveDay(): string {
      return this.activeRecord?.snapshot.tradeDate || ''
    },
    currentAlerts(): TradeAlert[] {
      const r = this.activeRecord
      if (!r) return []
      return dedupeAlertsById(filterAlertsByTradeDate(r.alerts, r.snapshot.tradeDate))
        .slice()
        .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
        .slice(0, MAX_VISIBLE_ALERTS)
    },
    activeDataTime(): string {
      const r = this.activeRecord
      if (!r) return ''
      const last = r.minuteBars.at(-1)?.timestamp || ''
      const updated = r.snapshot.updatedAt || ''
      if (!last) return updated
      if (!updated) return last
      // 用 epoch 比较，避免不同时区格式（+08:00 vs Z）下字典序比较出错。
      return Date.parse(last) >= Date.parse(updated) ? last : updated
    },
    displayStatus(): 'Live' | 'Warm' | 'Closed' | 'Connecting' | 'Error' {
      if (this.wsStatus === 'connecting') return 'Connecting'
      if (this.wsStatus === 'closed') return 'Closed'
      if (this.wsStatus === 'error') return 'Error'
      const rt = String(this.activeRecord?.freshness.runtime_state || '').toUpperCase()
      if (rt === 'LIVE') return 'Live'
      if (rt === 'CLOSED') return 'Closed'
      return 'Warm'
    },
  },

  actions: {
    visibleLevels(side: 'ask' | 'bid') {
      const r = this.activeRecord
      if (!r) return []
      return filterLevelsByGear(r.brokerQueue[side], this.brokerQueueGear)
    },
    setActiveSymbol(symbol: string) {
      this.activeSymbol = symbol
    },
    setConnectionStatus(s: WsStatus) {
      this.wsStatus = s
    },
    setGear(g: Gear) {
      this.brokerQueueGear = g
    },
    toggleCell(key: string) {
      if (this.expandedCells.has(key)) this.expandedCells.delete(key)
      else this.expandedCells.add(key)
    },
    setSnapshot(symbol: string, payload: SnapshotPayload, seq: number) {
      // 整体覆盖（snapshot 完整快照，绝不增量 merge）；maxSeq = 帧 seq（不重置为 0）。
      this.records[symbol] = {
        snapshot: { ...payload.snapshot },
        minuteBars: payload.minute_bars.slice(),
        alerts: payload.alerts.slice(),
        brokerQueue: cloneQueue(payload.broker_queue),
        freshness: payload.freshness || {},
        maxSeq: seq,
      }
    },
    applyDelta(symbol: string, payload: DeltaPayload, seq: number) {
      const r = this.records[symbol]
      if (!r) return
      if (seq != null && seq <= r.maxSeq) return // 丢弃重复/乱序帧
      if (payload.delta_type === 'minute_bar' && payload.minute_bar) {
        const bar = payload.minute_bar
        const newDay = barTradeDate(bar)
        if (newDay !== r.snapshot.tradeDate) {
          // 切日：丢弃旧日 bars；alerts 按新交易日过滤（保留切日前已到达的新日 alert，丢弃旧日）。
          r.minuteBars = []
          r.alerts = r.alerts.filter((a) => a.tradeDate === newDay)
          r.snapshot.tradeDate = newDay
        }
        r.minuteBars = upsertBar(r.minuteBars, bar)
        r.snapshot.price = bar.close
        r.snapshot.updatedAt = bar.timestamp
      } else if (payload.delta_type === 'trade_tick' && payload.alert) {
        // 当日过滤统一在 currentAlerts getter；这里只去重追加。
        if (!r.alerts.some((a) => a.id === payload.alert!.id)) {
          r.alerts = [payload.alert, ...r.alerts].slice(0, 100)
        }
        r.snapshot.price = payload.alert.price
        r.snapshot.updatedAt = payload.alert.timestamp
      } else if (payload.delta_type === 'broker_queue' && payload.broker_queue) {
        r.brokerQueue = cloneQueue(payload.broker_queue) // 整张覆盖（防御性浅拷贝）
      }
      if (seq != null) r.maxSeq = seq
    },
  },
})
