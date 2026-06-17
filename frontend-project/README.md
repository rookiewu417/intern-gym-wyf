# Frontend Project: Market Terminal Lite

轻量**实时**行情终端：连接 `mock-feed`，消费 WebSocket `snapshot / delta`，展示 5 支港股的实时回放行情——K 线 + 成交量、大额交易、经纪盘口（broker queue）。

默认数据源：`ws://127.0.0.1:9021/ws`（可用 `VITE_WS_URL` 覆盖）。

---

## 快速启动

需要 **Node.js ≥ 20.19.0**，以及 **Python 3.12/3.13**（只给 mock-feed 用）。要同时跑两个进程：

1. **mock-feed**（仓库根目录，数据源）
2. **前端 dev server**（本目录 `frontend-project/`）

### 步骤 1 — 启动 mock-feed（在**仓库根目录**，单独留一个终端）

```bash
# 仓库根目录
python -m venv .venv && source .venv/bin/activate
make install        # 安装 pandas / pyarrow / websockets
make serve          # 输出 "mock feed listening on ws://0.0.0.0:9021/ws" 即就绪
```

> 用 uv 等价：`uv venv && uv pip install -r requirements.txt`，再 `make serve`。
> 这个终端保持开着；它会按真实事件时间回放历史行情，模拟一个活的数据源。

### 步骤 2 — 启动前端（在本目录 `frontend-project/`）

```bash
cd frontend-project
npm install
npm run dev         # Vite -> http://localhost:5176
```

浏览器打开 **http://localhost:5176**：应看到左侧 5 支标的、K 线 + 成交量、大额交易表、买卖经纪盘口，右上角状态 chip 显示 `Live`，且数据会自动刷新（无需手动刷新页面）。

### 常用命令

```bash
npm run build       # vue-tsc --noEmit && vite build（类型检查 + 生产构建）
npm run test        # Vitest 单元/组件测试
```

### 故障排查

- **页面空白 / 连不上**：确认步骤 1 的 mock-feed 仍在跑、监听 `:9021`。
- **`make serve` 报缺包**：先在已激活的 venv 里 `make install`。
- **换数据源**：在本目录建 `.env`，写 `VITE_WS_URL=ws://<host>:<port>/ws`。
- **命令行 WS 自测连不上**：若环境设了 `*_proxy`（含 socks），`localhost` 可能被代理拦截；自测时先 `unset http_proxy https_proxy all_proxy`。浏览器通常自动绕过 localhost，不受影响。

---

## Required Features

- 5 支股票 watchlist，导航显示 `中文名 + 代码`，支持搜索/手动输入 symbol，切换不串状态。
- 分钟 K 线 + 同屏成交量；移动端两者不重叠；左上角显示中文名与数据时间。
- 大额交易表：按时间倒序、去重、只显示当前 effective day、live delta 自动追加。
- 买卖 broker queue，支持 `10 / 100 / 1000` 档切换；档位保留原始 `position/gear`，不重新归一化。
- 桌面和手机都至少能看买卖各 10 档。
- 状态 chip：`Live / Warm / Closed / Connecting`；WebSocket 断线自动重连、重连后自动重拉 snapshot。

## Important Edge Cases

- broker queue 是完整快照覆盖，不是增量累加。
- 档位（position）可能稀疏、非连续、且数值很大（见下方「档位语义」）。
- 大额交易不能混入非当前 effective day 的旧数据。
- broker cell 同一价位内同一券商可重复出现（多笔挂单）；UI 展开态按 `symbol + side + position` 保存。

---

## 组件结构

`App.vue`（薄壳：编排 + WebSocket 生命周期 + 布局）组合：

- `Watchlist` — 5 标的 + 搜索/手输 symbol + 切换
- `SymbolHeader` + `ConnectionChip`（`#chip` 槽）— 中文名/代码/数据时间 + `Live/Warm/Closed/Connecting`
- `QuoteStrip` — 行情摘要
- `ChartPanel` — lightweight-charts 蜡烛 + 成交量（独立 pane，结构上防重叠）
- `BigTradeTable` — 当日大额交易
- `BrokerQueue` → `BrokerQueueRow` → `BrokerCell` — 买卖盘口

