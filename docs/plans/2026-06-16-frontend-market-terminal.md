# Market Terminal Lite 前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `frontend-project/` 从最小占位骨架重构为命中满分 rubric 的实时行情终端：Pinia 集中状态 + 纯函数化业务逻辑 + lightweight-charts 双 pane 图表 + broker queue 档位语义 + effective-day 隔离 + 重连，并为每条红线配单测。

**Architecture:** 传输层（`marketFeed.ts`）保持纯 WebSocket，透传 `frame.seq` 与 `trackedSymbols` 重连重拉；业务逻辑下沉到 Pinia store + `utils/` 纯函数（mock-free 可测）；`App.vue` 退化为薄壳，组件树单一职责。

**Tech Stack:** Vue 3 `<script setup>` + TypeScript + Vite + Pinia + lightweight-charts；测试 Vitest + @vue/test-utils + jsdom。

**参考 spec：** `docs/superpowers/specs/2026-06-16-frontend-market-terminal-design.md`

**Git 身份：** 所有 commit 用 `rookiewu417 <1007372080@qq.com>`（仓库已配置；若未配置，commit 时加 `-c user.name=... -c user.email=...`）。

**所有命令在 `frontend-project/` 下执行。** 实时数据需仓库根 `make serve`（手动联调时）。

---

## 文件结构（决策锁定）

| 文件 | 创建/修改 | 职责 |
|---|---|---|
| `package.json` | 改 | 加 `pinia`/`lightweight-charts`（deps）、`@vue/test-utils`/`jsdom`（devDeps） |
| `vite.config.ts` | 改 | 加 `test: { environment: 'jsdom', globals: true }` |
| `src/main.ts` | 改 | `app.use(createPinia())` |
| `.env.example` | 创建 | `VITE_WS_URL=ws://127.0.0.1:9021/ws` |
| `src/services/marketFeed.ts` | 改 | 扩展类型；`trackedSymbols`；透传 `frame.seq`；`'connecting'` 态；重连重拉 |
| `src/utils/brokerQueueFilter.ts` | 创建 | `filterLevelsByGear` / `levelTotalVolume` |
| `src/utils/alertFilter.ts` | 创建 | `filterAlertsByTradeDate` / `dedupeAlertsById` |
| `src/utils/chartData.ts` | 创建 | `timeToEpochSec` / `toCandles` / `toVolumes` |
| `src/stores/marketDelta.ts` | 创建 | `barTradeDate` / `upsertBar` |
| `src/stores/marketStore.ts` | 创建 | Pinia：state/actions/getters |
| `src/components/ConnectionChip.vue` | 创建 | 状态 chip |
| `src/components/Watchlist.vue` | 创建 | 列表 + 搜索/手输 |
| `src/components/SymbolHeader.vue` | 创建 | 中文名 + 代码 + 数据时间 |
| `src/components/QuoteStrip.vue` | 创建 | 行情摘要 |
| `src/components/BigTradeTable.vue` | 创建 | 当日 alerts |
| `src/components/BrokerCell.vue` | 创建 | 单 broker |
| `src/components/BrokerQueueRow.vue` | 创建 | 单档 |
| `src/components/BrokerQueue.vue` | 创建 | 档位 toggle + 两列 |
| `src/components/ChartPanel.vue` | 创建 | lightweight-charts 双 pane |
| `src/App.vue` | 改 | 薄壳编排 + 响应式 CSS |
| `src/services/marketFeed.spec.ts` 等测试 | 创建 | 见各任务 |
| `frontend-project/README.md` | 改 | 运行/结构/限制 |

---

## Task 1: 项目依赖与配置

**Files:**
- Modify: `package.json`
- Modify: `vite.config.ts`
- Modify: `src/main.ts`
- Modify: `tsconfig.json`
- Create: `.env.example`

- [ ] **Step 1: 安装依赖**

Run:
```bash
npm install pinia lightweight-charts
npm install -D @vue/test-utils jsdom
```
Expected: `package.json` 出现这四个依赖，安装成功。

- [ ] **Step 2: 配置 Vitest 用 jsdom**

把 `vite.config.ts` 改为：
```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 3: main.ts 挂载 Pinia**

把 `src/main.ts` 改为：
```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

createApp(App).use(createPinia()).mount('#app')
```

- [ ] **Step 4: 创建 .env.example + vite/client 类型**

`.env.example`：
```
VITE_WS_URL=ws://127.0.0.1:9021/ws
```

把 `tsconfig.json` 的 `types` 改为含 `vite/client`（否则 `import.meta.env` 类型检查失败）：
```jsonc
"types": ["vitest/globals", "vite/client"]
```

- [ ] **Step 5: 验证既有测试仍通过**

Run: `npm run test`
Expected: 现有 `marketFormat.test.ts` PASS（jsdom 环境下纯函数仍通过）。

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json vite.config.ts src/main.ts tsconfig.json .env.example
git commit -m "chore(frontend): add pinia + lightweight-charts + jsdom test env"
```

---

## Task 2: 扩展共享类型

**Files:**
- Modify: `src/services/marketFeed.ts`（类型部分；传输逻辑在 Task 8 改）

- [ ] **Step 1: 扩展类型定义**

把 `src/services/marketFeed.ts` 顶部的类型块替换为（保留 `MarketFeedClient` 类暂不动）：
```ts
export type Gear = 10 | 100 | 1000
export type WsStatus = 'connecting' | 'open' | 'closed' | 'error'

export interface BrokerCell {
  brokerCode: string
  displayName: string
  volume: number
}

export interface QueueLevel {
  id: string
  side: 'ask' | 'bid'
  position: number
  gear: number
  price: number
  volume: number
  brokerCount: number
  brokers: BrokerCell[]
}

export interface BrokerQueue {
  ask: QueueLevel[]
  bid: QueueLevel[]
  sourceDate?: string
  historical?: boolean
  fallback?: boolean
}

export interface MarketBar {
  timestamp: string
  price: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover: number
}

export interface TradeAlert {
  id: string
  timestamp: string
  tradeDate: string
  sourceDate: string
  price: number
  volume: number
  turnover: number
  side: string
  thresholdVolume?: number
}

export interface SnapshotInner {
  symbol: string
  name: string
  currency?: string
  price: number
  open?: number
  high?: number
  low?: number
  volume?: number
  turnover?: number
  updatedAt: string
  tradeDate: string
}

export interface SnapshotPayload {
  symbol: string
  snapshot: SnapshotInner
  minute_bars: MarketBar[]
  alerts: TradeAlert[]
  broker_queue: BrokerQueue
  freshness: {
    runtime_state?: string
    effective_day?: string
    source_dates?: Record<string, string>
  }
}

export interface DeltaPayload {
  delta_type?: 'minute_bar' | 'trade_tick' | 'broker_queue'
  minute_bar?: MarketBar
  tick?: unknown
  alert?: TradeAlert | null
  broker_queue?: BrokerQueue
}
```

