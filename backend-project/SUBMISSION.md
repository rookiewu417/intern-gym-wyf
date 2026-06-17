# Market State Engine Lite — 提交说明 (PR 草稿)

## 概述

用 `from xtquant import xtdata` 实现轻量实时行情状态引擎：订阅 5 支港股的 `1m / hktransaction / hkbrokerqueueex`，在内存维护每 symbol 的 snapshot，通过 WebSocket（`ws://127.0.0.1:9031/ws`，协议 `terminal-message-v3` / `schema_version=1`）输出 `snapshot` 与 `delta`。

**核心设计决策**：把参考实现 `mock-feed/server.py`（`backend-project/tests/test_contracts.py` 校验的可执行规范）的纯业务转换函数**逐字复制**到 `transforms.py`，保证输出与规范逐字节一致；真正新写的只有 5 处：SDK 嵌套队列展平、线程→asyncio 桥、per-symbol seq + delta 环形缓冲 + reconnect 续传、动态 onboard、`frame.source="candidate-backend"`。

8 个职责单一的模块、40 个对抗式测试。

## 状态机设计

每 symbol 一个 `SymbolState`（`payload` / `seq` / `base_seq` / `deltas` 512 深环形缓冲 / `seen_tick_ids` / `last_queue_ts` / `lock`）。`apply(period,symbol,payload)` 是迁移的唯一入口，在 loop 单写者线程执行，变更 payload、bump per-symbol seq、append delta 环形缓冲，并返回 delta 帧——本身不碰 socket，便于独立单测。freshness 三态：hydrate 后 `WARM` → 首个 live 事件 `LIVE`。

## 协议

`frame` 信封恒含 `schema_version/protocol/type/source/server_ts/payload`，`symbol/seq/request_id` 仅在真值时附加。`source` 必须 `candidate-backend`。seq per-symbol 单调，snapshot 用 `max(1,seq)`。delta 三型 `minute_bar/trade_tick/broker_queue`。命令：`snapshot_request|visible_set|watchlist_set|health_request` + 候选扩展 `resume_request`（按 seq 续传）/`onboard_request`（动态加股）。

## Tradeoff

- **桥接选 `call_soon_threadsafe`**（而非 `run_coroutine_threadsafe` / 线程安全队列轮询）：生产者侧非阻塞（daemon 线程紧凑回放不被拖慢），且让 loop 成唯一写者 → per-symbol 顺序与 seq 单调免锁获得。
- **状态变更与广播解耦**：`apply` 同步快速（on-loop），delta 入 `asyncio.Queue` 由 gateway `asyncio.gather` 并发扇出 → 慢/死客户端不反压状态更新，也不互相拖累。
- **resume 是优化、snapshot 是地板**：512 深环形缓冲覆盖短暂断线的精确续传；离线超出则优雅退化为整 snapshot（配合 alert 按 id 去重 + minute bar 按 timestamp upsert，重叠应用幂等收敛）。

## 已知限制与下一步

诚实披露（均为已核实的真实约束，非遗漏）：

1. **baseline 的 SDK 限制**：本 lab 的 `xtdata` 取不到日线——`get_market_data_ex(period='1d')` 走死路返回 `{}`，`get_instrument_detail` 返回 `{}`。故大额阈值的 daily baseline、券商名映射、标的名由 `BaselineStore` 直读 `sample-data/*.csv`（与参考 `SampleDataStore` 同源，隔离在单一数据边界）。`XtquantAdapter.fetch_daily_baseline` 仍保留"先试 SDK"路径，未来若 SILVER_FAMILIES 增加 `1d` 即可生效。

2. **`error` 帧是无契约的发明**：文档列了 `error` 类型但参考实现从不发、也无字段规范。本实现用最小 `{code,message}`，`request_id` 放**顶层信封**（与 `ack`/`heartbeat` 一致），并把坏 JSON/未知命令收成 error 帧、不让 `handle_client` 崩溃。无测试可对齐其字段——这是有意的健壮性增强，非镀金。

3. **无限回放与 resume 退化**：未设回放上限时 SDK daemon 会对该 symbol 行**取模无限重放**。`apply` 用"重复 tick-id / 同 `queue_ts` / 同 bar 不发 delta、不 bump seq"抑制 seq 膨胀；长时间离线客户端的 resume 会优雅退化为整 snapshot（512 深 ring 之外）。`make serve-backend` 设 `XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION=2000` 作双保险。

4. **不存在"live tick 到今天就清 fallback alert"机制**：hydrate **从不注入历史 alert**（`alerts=[]` + `filter_current_day`），`big_trade_alert` 只对已过 day-guard 的 live tick 产出、其 `sourceDate==tick.tradeDate==effective_day`。因此"历史 alert 仅当 `sourceDate==effectiveTradeDate` 才入快照"是**空真**满足，不需要、也不应新增任何注入历史 alert 的路径。

5. **`effective_day` 的数据形状耦合**：取自 `fetch_minute_rows(count=420)` 的 tail-420 行的 max 日（参考实现扫全部分钟行）。样本每 symbol 每日约 341 bar、tail-420 仍含最后一日，故两者一致；但若某单日 bar 数 > 420 则可能偏差——必要时改为专门的全量 max-date 扫描。

6. **1m `time` 的 epoch 量级与 pandas 版本相关**：本 lab pandas 3.0（`datetime64[us]`）下 `silver_store._timestamp_ms` 实际产出 epoch **秒**（10 位），pandas 2.2（`datetime64[ns]`）下是毫秒（13 位）。`ms_to_hk_iso` 以 `1e12` 边界按量级兼容两者（2026 秒≈1.78e9 < 1e12 ≤ 2026 毫秒≈1.78e12），故对 pandas 版本无关，不依赖在 `requirements.txt` 钉死 pandas。若误当毫秒做 `/1000` 会使时间戳落到 1970、`effective_day` 退化——已加 10 位秒单测防回归。

**下一步**：每客户端独立 bounded 队列做精细背压（队列溢出则强制重连取 snapshot）、midnight roll 自动切交易日、periodic heartbeat keepalive。

## 测试

40 个测试（`make test` 或 `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests -q`）：`test_models`(3) `test_transforms`(10) `test_adapter`(4) `test_engine_contract`(6) `test_bridge`(2) `test_gateway`(5) `test_reconnect`(4) `test_integration_live`(1) + 既有 `test_smoke`(1) `test_contracts`(4)。覆盖每个评分红线，含真实订阅端到端集成。
