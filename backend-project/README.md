# Backend Project: Market State Engine Lite

目标：用 `mock-xtquant` 实现一个轻量实时行情状态引擎，并通过 WebSocket 输出 `snapshot/delta`。

候选人应直接使用：

```python
from xtquant import xtdata
```

不要接入真实 xtquant、Redis、Kafka 或生产服务。

`mock-xtquant` 模拟的是 SDK/raw sample 语义，不保证已经是 terminal API 业务视图。后端实现需要负责：

- effective day 对齐；
- old-date alerts 清理；
- broker queue snapshot 覆盖；
- 输出符合 `docs/api-contract.md` 的 snapshot/delta。

## Required Features

- 订阅 5 支股票：
  - `1m`
  - `hktransaction`
  - `hkbrokerqueueex`
- 维护每个 symbol 的内存 snapshot。
- `1m` 更新分钟 K 和 quote。
- `hktransaction` 生成大额交易 alert。
- `hkbrokerqueueex` 作为完整 broker queue 快照覆盖。
- WebSocket 支持：
  - `snapshot_request`
  - `visible_set`
  - `snapshot`
  - `delta`
- 动态 onboard 一个新 symbol。
- effective day 对齐：
  - 旧日期 historical alerts 不能混入今天 live 视图；
  - live tick 切到今天时，需要清掉 fallback alerts。

## Suggested Architecture

```text
adapters/xtquant_adapter.py  # 只负责从 xtdata 取数和订阅
state/engine.py              # 每个 symbol 的状态机
gateway/ws.py                # WebSocket 协议
models.py                    # payload 类型
```

## Run

```bash
PYTHONPATH=../mock-xtquant/src:src \
XTMOCK_SILVER_ROOT=../sample-data \
python -m market_state_engine.app
```

启动后默认监听：

```text
ws://127.0.0.1:9031/ws
```

## Big Trade Definition

默认阈值：

```text
tick.volume >= max(1, previous_or_current_daily_volume * 0.0005)
```

如果没有 daily baseline，可使用保守 fallback，但必须在代码和返回 payload 中说明。

## Submit

PR 里说明：

- 状态机设计；
- snapshot/delta 协议；
- effective day 怎么处理；
- broker queue 为什么是覆盖而不是累加；
- 测试覆盖了哪些坑。

## 实现说明

> 本任务已在本仓库完整实现，**40 个测试全绿**。PR 提交说明（含 tradeoff 与已知限制）见 [`SUBMISSION.md`](./SUBMISSION.md)。

模块拆分（单一职责、xtquant 仅 `adapters/`、业务仅 `state/`、协议仅 `gateway/`）：`models.py`（`frame`/`SymbolState`/常量）、`transforms.py`（参考纯转换逐字复制 + flatten/时间本地化）、`adapters/xtquant_adapter.py`（唯一 xtquant 边界）、`state/engine.py`（状态机 + `BaselineStore`）、`bridge.py`（线程→asyncio 桥）、`gateway/ws.py`（WS 协议）、`app.py`（装配根）。

### 状态机设计
每个 symbol 一个 `SymbolState`：`payload`（snapshot/minute_bars/alerts/broker_queue/freshness）、`seq`、`base_seq`、`deltas`（512 深环形缓冲）、`seen_tick_ids`、`last_queue_ts`、`lock`。freshness 三态：`hydrate` 后 `WARM` → 首个 live 事件经 `touch_freshness` 翻 `LIVE`。`apply(period,symbol,payload)` 是状态迁移的唯一入口，返回现成 delta 帧给 gateway，本身不碰 socket，故可像 `test_smoke` 一样独立单测。

### snapshot/delta 协议
`terminal-message-v3`、`schema_version=1`、`frame.source="candidate-backend"`。`seq` per-symbol 单调；snapshot 用 `seq=max(1,seq)`（永不为 0）。delta 三型：`minute_bar` / `trade_tick`（带 `tick`+`alert|null`）/ `broker_queue`（整快照）。客户端命令 `snapshot_request|visible_set|watchlist_set|health_request`，另加 `resume_request`（断线 seq 续传）与 `onboard_request`（动态加股）。监听 `ws://127.0.0.1:9031/ws`。

### 线程→asyncio 桥
SDK `subscribe_quote` 在每订阅各自的 daemon 线程触发回调；WS 跑单 asyncio loop。`ThreadAsyncBridge` 用 `loop.call_soon_threadsafe` 把每个事件交回 loop 线程——loop 成为**唯一写者**，`apply` 与 `seq` 分配都在那里，per-symbol 顺序天然保持、无竞态。产出的 delta 帧入 `asyncio.Queue`，gateway 用 `asyncio.gather` 并发广播，从而把状态变更与慢客户端的网络扇出解耦（一个慢客户端不拖垮全体）。

### effective day 处理
三处隔离：(1) 派生——`MARKET_EFFECTIVE_DAY` 覆盖，否则取该 symbol 分钟行的 max trade_date；(2) hydrate——逐 bar day-guard + `filter_current_day` 同时作用于 minute_bars 与 alerts；(3) live `apply`——旧日 1m/tick 事件 `return None` 直接丢弃（不入快照、不 bump seq）。broker queue 落后于 effective day 时不丢弃，而是打 `sourceDate/historical/fallback` 标记（样本数据每 symbol 仅一天队列、故多数 effective day 必触发 fallback——这是测试点）。alert 只能来自已过 day-guard 的 live tick，故其 `sourceDate==effectiveTradeDate` 恒成立，绝不混入旧日大额。

### broker queue 为什么是覆盖而不是累加
`hkbrokerqueueex` 每个事件就是该时刻的**整本快照**。`apply` 用 `state.payload["broker_queue"] = queue` 整体覆盖，绝不增量累加。档位（gear/position）直接取 SDK 已派生的值、**永不重编号**（10/100/1000 只过滤档位范围，不改编号）；一档总量 = 该档所有券商 cell 之和，与档位过滤无关；价格档位稀疏，不假设连续 1..N。`flatten_broker_levels` 把 SDK 嵌套 level 还原成扁平行时保留原 gear。

### 测试覆盖的坑（40 个测试）
队列整覆盖且不重编号（`test_engine_contract` 整覆盖 + `test_transforms` 稀疏 [1,3,11]）、effective-day 不串日（镜像 `test_contracts` 跑在候选引擎上 + day-switch）、alert 按 id 去重与阈值 `max(1,int(baseline*0.0005))` 截断/fallback 1000、broker queue fallback 标记、seq per-symbol 单调且重水合不回退、resume 三态（buffer 内/已最新/超 512 退 snapshot）、1m epoch 秒级时间本地化（防 1970 回归）、回放 wraparound 的 no-op 抑制、真实订阅端到端集成（daemon→bridge→apply→broadcast，断言 ≥1 `trade_tick`）。

### 运行
```bash
make serve-backend
# 或手动（在 backend-project/ 下）：
PYTHONPATH=../mock-xtquant/src:src XTMOCK_SILVER_ROOT=../sample-data \
  python -m market_state_engine.app
# → ws://127.0.0.1:9031/ws
```