- [ ] **Step 2: 验证类型编译**

Run: `npx vue-tsc --noEmit`
Expected: 无类型错误（`MarketFeedClient` 旧 handler 签名暂时仍编译；Task 8 调整）。

- [ ] **Step 3: Commit**

```bash
git add src/services/marketFeed.ts
git commit -m "feat(frontend): extend market types (BrokerQueue/TradeAlert.sourceDate/Gear/WsStatus)"
```

---

## Task 3: broker queue 过滤纯函数（TDD）

**Files:**
- Create: `src/utils/brokerQueueFilter.ts`
- Test: `src/utils/brokerQueueFilter.test.ts`

- [ ] **Step 1: 写失败测试**

`src/utils/brokerQueueFilter.test.ts`：
```ts
import { describe, expect, it } from 'vitest'
import { filterLevelsByGear, levelTotalVolume } from './brokerQueueFilter'
import type { QueueLevel } from '../services/marketFeed'

function lvl(position: number, volume: number, brokers = []): QueueLevel {
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
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- brokerQueueFilter`
Expected: FAIL（模块未定义）。

- [ ] **Step 3: 实现**

`src/utils/brokerQueueFilter.ts`：
```ts
import type { Gear, QueueLevel } from '../services/marketFeed'

// 10/100/1000 档切换只按原始档位过滤，绝不重新编号/归一化。
export function filterLevelsByGear(levels: QueueLevel[], gear: Gear): QueueLevel[] {
  return levels.filter((l) => l.position <= gear)
}

// 每档总挂单量恒等于档内各 broker volume 之和，与 10/100/1000 切换无关。
export function levelTotalVolume(level: QueueLevel): number {
  return level.brokers.reduce((sum, b) => sum + Number(b.volume || 0), 0)
}
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- brokerQueueFilter`
Expected: PASS（4 cases）。

- [ ] **Step 5: Commit**

```bash
git add src/utils/brokerQueueFilter.ts src/utils/brokerQueueFilter.test.ts
git commit -m "feat(frontend): broker queue gear filter + per-level volume (pure, tested)"
```

---

## Task 4: alert 过滤/去重纯函数（TDD）

**Files:**
- Create: `src/utils/alertFilter.ts`
- Test: `src/utils/alertFilter.test.ts`

- [ ] **Step 1: 写失败测试**

`src/utils/alertFilter.test.ts`：
```ts
import { describe, expect, it } from 'vitest'
import { filterAlertsByTradeDate, dedupeAlertsById } from './alertFilter'
import type { TradeAlert } from '../services/marketFeed'

function a(id: string, tradeDate: string, sourceDate = tradeDate): TradeAlert {
  return { id, timestamp: `${tradeDate}T10:00:00+08:00`, tradeDate, sourceDate, price: 1, volume: 1, turnover: 1, side: 'buy' }
}

describe('filterAlertsByTradeDate', () => {
  it('只保留 tradeDate 与 sourceDate 都等于当日', () => {
    const alerts = [a('1', '20260612'), a('2', '20260611'), a('3', '20260612', '20260611')]
    expect(filterAlertsByTradeDate(alerts, '20260612').map(x => x.id)).toEqual(['1'])
  })
})

describe('dedupeAlertsById', () => {
  it('同 id 只保留第一条', () => {
    expect(dedupeAlertsById([a('1', '20260612'), a('1', '20260612'), a('2', '20260612')]).map(x => x.id)).toEqual(['1', '2'])
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- alertFilter`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/utils/alertFilter.ts`：
```ts
import type { TradeAlert } from '../services/marketFeed'

// 大额交易只能进入当前 effective day 视图：tradeDate 与 sourceDate 都需等于当日。
export function filterAlertsByTradeDate(alerts: TradeAlert[], tradeDate: string): TradeAlert[] {
  if (!tradeDate) return alerts
  return alerts.filter((x) => x.tradeDate === tradeDate && x.sourceDate === tradeDate)
}

export function dedupeAlertsById(alerts: TradeAlert[]): TradeAlert[] {
  const seen = new Set<string>()
  const out: TradeAlert[] = []
  for (const x of alerts) {
    if (seen.has(x.id)) continue
    seen.add(x.id)
    out.push(x)
  }
  return out
}
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- alertFilter`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/utils/alertFilter.ts src/utils/alertFilter.test.ts
git commit -m "feat(frontend): alert effective-day filter + dedup by id (pure, tested)"
```

---

## Task 5: minute bar 纯函数（TDD）

**Files:**
- Create: `src/stores/marketDelta.ts`
- Test: `src/stores/marketDelta.test.ts`

- [ ] **Step 1: 写失败测试**

`src/stores/marketDelta.test.ts`：
```ts
import { describe, expect, it } from 'vitest'
import { barTradeDate, upsertBar } from './marketDelta'
import type { MarketBar } from '../services/marketFeed'

function bar(ts: string, close = 1): MarketBar {
  return { timestamp: ts, price: close, open: close, high: close, low: close, close, volume: 1, turnover: 1 }
}

describe('barTradeDate', () => {
  it('从 ISO timestamp 取 YYYYMMDD', () => {
    expect(barTradeDate(bar('2026-06-12T10:31:00.000+08:00'))).toBe('20260612')
  })
})

describe('upsertBar', () => {
  it('同 timestamp 覆盖，按时间排序', () => {
    const out = upsertBar([bar('2026-06-12T10:00:00+08:00', 1)], bar('2026-06-12T10:00:00+08:00', 2))
    expect(out.length).toBe(1)
    expect(out[0].close).toBe(2)
  })
  it('新 timestamp 追加并保持有序', () => {
    const out = upsertBar([bar('2026-06-12T10:01:00+08:00')], bar('2026-06-12T10:00:00+08:00'))
    expect(out.map(b => b.timestamp)).toEqual(['2026-06-12T10:00:00+08:00', '2026-06-12T10:01:00+08:00'])
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- marketDelta`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/stores/marketDelta.ts`：
```ts
import type { MarketBar } from '../services/marketFeed'

// 从 ISO timestamp 推导 YYYYMMDD 交易日。
export function barTradeDate(bar: MarketBar): string {
  return String(bar.timestamp).slice(0, 10).replaceAll('-', '')
}