状态集中在 Pinia `stores/marketStore.ts`；业务逻辑为纯函数：`utils/brokerQueueFilter.ts`、`utils/alertFilter.ts`、`utils/chartData.ts`、`stores/marketDelta.ts`。

## 状态管理与重连

- per-symbol record：`{ snapshot, minuteBars, alerts, brokerQueue, freshness, maxSeq }`。
- `frame.seq`（帧外层）透传；`seq <= maxSeq` 的 delta 丢弃；snapshot 的 `seq = max(1, state.seq)` 不重置。
- `MarketFeedClient` 维护 `trackedSymbols`，重连（`onopen`）后自动重发 `snapshot_request`，无需手动刷新；固定 1000ms 重连，不做指数退避。
- 状态 chip 优先级：未连上看连接态（Connecting/Closed/Error），连上后看 `freshness.runtime_state`（Live/Warm/Closed）。

## Broker Queue 过滤逻辑

- `10 / 100 / 1000` 档切换 = 前端按原始档位过滤 `position <= gear`，**绝不重编号**；显示原始 position。默认档位 `1000`（显示全深度，再向下收窄）。
- 每档 `volume` = 档内各 broker volume 之和，跨档位切换不变。
- broker queue 是**整张快照覆盖**，绝不增量累加。
- 行内显示 side（买/卖）；展开/收起用固定 grid 轨道宽度，不改变买卖两列宽度；展开态 key = `symbol|side|position`。
- `sourceDate != effectiveDay` 时显示 `Fallback` 徽标。

### 档位（position）语义 —— 重要

本 mock 数据里 `position`/`gear` 是**「挂单进入队列的全局序号」**（整个盘口按价格顺序 1..N 编号），**不是「第几档价」**。因此：

- 一个价位的「档位」= 该价位**首笔挂单的序号**；
- 相邻价位的档位会**跳过「上一价位的挂单笔数」**（如 52.85 有 25 笔 → 占序号 1–25 → 下一价位 52.90 档位 = 26）；
- 所以档位数字**稀疏、不连续、可达上千**（如 516、536、563）属正常；
- 前端按文档要求**原样显示、不重编号**（重编号是评分红线）。

部分标的的盘口是历史 **fallback** 切片（`broker_queue.fallback/sourceDate`），其档位落在较深区间，故 `10`/`100` 档可能为空，需切到 `1000`。

## Effective-day 隔离

- snapshot 整体覆盖即按当日隔离；切日（trade-date 变化）丢弃旧日 bars，并按新日过滤 alerts。
- alert 进入当前视图需 `tradeDate === sourceDate === effectiveDay`。

## 移动端

- `< 900px`：纵向堆叠；K 线/成交量分两个 pane 不重叠；broker queue 买卖纵向、容器可滚动保证各 ≥ 10 档。

## 测试

`npm run test`（Vitest + @vue/test-utils + jsdom）覆盖：

- 纯函数：档位过滤不重排 / 档内 volume 合计 / alert 当日过滤+去重 / bar upsert / 图表 epoch 转换。
- store：覆盖语义 / seq 去重 / 切日清理 / getter。
- 传输：重连重发 snapshot / `frame.seq` 透传 / `close()` 不重连。
- 组件：gear 切换 emit / 展开-收起 / side 标识 / fallback 徽标 / 空态 / 图表 pane 分离。

## 已知限制 / 下一步

- jsdom 不渲染真实布局像素与媒体查询：列宽稳定为 grid 轨道契约级断言；像素级重叠与移动端真实布局回归留待 Playwright（下一步）。
- ChartPanel 在测试中 mock 了 lightweight-charts；真实渲染已通过浏览器联调与 `npm run build` 验证，但未做自动化可视回归。
- 「档位 = 挂单序号」是 mock 数据的语义特性；若产品上想要「按价格深度的 1/2/3 档」需另做价位重排（与文档「不可重编号」冲突，未实现）。
- 暗盘 / 基本面等数据不在 `mock-feed` 范围内。

## Submit / PR 说明

PR 描述应包含：如何运行、组件结构、WebSocket 状态/重连处理、broker queue 档位过滤逻辑、移动端防溢出、测试说明、已知限制与下一步。
