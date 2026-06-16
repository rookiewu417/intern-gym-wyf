# 设计 Spec：Market Terminal Lite 前端（锁定满分 rubric）

- 日期：2026-06-16
- 项目：`frontend-project/`（Market Terminal Lite）
- 数据源：`mock-feed` WebSocket，`ws://127.0.0.1:9021/ws`
- 协议：`terminal-message-v3`，`schema_version: 1`
- 状态：已通过用户口头评审，待文档评审 → writing-plans

> 本 spec 经一次多 agent ground-truth 调查（精读 `mock-feed/src/market_mock_feed/server.py`、现有前端骨架、`docs/api-contract.md` 等）+ 三路对抗式评审（rubric 覆盖 / 契约正确性 / 完备性与 YAGNI）综合而成。所有契约关键断言均以源码为准。

---

## 0. 目标与范围

实现一个单页实时行情终端，连接 `mock-feed`，展示默认 5 支港股（`02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK`）的实时回放行情。前端**只消费** `snapshot`/`delta`，不触碰数据文件或 SDK。

**范围 = 命中每一条评分项 + 规避每一条红线，不做计分外功能（YAGNI）。** 每个设计决策都映射到 rubric / 红线（见 §11）。

明确**不做**（YAGNI，避免范围蔓延）：
- 指数退避重连（固定 1000ms 即可）。
- 客户端周期性 `health_request` 轮询（服务端主动发 heartbeat）。
- CCASS 持仓面板、主题切换等加分项（rubric 满分 100，加分项不计入）。
- Playwright 视觉回归（仅在 README「下一步」中列出，不实做）。

---

## 1. 技术栈与依赖

| 用途 | 选型 | 说明 |
|---|---|---|
| 框架 | Vue 3 `<script setup>` + TypeScript + Vite | 沿用现有脚手架 |
| 状态管理 | **Pinia** | 集中 per-symbol 状态、连接生命周期、UI 偏好（gear、展开态） |
| 图表 | **lightweight-charts**（最新稳定版） | 蜡烛 + 成交量直方图，金融场景、canvas 高性能；约 420 根/标的 |
| 单元/组件测试 | **Vitest + @vue/test-utils + jsdom** | 纯函数单测 + 组件契约测 |
| 配置 | `.env`（`VITE_WS_URL`）+ `.env.example` | 避免硬编码 WS 地址 |

**新增依赖**：`pinia`、`lightweight-charts`（deps）；`@vue/test-utils`、`jsdom`（devDeps）。`vitest.config.ts` 设 `environment: 'jsdom'`。

**保留不重写**：`services/marketFeed.ts`、`utils/marketFormat.ts`（仅扩展）。

---

## 2. 架构与组件树

`App.vue` 退化为薄壳（布局编排 + 挂载 client + 订阅 store）。业务逻辑全部下沉到 store / 纯函数 / 子组件。

```
src/
  services/
    marketFeed.ts          # WS 传输层（扩展：trackedSymbols + 透传 frame.seq + 'connecting' 态）
  stores/
    marketStore.ts         # Pinia：records / wsStatus / activeSymbol / gear / expandedCells
    marketDelta.ts         # 纯函数：applyMinuteBar / applyTradeTick / applyBrokerQueue / effective-day reset
  utils/
    marketFormat.ts        # 已有：formatPrice/formatCompact/formatDateTime/runtimeLabel
    brokerQueueFilter.ts   # 纯函数：filterLevelsByGear / levelTotalVolume
    alertFilter.ts         # 纯函数：filterAlertsByTradeDate / dedupeAlertsById
  components/
    Watchlist.vue          # 5 标的 + 搜索/手输 symbol + 切换（不串状态）
    ConnectionChip.vue     # Live / Warm / Closed / Connecting
    SymbolHeader.vue       # 中文名 + 代码 + 数据时间
    QuoteStrip.vue         # last/open/high/low/volume/state
    ChartPanel.vue         # lightweight-charts：价格蜡烛 pane + 成交量直方图 pane
    BigTradeTable.vue      # alerts：倒序 / 去重 / 仅当日 / 自动追加
    BrokerQueue.vue        # 10/100/1000 toggle + 买卖两列容器 + fallback 徽标
    BrokerQueueRow.vue     # 单档：position / price / total volume / brokerCount
    BrokerCell.vue         # 单 broker：短名 + 量；溢出展开/收起
  App.vue                  # 薄壳
```