// 按 timestamp upsert，时间升序，最多保留 cap 根。
export function upsertBar(bars: MarketBar[], bar: MarketBar, cap = 420): MarketBar[] {
  const next = bars.filter((item) => item.timestamp !== bar.timestamp)
  next.push(bar)
  next.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  return next.slice(-cap)
}
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- marketDelta`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/stores/marketDelta.ts src/stores/marketDelta.test.ts
git commit -m "feat(frontend): minute-bar tradeDate + upsert helpers (pure, tested)"
```

---

## Task 6: 图表数据转换纯函数（TDD）

**Files:**
- Create: `src/utils/chartData.ts`
- Test: `src/utils/chartData.test.ts`

- [ ] **Step 1: 写失败测试**

`src/utils/chartData.test.ts`：
```ts
import { describe, expect, it } from 'vitest'
import { timeToEpochSec, toCandles, toVolumes } from './chartData'
import type { MarketBar } from '../services/marketFeed'

const bars: MarketBar[] = [
  { timestamp: '2026-06-12T10:00:00.000+08:00', price: 11, open: 10, high: 12, low: 9, close: 11, volume: 100, turnover: 1 },
  { timestamp: '2026-06-12T10:01:00.000+08:00', price: 10, open: 11, high: 11, low: 9, close: 10, volume: 200, turnover: 1 },
]

describe('timeToEpochSec', () => {
  it('分钟级 timestamp 转 UTC epoch 秒（不塌成 date-only）', () => {
    const t0 = timeToEpochSec(bars[0].timestamp)
    const t1 = timeToEpochSec(bars[1].timestamp)
    expect(t1 - t0).toBe(60)
  })
})

describe('toCandles', () => {
  it('映射 OHLC + epoch time', () => {
    expect(toCandles(bars)[0]).toMatchObject({ open: 10, high: 12, low: 9, close: 11 })
    expect(typeof toCandles(bars)[0].time).toBe('number')
  })
})

describe('toVolumes', () => {
  it('涨用蓝、跌用红', () => {
    expect(toVolumes(bars)[0].color).toBe('#0f62fe33')  // close>=open
    expect(toVolumes(bars)[1].color).toBe('#da1e2833')  // close<open
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- chartData`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/utils/chartData.ts`：
```ts
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
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- chartData`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/utils/chartData.ts src/utils/chartData.test.ts
git commit -m "feat(frontend): chart data transforms (epoch-sec time, OHLC, volume color)"
```

---

## Task 7: Pinia store（TDD）

**Files:**
- Create: `src/stores/marketStore.ts`
- Test: `src/stores/marketStore.test.ts`

- [ ] **Step 1: 写失败测试**

`src/stores/marketStore.test.ts`：
```ts
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
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- marketStore`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/stores/marketStore.ts`：
```ts
import { defineStore } from 'pinia'
import type { BrokerQueue, DeltaPayload, Gear, MarketBar, SnapshotInner, SnapshotPayload, TradeAlert, WsStatus } from '../services/marketFeed'
import { barTradeDate, upsertBar } from './marketDelta'
import { dedupeAlertsById, filterAlertsByTradeDate } from '../utils/alertFilter'
import { filterLevelsByGear } from '../utils/brokerQueueFilter'

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
        .slice(0, 8)
    },
    activeDataTime(): string {
      const r = this.activeRecord
      if (!r) return ''
      const last = r.minuteBars.at(-1)?.timestamp || ''
      return last > (r.snapshot.updatedAt || '') ? last : r.snapshot.updatedAt || ''
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
        brokerQueue: payload.broker_queue,
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
          // 切日：丢弃旧日 bars + alerts
          r.minuteBars = []
          r.alerts = []
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
        r.brokerQueue = payload.broker_queue // 整张覆盖
      }
      if (seq != null) r.maxSeq = seq
    },
  },
})
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- marketStore`
Expected: PASS（5 cases）。

- [ ] **Step 5: Commit**

```bash
git add src/stores/marketStore.ts src/stores/marketStore.test.ts
git commit -m "feat(frontend): pinia market store (overwrite, seq guard, day-flip, getters)"
```

---

## Task 8: 传输层重连 + seq 透传（TDD）

**Files:**
- Modify: `src/services/marketFeed.ts`（`MarketFeedClient` 类）
- Test: `src/services/marketFeed.spec.ts`

- [ ] **Step 1: 写失败测试**

`src/services/marketFeed.spec.ts`：
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MarketFeedClient } from './marketFeed'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  constructor(public url: string) { MockWebSocket.instances.push(this) }
  send(data: string) { this.sent.push(data) }
  close() { this.readyState = 3; this.onclose?.() }
  open() { this.readyState = MockWebSocket.OPEN; this.onopen?.() }
}

describe('MarketFeedClient', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    ;(globalThis as any).WebSocket = MockWebSocket as any
  })
  afterEach(() => vi.useRealTimers())

  it('重连后自动重发 snapshot_request（tracked symbols）', () => {
    const client = new MarketFeedClient('ws://x', {})
    client.connect()
    client.requestSnapshots(['A'])               // CONNECTING：仅记录 tracked
    const ws1 = MockWebSocket.instances[0]
    ws1.open()
    expect(ws1.sent.filter(s => s.includes('snapshot_request')).length).toBe(1)
    ws1.close()                                   // 非主动关闭
    vi.advanceTimersByTime(1000)                  // 触发重连
    const ws2 = MockWebSocket.instances[1]
    ws2.open()
    expect(ws2.sent.filter(s => s.includes('snapshot_request')).length).toBe(1)
  })

  it('snapshot 帧把 frame.seq 透传给 onSnapshot', () => {
    const seqs: number[] = []
    const client = new MarketFeedClient('ws://x', { onSnapshot: (_sym, _p, seq) => seqs.push(seq) })
    client.connect()
    const ws = MockWebSocket.instances[0]
    ws.open()
    ws.onmessage?.({ data: JSON.stringify({ type: 'snapshot', symbol: 'A', seq: 7, payload: {} }) })
    expect(seqs).toEqual([7])
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- marketFeed.spec`
Expected: FAIL（旧 client 无 tracked/seq）。

- [ ] **Step 3: 实现（替换类）**

