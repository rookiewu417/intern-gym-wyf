# Frontend Project: Market Terminal Lite

目标：基于 `mock-feed` 实现一个轻量行情终端页面。

默认数据源：

```text
ws://127.0.0.1:9021/ws
```

## Required Features

- 5 支股票 watchlist。
- 支持搜索/切换 symbol。
- 展示分钟 K 线和成交量。
- 展示大额交易表。
- 展示买卖 broker queue。
- broker queue 支持 `10 / 100 / 1000` 档切换。
- 档位序号必须保留原始 `position/gear`，不能重新归一化。
- 10/100/1000 只过滤原始档位范围，不改变每档内聚合逻辑。
- 桌面和手机都至少能看买卖各 10 档。
- 页面显示数据时间和 `Live/Warm/Closed` 状态 chip。
- WebSocket 断线后自动重连，不能重复刷屏。

## Important Edge Cases

- broker queue 是完整快照覆盖，不是增量累加。
- 某些档位可能稀疏，例如 `1, 3, 5, 11`。
- 大额交易不能混入非当前 effective day 的旧数据。
- UI 展开状态建议按 `symbol + side + price` 或 `symbol + side + position` 保存。

## Run

需要 Node.js `>=20.19.0`。

先在仓库根目录启动浏览器 mock feed：

```bash
make serve
```

再启动前端：

```bash
npm install
npm run dev
```

`mock-feed` 会保证 `minute_bars` 和 `alerts` 只包含当前 effective day。若 broker queue 使用旧日期样本作为 fallback，payload 会带 `broker_queue.fallback/historical/sourceDate`。

## Submit

PR 里说明：

- 组件结构；
- WebSocket 状态处理；
- broker queue 档位过滤逻辑；
- 移动端如何保证不溢出；
- 你写了哪些测试。

## 组件结构

`App.vue`（薄壳，只做编排 + WebSocket 生命周期 + 布局）组合：
- `Watchlist` — 5 标的 + 搜索/手输 symbol + 切换
- `SymbolHeader` + `ConnectionChip`（`#chip` 槽）— 中文名/代码/数据时间 + Live/Warm/Closed/Connecting 状态
- `QuoteStrip` — 行情摘要
- `ChartPanel` — lightweight-charts 蜡烛 + 成交量（独立 pane）
- `BigTradeTable` — 当日大额交易
- `BrokerQueue` → `BrokerQueueRow` → `BrokerCell` — 买卖盘口

状态集中在 Pinia `stores/marketStore.ts`；业务逻辑为纯函数：`utils/brokerQueueFilter.ts`、`utils/alertFilter.ts`、`utils/chartData.ts`、`stores/marketDelta.ts`。

## 状态管理与重连

- per-symbol record：`{ snapshot, minuteBars, alerts, brokerQueue, freshness, maxSeq }`。
- `frame.seq`（帧外层）透传；`seq <= maxSeq` 的 delta 丢弃；snapshot 的 `seq = max(1, state.seq)` 不重置。
- `MarketFeedClient` 维护 `trackedSymbols`，重连（`onopen`）后自动重发 `snapshot_request`，无需手动刷新；固定 1000ms 重连，不做指数退避。
- 状态 chip 优先级：未连上看连接态（Connecting/Closed/Error），连上后看 `freshness.runtime_state`（Live/Warm/Closed）。

## Broker Queue 过滤逻辑

- `10 / 100 / 1000` 档切换 = 前端按原始档位过滤 `position <= gear`，**绝不重编号**；显示原始 position。
- 每档 `volume` = 档内各 broker volume 之和，跨档位切换不变。
- broker queue 是**整张快照覆盖**，绝不增量累加。
- 展开/收起用固定 grid 轨道宽度，不改变买卖两列宽度；展开态 key = `symbol|side|position`。
- `sourceDate != effectiveDay` 时显示 `Fallback` 徽标。

## Effective-day 隔离

- snapshot 整体覆盖即按当日隔离；切日（trade-date 变化）丢弃旧日 bars，并按新日过滤 alerts。
- alert 进入当前视图需 `tradeDate === sourceDate === effectiveDay`。

## 移动端

- `<900px`：纵向堆叠；K 线/成交量分两个 pane 不重叠；broker queue 买卖纵向、容器可滚动保证各 ≥10 档。

## 测试

`npm run test`（Vitest + @vue/test-utils + jsdom）覆盖：
- 纯函数：档位过滤不重排 / 档内 volume 合计 / alert 当日过滤+去重 / bar upsert / 图表 epoch 转换。
- store：覆盖语义 / seq 去重 / 切日清理 / getter。
- 传输：重连重发 snapshot / `frame.seq` 透传 / `close()` 不重连。
- 组件：gear 切换 emit / 展开-收起 / fallback 徽标 / 空态 / 图表 pane 分离。

## 已知限制 / 下一步

- jsdom 不渲染真实布局像素与媒体查询：列宽稳定为 grid 轨道契约级断言；像素级重叠与移动端真实布局回归留待 Playwright（下一步）。
- ChartPanel 在测试中 mock 了 lightweight-charts；真实渲染已通过 `npm run build` 集成验证，但未做端到端可视回归。
- 暗盘 / 基本面等数据不在 `mock-feed` 范围内。