每个组件单一职责、1–3 props + 1–2 emits，可不读内部实现即理解，可独立测试。

### 组件职责 / 接口

| 组件 | props | emits | 职责 |
|---|---|---|---|
| `Watchlist` | `symbols`, `activeSymbol`, `records` | `select(symbol)`, `add(symbol)` | 列表 + 搜索/手输 + 高亮当前 |
| `ConnectionChip` | `status`(显示文案) | — | 渲染状态 chip + 配色 |
| `SymbolHeader` | `name`, `symbol`, `dataTime` | — | 中文名 + 代码 + 数据时间 |
| `QuoteStrip` | `snapshot` | — | 6 格行情摘要 |
| `ChartPanel` | `bars`, `symbol`, `dataTime`, `name` | — | 建/更新/销毁 lightweight-charts；价格+成交量双 pane |
| `BigTradeTable` | `alerts` | — | 渲染当日 alerts（已在 getter 过滤好） |
| `BrokerQueue` | `ask`, `bid`, `gear`, `fallback`, `sourceDate`, `expandedCells` | `setGear(g)`, `toggleCell(key)` | 档位 toggle + 两列布局 + 徽标 |
| `BrokerQueueRow` | `level`, `expanded` | `toggle()` | 单档汇总 + 内嵌 cells |
| `BrokerCell` | `broker` | — | 单 broker 短名 + 量 |

---

## 3. 状态管理（Pinia `marketStore`）

### State
```ts
type RuntimeWs = 'connecting' | 'open' | 'closed' | 'error'
interface SymbolRecord {
  snapshot: SnapshotInner      // symbol/name/price/open/high/low/volume/updatedAt/tradeDate
  minuteBars: MarketBar[]
  alerts: TradeAlert[]
  brokerQueue: BrokerQueue     // { ask, bid, sourceDate?, historical?, fallback? }
  freshness: { runtime_state?: string; effective_day?: string; source_dates?: Record<string,string> }
  maxSeq: number               // 该 symbol 已应用的最大 seq
}
state = {
  records: Record<string, SymbolRecord>,
  activeSymbol: string,
  wsStatus: RuntimeWs,
  brokerQueueGear: 10 | 100 | 1000,   // 默认 10
  expandedCells: Set<string>,         // key = `${symbol}|${side}|${position}`
}
```

### Actions
- `setSnapshot(symbol, payload, seq)`：**整体覆盖** `records[symbol]`；`maxSeq = seq`（注意：seq 取自帧外层，见 §4）。
- `applyDelta(symbol, payload, seq)`：seq 守卫——`if (seq != null && seq <= records[symbol].maxSeq) return`；否则按 `delta_type` 调对应纯函数应用，再 `maxSeq = seq`。
- `setConnectionStatus(s: RuntimeWs)`。
- `setGear(g)` / `toggleCell(key)` / `setActiveSymbol(symbol)`。

### Getters
- `activeRecord`。
- `visibleLevels(side)`：`filterLevelsByGear(record.brokerQueue[side], brokerQueueGear)`。
- `currentAlerts`：`dedupeAlertsById(filterAlertsByTradeDate(alerts, effectiveDay))` → 倒序 → 前 8。
- `displayStatus`：见 §8 chip 映射。
- `activeDataTime`：`max(snapshot.updatedAt, lastBar.timestamp)`。

### 纯函数模块
`marketDelta.ts`（delta 应用 + effective-day）、`brokerQueueFilter.ts`、`alertFilter.ts` 全部 mock-free、可独立单测；store 仅做编排与响应式封装。

---

## 4. 数据流与 WebSocket 契约

### 帧信封
```jsonc
{ "schema_version":1, "protocol":"terminal-message-v3",
  "type":"hello|heartbeat|ack|snapshot|delta|error",
  "symbol":"02723.HK",   // 仅 snapshot/delta
  "seq": 2,              // 仅 snapshot/delta；控制帧无 seq
  "payload": { ... } }
```