把 `src/services/marketFeed.ts` 中 `ClientHandlers` 与 `MarketFeedClient` 替换为：
```ts
import type { WsStatus } from './marketFeed' // 同文件类型，实际无需 import，仅说明

interface ClientHandlers {
  onStatus?: (status: WsStatus) => void
  onSnapshot?: (symbol: string, payload: SnapshotPayload, seq: number) => void
  onDelta?: (symbol: string, payload: DeltaPayload, seq: number) => void
}

export class MarketFeedClient {
  private ws: WebSocket | null = null
  private reconnectTimer: number | null = null
  private closedByClient = false
  private pendingCommands: string[] = []
  private trackedSymbols = new Set<string>()

  constructor(
    private readonly url: string,
    private readonly handlers: ClientHandlers = {},
  ) {}

  connect() {
    this.closedByClient = false
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return
    this.handlers.onStatus?.('connecting')
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => {
      this.handlers.onStatus?.('open')
      this.flushPending()
      if (this.trackedSymbols.size) this.sendNow('snapshot_request', [...this.trackedSymbols])
    }
    this.ws.onerror = () => this.handlers.onStatus?.('error')
    this.ws.onclose = () => {
      this.handlers.onStatus?.('closed')
      if (!this.closedByClient) this.reconnectTimer = window.setTimeout(() => this.connect(), 1000)
    }
    this.ws.onmessage = (event) => this.handleMessage(event.data)
  }

  close() {
    this.closedByClient = true
    if (this.reconnectTimer !== null) { window.clearTimeout(this.reconnectTimer); this.reconnectTimer = null }
    this.ws?.close()
    this.ws = null
  }

  requestSnapshots(symbols: string[]) {
    symbols.forEach((s) => this.trackedSymbols.add(s))
    if (this.ws?.readyState === WebSocket.OPEN) this.sendNow('snapshot_request', symbols)
  }

  setVisible(symbols: string[]) {
    symbols.forEach((s) => this.trackedSymbols.add(s))
    this.sendCommand('visible_set', symbols)
  }

  private sendCommand(command: string, symbols: string[]) {
    const encoded = this.encode(command, symbols)
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(encoded)
    else { this.pendingCommands.push(encoded); this.connect() }
  }

  private sendNow(command: string, symbols: string[]) {
    this.ws?.send(this.encode(command, symbols))
  }

  private encode(command: string, symbols: string[]) {
    return JSON.stringify({
      schema_version: 1,
      protocol: 'terminal-message-v3',
      command,
      request_id: `${command}-${Date.now()}`,
      symbols,
    })
  }

  private flushPending() {
    if (this.ws?.readyState !== WebSocket.OPEN) return
    for (const command of this.pendingCommands.splice(0)) this.ws.send(command)
  }

  private handleMessage(raw: string) {
    const frame = JSON.parse(raw)
    const seq = Number(frame.seq || 0)
    if (frame.type === 'snapshot') this.handlers.onSnapshot?.(frame.symbol, frame.payload, seq)
    if (frame.type === 'delta') this.handlers.onDelta?.(frame.symbol, frame.payload, seq)
  }
}
```
> 注：`WsStatus` 与 `SnapshotPayload`/`DeltaPayload` 已在同文件 Task 2 定义，删除示例里的 `import type ... from './marketFeed'` 行（同文件不需要 import）。

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- marketFeed.spec`
Expected: PASS（2 cases）。

- [ ] **Step 5: Commit**

```bash
git add src/services/marketFeed.ts src/services/marketFeed.spec.ts
git commit -m "feat(frontend): transport reconnect re-request + frame.seq passthrough + connecting state"
```

---

## Task 9: ConnectionChip 组件

**Files:**
- Create: `src/components/ConnectionChip.vue`
- Test: `src/components/ConnectionChip.spec.ts`

- [ ] **Step 1: 写失败测试**

`src/components/ConnectionChip.spec.ts`：
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConnectionChip from './ConnectionChip.vue'

describe('ConnectionChip', () => {
  it('渲染状态文案与对应 class', () => {
    const w = mount(ConnectionChip, { props: { status: 'Connecting' } })
    expect(w.text()).toContain('Connecting')
    expect(w.find('.chip').classes()).toContain('connecting')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- ConnectionChip`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/components/ConnectionChip.vue`：
```vue
<script setup lang="ts">
const props = defineProps<{ status: 'Live' | 'Warm' | 'Closed' | 'Connecting' | 'Error' }>()
const cls = () => props.status.toLowerCase()
</script>

<template>
  <strong class="chip" :class="cls()">{{ status }}</strong>
</template>

