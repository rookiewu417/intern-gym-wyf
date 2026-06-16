import type { Gear, QueueLevel } from '../services/marketFeed'

// 10/100/1000 档切换只按原始档位过滤，绝不重新编号/归一化。
export function filterLevelsByGear(levels: QueueLevel[], gear: Gear): QueueLevel[] {
  return levels.filter((l) => l.position <= gear)
}

// 每档总挂单量恒等于档内各 broker volume 之和，与 10/100/1000 切换无关。
export function levelTotalVolume(level: QueueLevel): number {
  return level.brokers.reduce((sum, b) => sum + Number(b.volume || 0), 0)
}