**关键修正 1 — `seq` 在帧外层，不在 payload。** 现有 `MarketFeedClient.handleMessage` 只把 `frame.payload` 交给 handler，丢了 `frame.seq`。必须改为把 `frame.seq` 一并透传：`onSnapshot(symbol, payload, seq)` / `onDelta(symbol, payload, seq)`。
（依据：`server.py` 仅当 `seq>0` 时把 `seq` 放进帧；snapshot/delta 必带。）

**关键修正 2 — snapshot 的 seq 不重置为 0。** 服务端 `snapshot` 的 `seq = max(1, state.seq)`：重连后若服务端 seq 已是 100，snapshot 带 `seq=100`。故 `setSnapshot` 必须 `maxSeq = frame.seq`（**不是 0**），后续只接受 `seq > maxSeq` 的 delta。

**seq 过滤位置**：放在 **store 的 `applyDelta`**（应用层业务逻辑）；`MarketFeedClient` 保持纯传输层。

### delta 三型（`payload.delta_type`）
| delta_type | payload 字段 | store 行为 |
|---|---|---|
| `minute_bar` | `minute_bar` | 按 timestamp upsert 进 minuteBars；更新 price/updatedAt/tradeDate |
| `trade_tick` | `tick`, `alert`（**alert 可能为 null**） | 更新 price/updatedAt；alert 非 null 则按 id 去重追加（**当日过滤统一在 `currentAlerts` getter 处理，insert 不做日期过滤**，单点真相） |
| `broker_queue` | `broker_queue` | **整张覆盖** brokerQueue |

### 重连（规避「需手动刷新」红线）
- `MarketFeedClient` 维护 `trackedSymbols: Set<string>`；`requestSnapshots()` / `setVisible()` 调用时累加。
- `onopen`（含重连后）先 `flushPending()`，再**自动重发 `snapshot_request(Array.from(trackedSymbols))`**。
- 固定 1000ms 重连，**不做指数退避**（YAGNI）。
- `closedByClient` 区分用户主动关闭与网络断开（主动关闭不重连）。
- 暴露 `'connecting'` 态（初次连接 / 重连等待期），供 chip 显示。

---

## 5. Broker Queue 语义（核心评分点）

### 档形态（以 `server.py:358-391` 为准）
```ts
interface QueueLevel {
  id: string; side: 'ask' | 'bid';
  position: number; gear: number;   // gear === position（server 同值）
  price: number; volume: number;    // volume === Σ brokers[].volume
  brokerCount: number;
  brokers: Array<{ brokerCode: string; displayName: string; volume: number }>
}
```
- `displayName`：短名；`brokerCode === '0'` 显示「未披露」。
- `position` 可稀疏/非连续，**不假设连续**。

### 10/100/1000 档切换 = 前端按原始档位过滤
```ts
// brokerQueueFilter.ts
function filterLevelsByGear(levels: QueueLevel[], gear: 10|100|1000): QueueLevel[] {
  return levels.filter(l => l.position <= gear)   // 注意：阈值就是 gear 本身
}
```
**关键修正 3 — 阈值是 `position <= gear`，不是 `gear/10`。**
例 `position = [1,3,5,11,13,15]`：
- gear=10 → `[1,3,5]`（≤10）
- gear=100 → 全部（≤100）
- **显示原始 position 数字，绝不重编号/归一化。**

### 不变量
- 每档 `volume === Σ brokers[].volume`，**跨档位切换不变**（10/100/1000 只决定显示哪些档，不改变档内聚合）。`levelTotalVolume(level)` 纯函数 + 断言测试。
- **整张覆盖**：`broker_queue` 到达直接替换上一张，绝不累加/merge。store action 注释说明 + 单测验证「应用更少档的 delta 后旧档消失」。

### 展开/收起 + 布局稳定
- 单档 broker cells 溢出时可展开；展开态 key = `${symbol}|${side}|${position}`（position 唯一、避免 price 精度问题）。
- **固定 CSS grid 轨道宽度 / 预留展开区**：展开/收起**不得改变买卖两列宽度**（测试点）。

