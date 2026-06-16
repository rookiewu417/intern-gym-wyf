import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import * as lwc from 'lightweight-charts'

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

function chartMock() {
  return (lwc.createChart as any).mock.results.at(-1)!.value
}

describe('ChartPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('挂载渲染容器，不抛错', () => {
    const w = mount(ChartPanel, { props: { bars, symbol: 'A', name: '深演智能', dataTime: bars[0].timestamp } })
    expect(w.find('.chart-host').exists()).toBe(true)
  })

  it('空 bars 显示空态', () => {
    const w = mount(ChartPanel, { props: { bars: [], symbol: 'A', name: 'A', dataTime: '' } })
    expect(w.text()).toContain('Awaiting data')
  })

  it('成交量直方图放在 paneIndex=1（与 K 线分离不重叠）', () => {
    mount(ChartPanel, { props: { bars, symbol: 'A', name: 'A', dataTime: bars[0].timestamp } })
    const calls = chartMock().addSeries.mock.calls
    expect(calls.length).toBe(2)   // 蜡烛 + 成交量
    expect(calls[1][2]).toBe(1)    // 第二条（成交量）放 pane 1
  })

  it('卸载时 chart.remove 被调用（防泄漏）', () => {
    const w = mount(ChartPanel, { props: { bars, symbol: 'A', name: 'A', dataTime: bars[0].timestamp } })
    const chart = chartMock()
    w.unmount()
    expect(chart.remove).toHaveBeenCalled()
  })
})
