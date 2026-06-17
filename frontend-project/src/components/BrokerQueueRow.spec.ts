import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BrokerQueueRow from './BrokerQueueRow.vue'
import BrokerCell from './BrokerCell.vue'
import type { QueueLevel } from '../services/marketFeed'

function level(n: number, side: 'ask' | 'bid' = 'ask'): QueueLevel {
  const brokers = Array.from({ length: n }, (_, i) => ({ brokerCode: String(i), displayName: `B${i}`, volume: 10 }))
  return { id: `${side}-1`, side, position: 1, gear: 1, price: 100, volume: 10 * n, brokerCount: n, brokers }
}

describe('BrokerQueueRow', () => {
  it('显示档位 side：ask→卖 / bid→买', () => {
    const ask = mount(BrokerQueueRow, { props: { level: level(1, 'ask'), expanded: false } })
    expect(ask.find('.side').text()).toBe('卖')
    expect(ask.find('.side').classes()).toContain('ask')
    const bid = mount(BrokerQueueRow, { props: { level: level(1, 'bid'), expanded: false } })
    expect(bid.find('.side').text()).toBe('买')
    expect(bid.find('.side').classes()).toContain('bid')
  })
  it('折叠时只显示前 3 个 cell + 溢出按钮 +N', () => {
    const w = mount(BrokerQueueRow, { props: { level: level(5), expanded: false } })
    expect(w.findAllComponents(BrokerCell).length).toBe(3)
    expect(w.find('button.more').text()).toBe('+2')
  })
  it('展开时显示全部 cell', () => {
    const w = mount(BrokerQueueRow, { props: { level: level(5), expanded: true } })
    expect(w.findAllComponents(BrokerCell).length).toBe(5)
  })
  it('点击溢出按钮 emit toggle', async () => {
    const w = mount(BrokerQueueRow, { props: { level: level(5), expanded: false } })
    await w.find('button.more').trigger('click')
    expect(w.emitted('toggle')).toBeTruthy()
  })
  it('cell 数 <= 3 时不显示溢出按钮', () => {
    const w = mount(BrokerQueueRow, { props: { level: level(2), expanded: false } })
    expect(w.find('button.more').exists()).toBe(false)
  })
})