### fallback 徽标
- `sourceDate` 为 `YYYYMMDD`；当 `sourceDate` 非空且 `!= effectiveDay` 时，`fallback === historical === true`。
- UI 显示「Fallback {sourceDate}」。fallback 队列**保留展示**（不丢），依赖徽标提示用户。

---

## 6. Effective-day 隔离

- snapshot 整体覆盖即天然按当日隔离。
- **切日**：当 `snapshot.tradeDate`（或新到 minute_bar 的交易日）变化为新 effective day 时，丢弃旧日 minuteBars / alerts。
- **alert 进入当前视图的条件**：`alert.tradeDate === effectiveDay && alert.sourceDate === effectiveDay`（**双校验**，防历史 alert 串日）。
- minute_bar 服务端已按 `effective_day` 过滤（`server.py:233-234`），客户端再做防御性校验。
- runtime_state：服务端初始 `WARM`，首个 delta 后 `LIVE`（`server.py` empty_snapshot / touch_freshness）。

---

## 7. 图表（lightweight-charts）

- **单 chart 双 pane**：价格蜡烛 pane + 成交量直方图 pane，各给显式高度——**结构上杜绝 K 线/成交量重叠**（桌面/移动统一方案，移动端只调整高度比例，比「移动切两个 chart 实例」更稳健）。
- **关键修正 4 — `time` 字段用 UTC epoch 秒**（分钟级 bar），**不能用 date-only**——date-only 会把一整天的分钟 bar 塌成一根蜡烛。
- 颜色：涨 `#0f62fe`（与现有设计一致）/ 跌 `#da1e28`。
- 生命周期：`onMounted` 建 chart；bars 变化时单根用 `.update()`、批量/切标的用 `.setData()`；**`onUnmounted` 与切 symbol 时 `chart.remove()`** 防内存/series 泄漏。
- **无未来函数**：只渲染时间 ≤ 最新事件时间的 bar，不构造未来 bar。
- 左上中文名 + 数据时间（`activeDataTime`）。空态显示「Awaiting data…」。

---

## 8. 状态 chip / 响应式 / 空错态

### chip 优先级映射
```
wsStatus !== 'open' :
  'connecting' -> "Connecting"
  'closed'     -> "Closed"
  'error'      -> "Error"
wsStatus === 'open' : 按 freshness.runtime_state
  LIVE -> "Live" | WARM -> "Warm" | CLOSED -> "Closed"
```
即：未连上时网络态优先，连上后才看 runtime_state。

### 响应式（断点 900px）
- 桌面：左 watchlist + 右工作区栅格。
- 移动：纵向堆叠；ChartPanel 双 pane 不重叠；broker queue 买卖**纵向堆叠**、容器固定高 + `overflow-y:auto`，**保证买卖各 ≥10 档可见**；watchlist 收成可横滑 tab 条，释放纵向空间。

### 空态 / 错态（每面板）
- 首屏未收到 snapshot：各面板「Awaiting data…」。
- 连接断开：chip 显示 + 面板提示「Connection lost」。
- broker queue 无档：「No ask/bid levels」。
- alerts 无当日：「No current-day alerts」。

---

## 9. 测试矩阵（Vitest + @vue/test-utils）

| # | 验收点 / 红线 | 测试文件 | 断言 |
|---|---|---|---|
| 1 | 档位过滤不重排/不重编号 | `brokerQueueFilter.test.ts` | `[1,3,5,11,13,15]`→gear10→`[1,3,5]`，且各 `position` 为原值 |
| 2 | 档内 volume 合计正确且跨档不变 | `brokerQueueFilter.test.ts` | `levelTotalVolume === Σcells`；切 gear 不变 |
| 3 | broker queue 覆盖非累加 | `marketStore.test.ts` | applyDelta(更少档) 后旧档消失，仅剩新档 |
| 4 | 旧日 alert 不显示 | `alertFilter.test.ts` + `marketStore.test.ts` | 混日 alerts 仅留 `tradeDate==sourceDate==effectiveDay` |
| 5 | alert 去重 | `alertFilter.test.ts` | 同 id 不重复 |
| 6 | 重连重发 snapshot | `marketFeed.spec.ts`（mock WebSocket） | 断开重连后 `requestSnapshots` 被再次调用 |
| 7 | seq 去重 | `marketStore.test.ts` | `seq <= maxSeq` 的 delta 被丢弃；snapshot seq=100 后 delta seq=100 拒绝、101 接受 |
| 8 | 展开/收起不改列宽 | `BrokerQueue.spec.ts` | 展开前后 `grid-template-columns` 不变（注明 jsdom 限制） |
| 9 | 移动不重叠 / ≥10 档 | 组件契约测 | 渲染 15 档可滚动到 ≥10；注明像素级重叠靠 Playwright（下一步） |

