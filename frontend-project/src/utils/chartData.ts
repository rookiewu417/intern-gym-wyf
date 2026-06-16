import type { MarketBar } from '../services/marketFeed'

export interface Candle { time: number; open: number; high: number; low: number; close: number }
export interface VolumePoint { time: number; value: number; color: string }

// 分钟级 K 线必须用 UTC epoch 秒作为 time，date-only 会把全天塌成一根。
export function timeToEpochSec(ts: string): number {
  return Math.floor(Date.parse(ts) / 1000)
}

export function toCandles(bars: MarketBar[]): Candle[] {
  return bars.map((b) => ({
    time: timeToEpochSec(b.timestamp),
    open: Number(b.open), high: Number(b.high), low: Number(b.low), close: Number(b.close),
  }))
}

export function toVolumes(bars: MarketBar[]): VolumePoint[] {
  return bars.map((b) => ({
    time: timeToEpochSec(b.timestamp),
    value: Number(b.volume || 0),
    color: Number(b.close) >= Number(b.open) ? '#0f62fe33' : '#da1e2833',
  }))
}