<style scoped>
.chip { border-radius: 999px; padding: 6px 10px; background: #f1f4f9; color: #344054; font-size: 13px; }
.chip.live { background: #e9f8ef; color: #137333; }
.chip.error, .chip.closed { background: #fdecec; color: #b42318; }
.chip.connecting, .chip.warm { background: #f1f4f9; color: #344054; }
</style>
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- ConnectionChip`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/components/ConnectionChip.vue src/components/ConnectionChip.spec.ts
git commit -m "feat(frontend): ConnectionChip component"
```

---

## Task 10: Watchlist 组件（搜索 + 手输）

**Files:**
- Create: `src/components/Watchlist.vue`
- Test: `src/components/Watchlist.spec.ts`

- [ ] **Step 1: 写失败测试**

`src/components/Watchlist.spec.ts`：
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Watchlist from './Watchlist.vue'

const symbols = ['02723.HK', '02675.HK']
const names: Record<string, string> = { '02723.HK': '深演智能' }

describe('Watchlist', () => {
  it('点击标的 emit select', async () => {
    const w = mount(Watchlist, { props: { symbols, activeSymbol: '02723.HK', names } })
    await w.findAll('button.item')[1].trigger('click')
    expect(w.emitted('select')?.[0]).toEqual(['02675.HK'])
  })

  it('搜索过滤；回车手输新 symbol emit add', async () => {
    const w = mount(Watchlist, { props: { symbols, activeSymbol: '02723.HK', names } })
    const input = w.find('input')
    await input.setValue('00100.hk')
    await input.trigger('keyup.enter')
    expect(w.emitted('add')?.[0]).toEqual(['00100.HK'])
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- Watchlist`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/components/Watchlist.vue`：
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ symbols: string[]; activeSymbol: string; names: Record<string, string> }>()
const emit = defineEmits<{ (e: 'select', s: string): void; (e: 'add', s: string): void }>()

const search = ref('')
const filtered = computed(() => {
  const q = search.value.trim().toUpperCase()
  if (!q) return props.symbols
  return props.symbols.filter((s) => s.includes(q) || (props.names[s] || '').toUpperCase().includes(q))
})

function submit() {
  const q = search.value.trim().toUpperCase()
  if (q && !props.symbols.includes(q)) emit('add', q)
}
</script>

<template>
  <aside class="watchlist">
    <div class="search">
      <input v-model="search" type="search" placeholder="搜索 / 输入 symbol 回车" @keyup.enter="submit" />
    </div>
    <button
      v-for="symbol in filtered"
      :key="symbol"
      class="item"
      :class="{ active: symbol === activeSymbol }"
      @click="emit('select', symbol)"
    >
      <span>{{ names[symbol] || symbol }}</span>
      <small>{{ symbol }}</small>
    </button>
  </aside>
</template>

<style scoped>
.watchlist { border-right: 1px solid #d7dde5; background: #fff; padding: 12px; }
.search { margin-bottom: 12px; }
.search input { width: 100%; height: 36px; border: 1px solid #cfd7e2; border-radius: 6px; padding: 0 10px; }
.item { display: block; width: 100%; margin-bottom: 8px; padding: 9px; text-align: left; border: 1px solid #d7dde5; border-radius: 6px; background: #fff; }
.item.active { border-color: #0f62fe; box-shadow: inset 3px 0 0 #0f62fe; }
.item span, .item small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item small { color: #667085; }
@media (max-width: 900px) {
  .watchlist { display: flex; gap: 8px; overflow-x: auto; border-right: 0; border-bottom: 1px solid #d7dde5; }
  .search { flex: 0 0 100%; }
  .item { flex: 0 0 132px; }
}
</style>
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- Watchlist`
Expected: PASS（2 cases）。

- [ ] **Step 5: Commit**

```bash
git add src/components/Watchlist.vue src/components/Watchlist.spec.ts
git commit -m "feat(frontend): Watchlist with search + manual symbol entry"
```

---

## Task 11: SymbolHeader + QuoteStrip 组件

**Files:**
- Create: `src/components/SymbolHeader.vue`
- Create: `src/components/QuoteStrip.vue`

- [ ] **Step 1: 实现 SymbolHeader**

`src/components/SymbolHeader.vue`：
```vue
<script setup lang="ts">
import { formatDateTime } from '../utils/marketFormat'
defineProps<{ name: string; symbol: string; dataTime: string }>()
</script>

<template>
  <header class="topbar">
    <div>
      <h1>{{ name || symbol }}</h1>
      <span>{{ symbol }} · 数据时间 {{ formatDateTime(dataTime) }}</span>
    </div>
    <slot name="chip" />
  </header>
</template>

<style scoped>
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
h1 { margin: 0; font-size: 22px; }
.topbar span { color: #667085; font-size: 12px; }
</style>
```

- [ ] **Step 2: 实现 QuoteStrip**

`src/components/QuoteStrip.vue`：
```vue
<script setup lang="ts">
import { formatCompact, formatPrice, runtimeLabel } from '../utils/marketFormat'
import type { SnapshotInner } from '../services/marketFeed'
defineProps<{ snapshot?: SnapshotInner; runtimeState?: string }>()
</script>

<template>
  <section class="quote-strip">
    <div><span>Last</span><strong>{{ formatPrice(snapshot?.price) }}</strong></div>
    <div><span>Open</span><strong>{{ formatPrice(snapshot?.open) }}</strong></div>
    <div><span>High</span><strong>{{ formatPrice(snapshot?.high) }}</strong></div>
    <div><span>Low</span><strong>{{ formatPrice(snapshot?.low) }}</strong></div>
    <div><span>Volume</span><strong>{{ formatCompact(snapshot?.volume) }}</strong></div>
    <div><span>State</span><strong>{{ runtimeLabel(runtimeState) }}</strong></div>
  </section>
</template>

<style scoped>
.quote-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 1px; overflow: hidden; border: 1px solid #d7dde5; border-radius: 8px; background: #d7dde5; margin-bottom: 14px; }
.quote-strip div { background: #fff; padding: 12px; min-width: 0; }
.quote-strip span { color: #667085; font-size: 12px; }
.quote-strip strong { display: block; margin-top: 4px; font-size: 18px; }
@media (max-width: 900px) { .quote-strip { grid-template-columns: repeat(2, 1fr); } }
</style>
```

- [ ] **Step 3: 验证编译**

Run: `npx vue-tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 4: Commit**

```bash
git add src/components/SymbolHeader.vue src/components/QuoteStrip.vue
git commit -m "feat(frontend): SymbolHeader + QuoteStrip components"
```

---

## Task 12: BigTradeTable 组件

**Files:**
- Create: `src/components/BigTradeTable.vue`
- Test: `src/components/BigTradeTable.spec.ts`

- [ ] **Step 1: 写失败测试**

`src/components/BigTradeTable.spec.ts`：
```ts
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
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- BigTradeTable`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/components/BigTradeTable.vue`：
```vue
<script setup lang="ts">
import { formatCompact, formatDateTime, formatPrice } from '../utils/marketFormat'
import type { TradeAlert } from '../services/marketFeed'
defineProps<{ alerts: TradeAlert[] }>()
</script>

<template>
  <section class="panel">
    <div class="panel-title"><h2>大额交易</h2><span>{{ alerts.length }}</span></div>
    <table>
      <thead><tr><th>时间</th><th>方向</th><th>价格</th><th>数量</th></tr></thead>
      <tbody>
        <tr v-for="a in alerts" :key="a.id">
          <td>{{ formatDateTime(a.timestamp) }}</td>
          <td>{{ a.side }}</td>
          <td>{{ formatPrice(a.price) }}</td>
          <td>{{ formatCompact(a.volume) }}</td>
        </tr>
        <tr v-if="!alerts.length"><td colspan="4">No current-day alerts</td></tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.panel { border: 1px solid #d7dde5; border-radius: 8px; background: #fff; padding: 14px; min-width: 0; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.panel-title span { color: #667085; font-size: 12px; }
h2 { margin: 0; font-size: 15px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e3e8ef; padding: 8px 6px; text-align: left; }
th { color: #667085; font-weight: 600; }
</style>
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- BigTradeTable`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/components/BigTradeTable.vue src/components/BigTradeTable.spec.ts
git commit -m "feat(frontend): BigTradeTable component with empty state"
```

---

## Task 13: BrokerCell + BrokerQueueRow 组件

**Files:**
- Create: `src/components/BrokerCell.vue`
- Create: `src/components/BrokerQueueRow.vue`

- [ ] **Step 1: 实现 BrokerCell**

`src/components/BrokerCell.vue`：
```vue
<script setup lang="ts">
import { formatCompact } from '../utils/marketFormat'
import type { BrokerCell } from '../services/marketFeed'
defineProps<{ broker: BrokerCell }>()
</script>

<template>
  <span class="cell"><b>{{ broker.displayName }}</b><em>{{ formatCompact(broker.volume) }}</em></span>
</template>

<style scoped>
.cell { display: inline-flex; gap: 4px; align-items: baseline; padding: 2px 6px; margin: 2px; border: 1px solid #e3e8ef; border-radius: 4px; font-size: 12px; }
.cell em { color: #667085; font-style: normal; }
</style>
```

- [ ] **Step 2: 实现 BrokerQueueRow**

`src/components/BrokerQueueRow.vue`（展开/收起：默认显示前 3 个 cell，超出可展开；列宽用固定 grid 轨道，展开不影响两列宽度）：
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { formatCompact, formatPrice } from '../utils/marketFormat'
import BrokerCell from './BrokerCell.vue'
import type { QueueLevel } from '../services/marketFeed'

const props = defineProps<{ level: QueueLevel; expanded: boolean }>()
const emit = defineEmits<{ (e: 'toggle'): void }>()
const VISIBLE = 3
const shown = computed(() => (props.expanded ? props.level.brokers : props.level.brokers.slice(0, VISIBLE)))
const overflow = computed(() => Math.max(0, props.level.brokers.length - VISIBLE))
</script>

<template>
  <li class="row">
    <div class="head">
      <span class="pos">{{ level.position }}档</span>
      <strong>{{ formatPrice(level.price) }}</strong>
      <em>{{ formatCompact(level.volume) }}</em>
      <small>{{ level.brokerCount }} 家</small>
    </div>
    <div class="cells">
      <BrokerCell v-for="b in shown" :key="b.brokerCode + b.volume" :broker="b" />
      <button v-if="overflow" class="more" @click="emit('toggle')">{{ expanded ? '收起' : `+${overflow}` }}</button>
    </div>
  </li>
</template>

<style scoped>
.row { list-style: none; border-bottom: 1px solid #eef2f6; padding: 6px 0; }
/* 固定档头四列轨道宽度：展开/收起 cells 不改变列宽 */
.head { display: grid; grid-template-columns: 48px 1fr 72px 48px; gap: 8px; align-items: center; font-size: 13px; }
.head em { color: #344054; font-style: normal; text-align: right; }
.head small { color: #667085; text-align: right; }
.cells { margin-top: 4px; }
.more { padding: 2px 6px; margin: 2px; border: 1px solid #cfd7e2; border-radius: 4px; background: #f7f9fc; font-size: 12px; cursor: pointer; }
</style>
```

- [ ] **Step 3: 验证编译**

Run: `npx vue-tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 4: Commit**

```bash
git add src/components/BrokerCell.vue src/components/BrokerQueueRow.vue
git commit -m "feat(frontend): BrokerCell + BrokerQueueRow with expand/collapse"
```

---

## Task 14: BrokerQueue 组件（档位切换 + 布局稳定）（TDD）

**Files:**
- Create: `src/components/BrokerQueue.vue`
- Test: `src/components/BrokerQueue.spec.ts`

- [ ] **Step 1: 写失败测试**

`src/components/BrokerQueue.spec.ts`：
```ts
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
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- BrokerQueue`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/components/BrokerQueue.vue`（父级已用 `store.visibleLevels` 把 ask/bid 过滤好传入；本组件负责档位 toggle UI、两列布局、展开态分发）：
```vue
<script setup lang="ts">
import BrokerQueueRow from './BrokerQueueRow.vue'
import type { Gear, QueueLevel } from '../services/marketFeed'

const props = defineProps<{
  ask: QueueLevel[]
  bid: QueueLevel[]
  gear: Gear
  expandedCells: Set<string>
  symbol: string
  fallback?: boolean
  sourceDate?: string
}>()
const emit = defineEmits<{ (e: 'setGear', g: Gear): void; (e: 'toggleCell', key: string): void }>()

const GEARS: Gear[] = [10, 100, 1000]
function key(side: string, position: number) { return `${props.symbol}|${side}|${position}` }
</script>

<template>
  <section class="panel queue-panel">
    <div class="panel-title">
      <h2>Broker Queue</h2>
      <div class="meta">
        <span v-if="fallback" class="fallback">Fallback {{ sourceDate }}</span>
        <div class="gears">
          <button v-for="g in GEARS" :key="g" class="gear" :class="{ active: g === gear }" @click="emit('setGear', g)">{{ g }}</button>
        </div>
      </div>
    </div>
    <div class="queues">
      <div>
        <h3>买盘 Bid</h3>
        <ol>
          <BrokerQueueRow v-for="l in bid" :key="l.id" :level="l" :expanded="expandedCells.has(key('bid', l.position))" @toggle="emit('toggleCell', key('bid', l.position))" />
          <li v-if="!bid.length" class="empty">No bid levels</li>
        </ol>
      </div>
      <div>
        <h3>卖盘 Ask</h3>
        <ol>
          <BrokerQueueRow v-for="l in ask" :key="l.id" :level="l" :expanded="expandedCells.has(key('ask', l.position))" @toggle="emit('toggleCell', key('ask', l.position))" />
          <li v-if="!ask.length" class="empty">No ask levels</li>
        </ol>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel { border: 1px solid #d7dde5; border-radius: 8px; background: #fff; padding: 14px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.meta { display: flex; align-items: center; gap: 10px; }
.fallback { color: #b54708; font-size: 12px; }
.gears { display: inline-flex; border: 1px solid #cfd7e2; border-radius: 6px; overflow: hidden; }
.gear { padding: 4px 10px; border: 0; background: #fff; font-size: 12px; cursor: pointer; }
.gear.active { background: #0f62fe; color: #fff; }
h2 { margin: 0; font-size: 15px; }
h3 { margin: 0 0 8px; font-size: 13px; }
ol { list-style: none; margin: 0; padding: 0; }
.empty { color: #667085; font-size: 12px; padding: 8px 0; }
/* 买卖各占固定一列，列宽不随档内展开变化 */
.queues { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) {
  .queues { grid-template-columns: 1fr; }
  .queues > div { max-height: 360px; overflow-y: auto; }  /* 保证买卖各 >=10 档可滚动 */
}
</style>
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- BrokerQueue`
Expected: PASS（3 cases）。

- [ ] **Step 5: Commit**

```bash
git add src/components/BrokerQueue.vue src/components/BrokerQueue.spec.ts
git commit -m "feat(frontend): BrokerQueue gear toggle + stable two-column layout + fallback badge"
```

---

## Task 15: ChartPanel 组件（lightweight-charts 双 pane）

**Files:**
- Create: `src/components/ChartPanel.vue`
- Test: `src/components/ChartPanel.spec.ts`

> lightweight-charts v5 API：`chart.addSeries(CandlestickSeries, opts)`；成交量直方图放第二 pane：`chart.addSeries(HistogramSeries, opts, 1)`。实现前用 context7 查 `lightweight-charts` 最新版确认 series/pane 调用签名。

- [ ] **Step 1: 写失败测试（mock 图表库）**

`src/components/ChartPanel.spec.ts`：
```ts
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
```

- [ ] **Step 2: 运行确认失败**

Run: `npm run test -- ChartPanel`
Expected: FAIL。

- [ ] **Step 3: 实现**

`src/components/ChartPanel.vue`：
```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createChart, CandlestickSeries, HistogramSeries, type IChartApi, type ISeriesApi } from 'lightweight-charts'
import { toCandles, toVolumes } from '../utils/chartData'
import { formatDateTime } from '../utils/marketFormat'
import type { MarketBar } from '../services/marketFeed'

const props = defineProps<{ bars: MarketBar[]; symbol: string; name: string; dataTime: string }>()

const host = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null

function build() {
  if (!host.value) return
  chart = createChart(host.value, { autoSize: true, layout: { background: { color: '#fff' }, textColor: '#344054' } })
  candleSeries = chart.addSeries(CandlestickSeries, { upColor: '#0f62fe', downColor: '#da1e28', borderVisible: false, wickUpColor: '#0f62fe', wickDownColor: '#da1e28' })
  // 成交量放第二个 pane（paneIndex=1），结构上与 K 线分离、绝不重叠
  volumeSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } }, 1)
  render()
}

function render() {
  if (!candleSeries || !volumeSeries) return
  candleSeries.setData(toCandles(props.bars) as never)
  volumeSeries.setData(toVolumes(props.bars) as never)
  chart?.timeScale().fitContent()
}

function dispose() {
  chart?.remove()
  chart = null; candleSeries = null; volumeSeries = null
}

onMounted(build)
onBeforeUnmount(dispose)
// 切 symbol：重建（防 series/canvas 泄漏）；同 symbol 仅更新数据
watch(() => props.symbol, () => { dispose(); build() })
watch(() => props.bars, render, { deep: false })
</script>

<template>
  <section class="panel chart-panel">
    <div class="panel-title">
      <h2>{{ name || symbol }} · 分钟</h2>
      <span>{{ formatDateTime(dataTime) }}</span>
    </div>
    <div v-show="bars.length" ref="host" class="chart-host"></div>
    <div v-if="!bars.length" class="empty">Awaiting data…</div>
  </section>
</template>

<style scoped>
.panel { border: 1px solid #d7dde5; border-radius: 8px; background: #fff; padding: 14px; min-width: 0; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.panel-title span { color: #667085; font-size: 12px; }
h2 { margin: 0; font-size: 15px; }
.chart-host { height: 340px; }
.empty { height: 340px; display: grid; place-items: center; color: #667085; }
@media (max-width: 900px) { .chart-host, .empty { height: 280px; } }
</style>
```

- [ ] **Step 4: 运行确认通过**

Run: `npm run test -- ChartPanel`
Expected: PASS（2 cases）。

- [ ] **Step 5: Commit**

```bash
git add src/components/ChartPanel.vue src/components/ChartPanel.spec.ts
git commit -m "feat(frontend): ChartPanel candlestick + volume pane (epoch time, dispose on symbol switch)"
```

---

## Task 16: App.vue 薄壳编排 + 响应式

**Files:**
- Modify: `src/App.vue`（整体替换）

- [ ] **Step 1: 替换 App.vue**

`src/App.vue`：
```vue
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useMarketStore } from './stores/marketStore'
import { MarketFeedClient } from './services/marketFeed'
import type { Gear } from './services/marketFeed'
import Watchlist from './components/Watchlist.vue'
import ConnectionChip from './components/ConnectionChip.vue'
import SymbolHeader from './components/SymbolHeader.vue'
import QuoteStrip from './components/QuoteStrip.vue'
import ChartPanel from './components/ChartPanel.vue'
import BigTradeTable from './components/BigTradeTable.vue'
import BrokerQueue from './components/BrokerQueue.vue'

const SYMBOLS = ['02723.HK', '02675.HK', '00100.HK', '02513.HK', '06082.HK']
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:9021/ws'

const store = useMarketStore()
if (!store.activeSymbol) store.setActiveSymbol(SYMBOLS[0])

const names = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const s of SYMBOLS) out[s] = store.records[s]?.snapshot.name || ''
  return out
})
const active = computed(() => store.activeRecord)
const ask = computed(() => store.visibleLevels('ask'))
const bid = computed(() => store.visibleLevels('bid'))

let client: MarketFeedClient | null = null

onMounted(() => {
  client = new MarketFeedClient(WS_URL, {
    onStatus: (s) => store.setConnectionStatus(s),
    onSnapshot: (symbol, payload, seq) => store.setSnapshot(symbol, payload, seq),
    onDelta: (symbol, payload, seq) => store.applyDelta(symbol, payload, seq),
  })
  client.connect()
  client.requestSnapshots(SYMBOLS)
})
onBeforeUnmount(() => client?.close())

function onAdd(symbol: string) {
  store.setActiveSymbol(symbol)
  client?.requestSnapshots([symbol])
}
function setGear(g: Gear) { store.setGear(g) }
function toggleCell(key: string) { store.toggleCell(key) }
</script>

<template>
  <main class="terminal">
    <Watchlist :symbols="SYMBOLS" :active-symbol="store.activeSymbol" :names="names"
      @select="store.setActiveSymbol" @add="onAdd" />
    <section class="workspace">
      <SymbolHeader :name="active?.snapshot.name || ''" :symbol="store.activeSymbol" :data-time="store.activeDataTime">
        <template #chip><ConnectionChip :status="store.displayStatus" /></template>
      </SymbolHeader>
      <QuoteStrip :snapshot="active?.snapshot" :runtime-state="active?.freshness.runtime_state" />
      <section class="market-grid">
        <ChartPanel :bars="active?.minuteBars || []" :symbol="store.activeSymbol"
          :name="active?.snapshot.name || ''" :data-time="store.activeDataTime" />
        <BigTradeTable :alerts="store.currentAlerts" />
        <BrokerQueue class="full" :ask="ask" :bid="bid" :gear="store.brokerQueueGear"
          :expanded-cells="store.expandedCells" :symbol="store.activeSymbol"
          :fallback="active?.brokerQueue.fallback" :source-date="active?.brokerQueue.sourceDate"
          @set-gear="setGear" @toggle-cell="toggleCell" />
      </section>
    </section>
  </main>
</template>

<style scoped>
.terminal { display: grid; grid-template-columns: 224px minmax(0, 1fr); min-height: 100vh; font-family: Inter, system-ui, sans-serif; color: #18212f; background: #f7f9fc; }
.workspace { min-width: 0; padding: 16px; }
.market-grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(300px, 0.7fr); gap: 14px; }
.market-grid > .full { grid-column: 1 / -1; }
@media (max-width: 900px) {
  .terminal { grid-template-columns: 1fr; }
  .market-grid { grid-template-columns: 1fr; }
}
</style>
```

- [ ] **Step 2: 类型与构建验证**

Run: `npx vue-tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 3: 全量测试**

Run: `npm run test`
Expected: 所有单测 PASS。

- [ ] **Step 4: 手动联调（仓库根另开终端 `make serve`）**

Run: `npm run dev` → 浏览器开 `http://127.0.0.1:5176`
Expected: 5 标的可切换；K 线+成交量不重叠；大额交易自动追加；broker queue 10/100/1000 切换、展开/收起列宽不变；断开 mock feed 再起，页面自动恢复（无需刷新）。

- [ ] **Step 5: Commit**

```bash
git add src/App.vue
git commit -m "feat(frontend): thin App shell wiring store + components + responsive layout"
```

---

## Task 17: README + 交付文档 + 收尾验证

**Files:**
- Modify: `frontend-project/README.md`

- [ ] **Step 1: 更新 README**

在 `frontend-project/README.md` 增补以下小节（保留原有 Run 段）：
```markdown
## 组件结构
App.vue（薄壳）→ Watchlist / SymbolHeader+ConnectionChip / QuoteStrip / ChartPanel / BigTradeTable / BrokerQueue→BrokerQueueRow→BrokerCell。
状态集中在 Pinia `stores/marketStore.ts`；业务逻辑为 `utils/*` 与 `stores/marketDelta.ts` 纯函数。

## 状态管理与重连
- per-symbol record（snapshot/minuteBars/alerts/brokerQueue/freshness/maxSeq）。
- `frame.seq` 透传，`seq<=maxSeq` 的 delta 丢弃；snapshot 的 seq=max(1,state.seq) 不重置。
- `MarketFeedClient` 维护 trackedSymbols，重连后自动重发 snapshot_request（无需手动刷新）；固定 1000ms 重连。

## Broker Queue 过滤逻辑
- 10/100/1000 = 前端按原始 position 过滤：`position <= gear`，绝不重编号。
- 每档 volume = 档内各 broker volume 之和，跨档位切换不变；队列整张覆盖非累加。
- 展开/收起用固定 grid 轨道宽度，不改变买卖两列宽度；展开态 key=`symbol|side|position`。

## 移动端
- <900px：纵向堆叠；K 线/成交量分两个 pane 不重叠；broker queue 买卖纵向、容器可滚动保证各 >=10 档。

## 测试
`npm run test`：纯函数（档位过滤/volume 合计/alert 当日过滤+去重/bar upsert/图表转换）+ store（覆盖语义/seq 去重/切日/getter）+ 传输（重连重拉/seq 透传）+ 组件契约。

## 已知限制 / 下一步
- jsdom 不渲染 canvas/真实布局：列宽稳定为 grid 轨道契约级断言；像素级重叠/媒体查询留 Playwright（下一步）。
- 暗盘/基本面等不在 mock-feed 数据范围内。
```

- [ ] **Step 2: PR 描述要点（写入 PR body，非代码）**

PR 说明覆盖：运行方式、组件结构、WS 状态/重连、broker queue 过滤逻辑、移动端、测试、已知限制；tradeoff：为何 Pinia、为何前端过滤档位（服务端发全量）、为何固定重连不退避（YAGNI）、为何 lightweight-charts。

- [ ] **Step 3: 收尾全量验证**

Run:
```bash
npm run test
npm run build   # 含 vue-tsc --noEmit
```
Expected: 测试全 PASS；构建成功无类型错误。

- [ ] **Step 4: Commit**

```bash
git add frontend-project/README.md
git commit -m "docs(frontend): README structure/state/broker-queue/mobile/tests/limitations"
```

---

## Self-Review（已对照 spec）

- **Spec 覆盖**：§1 依赖→T1；§2 组件树→T9–16；§3 store→T7；§4 传输/seq/重连→T2/T8；§5 broker queue→T3/T13/T14；§6 effective-day→T4/T7；§7 图表→T6/T15；§8 chip/响应式/空态→T7/T9/T11/T16；§9 测试矩阵→T3–8/T14；§10 沟通→T17；§11 rubric 全覆盖。
- **测试矩阵对照**：测1/2→T3；测3/7→T7；测4/5→T4(+T7)；测6→T8；测8→T14(列宽 grid 轨道契约) + jsdom 限制已注；测9→T14(mobile 滚动) + Playwright 列为下一步。
- **类型一致性**：`Gear`/`WsStatus`/`BrokerQueue`/`BrokerCell`/`TradeAlert.sourceDate`/`SnapshotInner` 在 T2 定义，后续 T3–16 一致引用；store getter `currentAlerts`/`displayStatus`/`activeDataTime` 与 App.vue 调用一致；`visibleLevels(side)` 为 action（非 getter，因带参），App.vue 以 `store.visibleLevels('ask')` 调用一致。
- **无占位符**：每个代码步骤含可运行代码与期望输出。
- 唯一外部待确认项：lightweight-charts v5 的 `addSeries`/pane 签名（T15 已注明实现前用 context7 核对）。
```

---

## 进度更新（2026-06-17 完成）

实施通过 subagent-driven 流程执行：17 个计划任务归并为 9 个实现单元，每单元两阶段评审（spec 合规 + 代码质量），共 24 个 commit。

- 分支：`feat/frontend-market-terminal`（保持未合并、未 push）。
- 单元：A 配置/类型、B 纯函数、C Pinia store、D 传输层、E 叶子组件、F BrokerQueue、G ChartPanel、H App 集成、I README/收尾 —— 全部 DONE，评审全过。
- 验证门：`npm run test` 48/48（13 文件）；`npx vue-tsc --noEmit` clean；`npm run build` 成功。
- 整体终审（opus）：**SHIP IT**，六条红线全部明确不存在，估分 99/100（唯一扣分点：移动端像素级回归留待 Playwright，属已声明限制）。
- 评审吸收的修正：seq 在帧外层且 snapshot 不重置 maxSeq；alert 双校验 + 空 effective-day 返回空；broker queue 防御性整张拷贝；档位过滤 `position <= gear`；切日按新日过滤 alerts；BrokerCell key 用索引（防撞键丢 cell）；图表 `UTCTimestamp` 品牌类型去 `as never` + 懒构建 + pane 分离断言；`setVisible` 不进 trackedSymbols；`JSON.parse` 防护。

### 待办（未在自动化流程内完成）
- **浏览器实跑联调**（计划 T16 手动步骤）：根目录 `make serve` 起 mock-feed + `npm run dev`，浏览器验证实时渲染/重连/档位切换。静态门（build + 单测 + vue-tsc）已全绿，但未做真实渲染端到端验证。