- 纯函数全部 mock-free 直测；`lightweight-charts` 在组件测中 stub 成 `<div>`（jsdom 不渲染 canvas/SVG），只断言 props/数据形态。
- 覆盖目标：关键路径（broker queue 过滤、alert 过滤/去重、seq 去重、覆盖语义、重连）≥80%。

---

## 10. 沟通交付物（Communication 15 分）

`frontend-project/README.md` 增补：
- 如何运行（`make serve` + `npm install` + `npm run dev`）。
- 组件结构（§2 树）。
- WebSocket 状态处理与重连（§4）。
- broker queue 档位过滤逻辑（§5）。
- 移动端如何防溢出/重叠（§7/§8）。
- 测试说明（§9）。
- **已知限制 + 下一步**：jsdom 不测真实布局像素；Playwright 视觉回归待接；暗盘/基本面等不在数据源内。

PR 描述讲清 tradeoff：为何 Pinia（隔离+可测）、为何前端过滤档位（服务端发全量，见 `api-contract.md`）、为何固定 1000ms 重连不退避（YAGNI）、为何 lightweight-charts（金融+性能+移动安全）。

---

## 11. Rubric 对照（覆盖到 100）

| 维度 | 分 | 覆盖 |
|---|---|---|
| 核心功能跑通 | 10 | §2–§8 全功能 |
| broker queue 语义 | 10 | §5 + 测 1/2/3 |
| effective-day / alerts 不串日 | 10 | §6 + 测 4/5 |
| WS snapshot/delta/reconnect | 10 | §4 + 测 6/7 |
| 组件/模块边界 | 8 | §2 组件树 |
| 状态管理可解释 | 7 | §3 store + 纯函数 |
| 测试覆盖关键坑 | 7 | §9 矩阵 |
| 错误/空态 | 3 | §8 |
| 桌面+移动布局稳定 | 8 | §7 双 pane + §8 响应式 |
| 信息层级清楚 | 8 | §2 面板分层 + §7/§8 |
| 数据时间+状态展示 | 4 | §7 数据时间 + §8 chip |
| PR/tradeoff/限制 | 15 | §10 |

---

## 12. 关键修正与风险

**综合时已吸收的契约修正（相对初稿 / 评审误判）：**
1. `seq` 在帧外层、不在 payload；client 必须透传 `frame.seq`。
2. snapshot 的 `seq = max(1, state.seq)`，**不重置为 0**；`maxSeq = frame.seq`。
3. alert 过滤须 `tradeDate === sourceDate === effectiveDay`（双校验）。
4. 档位过滤阈值是 `position <= gear`（gear 取 10/100/1000 本身），**不是 `gear/10`**（评审中两处误写，不予采纳）。
5. 图表 `time` 用 UTC epoch 秒，**不用 date-only**（否则全天塌成一根）。

**风险 / 实现期注意：**
- `lightweight-charts` 多 pane API 以最新版文档为准（实现期用 context7 确认 series/pane 调用）。
- jsdom 无法验证真实布局重叠 / 媒体查询；测 8/9 为契约级，像素级留 Playwright（README「下一步」）。
- 切 symbol 时务必 `chart.remove()` 防泄漏。
- broker_queue 覆盖：避免任何 `.push()`/merge，统一整张替换。

---

## 13. 后续

文档评审通过后 → 调用 `writing-plans` skill 产出带阶段/验收/测试顺序的实施计划，保存到 `docs/plans/`（带时间戳）。
