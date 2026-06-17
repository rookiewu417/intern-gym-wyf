import { describe, expect, it } from 'vitest'
import { filterLevelsByGear, levelTotalVolume } from './brokerQueueFilter'
import type { QueueLevel, BrokerCell } from '../services/marketFeed'

function lvl(position: number, volume: number, brokers: BrokerCell[] = []): QueueLevel {
  return { id: `ask-${position}`, side: 'ask', position, gear: position, price: 100 + position, volume, brokerCount: brokers.length, brokers }
}

describe('filterLevelsByGear', () => {
  const sparse = [lvl(1, 10), lvl(3, 10), lvl(5, 10), lvl(11, 10), lvl(13, 10), lvl(15, 10)]

  it('10档只保留 position<=10，且不重编号', () => {
    const out = filterLevelsByGear(sparse, 10)
    expect(out.map(l => l.position)).toEqual([1, 3, 5])
  })

  it('100档保留全部 position<=100', () => {
    expect(filterLevelsByGear(sparse, 100).map(l => l.position)).toEqual([1, 3, 5, 11, 13, 15])
  })

  it('阈值是 gear 本身（不是 gear/10）', () => {
    expect(filterLevelsByGear([lvl(8, 1), lvl(10, 1)], 10).map(l => l.position)).toEqual([8, 10])
  })
})

describe('levelTotalVolume', () => {
  it('等于档内各 broker volume 之和', () => {
    const level = { ...lvl(1, 999), brokers: [
      { brokerCode: 'a', displayName: 'A', volume: 300 },
      { brokerCode: 'b', displayName: 'B', volume: 450 },
    ], brokerCount: 2 }
    expect(levelTotalVolume(level)).toBe(750)
  })
  it('空 brokers 返回 0', () => {
    expect(levelTotalVolume(lvl(1, 0))).toBe(0)
  })
})
