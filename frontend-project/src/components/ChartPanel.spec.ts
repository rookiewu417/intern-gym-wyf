import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('lightweight-charts', () => {
  const series = { setData: vi.fn(), update: vi.fn() }
  const chart = { addSeries: vi.fn(() => series), remove: vi.fn(), applyOptions: vi.fn(), timeScale: () => ({ fitContent: vi.fn() }), panes: () => [] }
  return { createChart: vi.fn(() => chart), CandlestickSeries: {}, HistogramSeries: {} }
})

import ChartPanel from './ChartPanel.vue'
import type { MarketBar } from '../services/marketFeed'

const bars: MarketBar[] = [
  { timestamp: '2026-06-12T10:00:00+08:00', price: 11, open: 10, high: 12, low: 9, close: 11, volume: 100, turnover: 1 },
]

describe('ChartPanel', () => {
  it('挂载渲染容器，不抛错', () => {
    const w = mount(ChartPanel, { props: { bars, symbol: 'A', name: '深演智能', dataTime: bars[0].timestamp } })
    expect(w.find('.chart-host').exists()).toBe(true)
  })
  it('空 bars 显示空态', () => {
    const w = mount(ChartPanel, { props: { bars: [], symbol: 'A', name: 'A', dataTime: '' } })
    expect(w.text()).toContain('Awaiting data')
  })
})
