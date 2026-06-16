import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BrokerQueue from './BrokerQueue.vue'
import type { QueueLevel } from '../services/marketFeed'

function lvl(side: 'ask' | 'bid', position: number): QueueLevel {
  return { id: `${side}-${position}`, side, position, gear: position, price: 100 + position, volume: 10, brokerCount: 1, brokers: [{ brokerCode: 'x', displayName: '券商', volume: 10 }] }
}
const ask = [lvl('ask', 1), lvl('ask', 3), lvl('ask', 11)]
const bid = [lvl('bid', 1)]

describe('BrokerQueue', () => {
  it('点击 100 档 emit setGear(100)', async () => {
    const w = mount(BrokerQueue, { props: { ask, bid, gear: 10, expandedCells: new Set<string>(), symbol: 'A' } })
    await w.findAll('button.gear')[1].trigger('click')  // 10 / 100 / 1000
    expect(w.emitted('setGear')?.[0]).toEqual([100])
  })

  it('档位过滤由父级 visibleLevels 完成；本组件按传入 ask 渲染原始 position', () => {
    const w = mount(BrokerQueue, { props: { ask: [lvl('ask', 1), lvl('ask', 3)], bid, gear: 10, expandedCells: new Set<string>(), symbol: 'A' } })
    expect(w.text()).toContain('1档')
    expect(w.text()).toContain('3档')
  })

  it('fallback 时显示徽标', () => {
    const w = mount(BrokerQueue, { props: { ask, bid, gear: 10, expandedCells: new Set<string>(), symbol: 'A', fallback: true, sourceDate: '20260603' } })
    expect(w.text()).toContain('Fallback 20260603')
  })
})
