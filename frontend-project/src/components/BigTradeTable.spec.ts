import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BigTradeTable from './BigTradeTable.vue'
import type { TradeAlert } from '../services/marketFeed'

const alerts: TradeAlert[] = [
  { id: '1', timestamp: '2026-06-12T10:31:00+08:00', tradeDate: '20260612', sourceDate: '20260612', price: 350, volume: 10000, turnover: 1, side: 'buy' },
]

describe('BigTradeTable', () => {
  it('渲染 alert 行', () => {
    const w = mount(BigTradeTable, { props: { alerts } })
    expect(w.findAll('tbody tr').length).toBe(1)
  })
  it('空数组显示空态', () => {
    const w = mount(BigTradeTable, { props: { alerts: [] } })
    expect(w.text()).toContain('No current-day alerts')
  })
})
