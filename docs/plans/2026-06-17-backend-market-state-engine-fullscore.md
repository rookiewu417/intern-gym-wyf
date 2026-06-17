# Market State Engine Lite — 满分实现计划 (Backend Project)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 提交身份必须为 `rookiewu417 / 1007372080@qq.com`（仓库已配置）。

**Goal:** 在 `backend-project/` 用 `from xtquant import xtdata` 实现一个轻量实时行情状态引擎，订阅 5 支港股的 `1m/hktransaction/hkbrokerqueueex`，在内存维护每 symbol snapshot，并按 `terminal-message-v3`(schema 1) 协议通过 WebSocket(:9031) 输出 `snapshot/delta`，做到评分表 100/100：broker queue 整快照覆盖且不重编号、effective-day 隔离、大额 alert 去重、freshness 证据、reconnect+seq 续传、动态 onboard、health/error 帧，并以对抗式单测覆盖每一个 graded trap。

**Architecture:** 八个职责单一的模块。**核心决策**：把 mock-feed 参考实现（`mock-feed/src/market_mock_feed/server.py`，即 `backend-project/tests/test_contracts.py` 校验的可执行规范）里的**纯业务转换函数逐字复制**到 `transforms.py`，保证输出与规范逐字节一致；真正新写的只有 5 处：(1) `XtquantAdapter` 把 SDK 的嵌套 broker-queue level 还原成扁平行 + 把 1m 的 epoch 时间戳（**按量级兼容秒/毫秒**）本地化为 +08:00；(2) `ThreadAsyncBridge` 把 SDK 守护线程回调安全地交给 asyncio 单写者；(3) per-symbol seq + delta 环形缓冲 + reconnect 续传；(4) 动态 onboard；(5) `frame()` 的 `source` 必须是 `"candidate-backend"`。状态机（effective-day 隔离、apply、seq）全部收敛在 `state/engine.py`，与传输层彻底解耦，保持 `test_smoke` 的 `MarketStateEngine(['02723.HK']).hydrate()` 接口不变。

**Tech Stack:** Python 3.12/3.13、`websockets`、`pandas`、`asyncio` + `threading`（桥接）、`pytest`。无任何真实 xtquant/Redis/Kafka；唯一非 SDK 读取（baseline/券商名/标的名参考数据）隔离在 `BaselineStore` 中读 `sample-data/*.csv`，因为 SDK mock 不暴露这些（`get_instrument_detail` 返回 `{}`，无 `1d` 周期）。

---

## 0. 执行前必读：已核实的硬约束（决定每段代码为何这样写）

这些事实由通读 `mock-xtquant/src/xtmock/{replay_engine,silver_store,config}.py`、`mock-xtquant/src/xtquant/xtdata.py`、`mock-feed/src/market_mock_feed/server.py`、两份后端测试和真实 `sample-data/` 逐一核实，**对抗式评审已确认其中 4 个 blocker**。实现时若与下述任一条冲突，以本节为准。

### 0.1 SDK 数据路径（候选人唯一可用入口）
- `subscribe_quote(stock_code, period=..., callback=...)` **丢弃** `start_time/end_time/count`，默认 `period='1d'`。`'1d'` 不是 silver-backed，返回 `{}` 并打印 `周期错误1d…`。**必须**用 `period in {'1m','hktransaction','hkbrokerqueueex'}`。
- 回调签名：`callback({symbol: [payload]})` —— 单参数 dict，值是**只含 1 个元素的 list**，不是 DataFrame、不是裸 dict。回调在**每个订阅各自的 daemon 后台线程**上触发（`replay_engine.py:404-437`），共享状态必须加锁/转交 loop。
- `period='1m'` 的 payload **只有** `time/Time`（**epoch 秒**，10 位整数，如 `1780992600`；本 lab pandas 3.0 的 `datetime64[us]` 使 `silver_store._timestamp_ms` 的 `//1e6` 实际得到的是秒而非毫秒——已实测核实），**没有** `bar_ts`、没有 ISO `timestamp`。OHLC 为 float。→ **(BLOCKER 修复)** 适配层必须把 `time` **按量级**本地化为 `+08:00` ISO 注入 `bar_ts`（`ms_to_hk_iso` 用 1e12 边界兼容秒/毫秒，对 pandas 版本无关：2026 秒≈1.78e9 < 1e12 ≤ 2026 毫秒≈1.78e12）。**若误当毫秒做 `/1000`**：秒被当毫秒 → `minute_bar` 时间戳落到 **1970-01-21** → `effective_day` 退化成 `19700121` → 整套日隔离崩塌、≥3 个测试挂。参考实现 mock-feed 不受影响（它直读 parquet 的 `bar_ts` ISO 字符串，从不碰 SDK 的 `time` 整数）。
- `period='hktransaction'` 的 payload 有 `tick_ts`(ISO +08:00 字符串) + `time`(epoch 秒，未用) + `side`('buy'/'sell'/'neutral') + `trade_id` + `active_broker_code` 等。`trade_tick()` 优先读 `tick_ts`（不碰 `time`），正确。
- `period='hkbrokerqueueex'` 的 payload 是**整快照**：顶层 `time/Time/timestamp/queue_ts/askbrokerqueues/bidbrokerqueues`(+别名 `askQueues/bidQueues`)。每个 level 是 SDK 已派生好的 dict：`{gear, position(==gear), price, brokerCount, brokers:[码], volumes:[每券商汇总量]}`。**level 内没有券商名，只有券商码**。
- `get_market_data_ex(field_list, stock_list, period, count)` 返回 `dict[symbol -> DataFrame]`；`count` 在此处**有效**(`tail(count)`)。**(BLOCKER 修复)** `field_list=[]` 时对 `hkbrokerqueueex` 只保留 `PERIOD_COLUMNS=['time','askbrokerqueues','bidbrokerqueues']`，**会丢掉 `queue_ts`** → `sourceDate` 变空 → `historical/fallback` 退成 `False` → 直接挂掉 `test_contracts.py:38-40` 的核心断言。**必须**显式传 `field_list=['time','queue_ts','timestamp','askbrokerqueues','bidbrokerqueues']`。
- **xtdata 取不到日线**：`'1d'` 死路返回 `{}`；`get_instrument_detail/_list` 返回 `{}`。→ 大额 alert 的 daily baseline 与券商/标的名只能由 `BaselineStore` 直读 `sample-data/*.csv`（与参考实现的 `SampleDataStore` 同源）。
- **无限回放**：未设 `XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION` 时 daemon 线程对该 symbol 行**取模无限循环重放**（`replay_engine.py:430-434`）。→ 同一 tick/bar/queue 会反复重放。`merge_alert` 按 id 去重保住 alerts，但若不做变更检测，seq 会无限膨胀、环形缓冲灌满 no-op、resume 永远退化为 snapshot、相同 broker_queue 反复刷客户端。→ 计划用「单写者里做变更检测（重复 tick-id / 同 queue_ts / 同 bar 不发 delta、不 bump seq）」+ serve/test 环境设上 `XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION` 双保险。
- `unsubscribe_quote(seq)` 协作式停（置 `stop_event`，daemon 下个循环退出，无 join）。
- 传规范符号 `NNNNN.HK`（回调 key 用的是你传入的原始字符串，未归一化）。

### 0.2 WebSocket 线协议（必须逐字段匹配参考实现，文档里的 JSON 是占位 stub）
- 信封 `frame()`：恒有 `schema_version=1, protocol="terminal-message-v3", type, source, server_ts(ISO UTC ms), payload`；`symbol/seq/request_id` 仅在真值时附加。**`source` 必须 `"candidate-backend"`**（`test_contracts.py:62` 唯一校验候选代码的断言）。
- 连接即发 `hello`(payload.symbols=全集) + `heartbeat`(ready)。
- 客户端命令：`snapshot_request|visible_set|watchlist_set|health_request`（后端必需前三 + health；本计划另加 candidate-extra `resume_request`、`onboard_request`）。每条命令先回 `ack`。`snapshot_request/visible_set/watchlist_set` → 逐 symbol 回 `snapshot`。`health_request` → 回带 `request_id` 的 `heartbeat`。**`visible_set` 不得改变监控universe、不得 re-hydrate 已 live 的 symbol**，只请求快照。
- snapshot payload：`{symbol, snapshot, minute_bars[], alerts[], broker_queue{}, freshness{}}`。各子对象精确字段见 §0.3。
- delta payload：`{delta_type: 'minute_bar'|'trade_tick'|'broker_queue', ...}`；`trade_tick` 带 `tick` 与 `alert`(可为 `null`)。
- `seq` **per-symbol 单调**；`snapshot` 用 `seq=max(1,st.seq)`（不为 0）。`error` 帧文档列了但参考实现从不发、无字段契约 → 我们自定义最小 `{code,message}` 并在 PR 注明这是无契约的发明。

### 0.3 精确 payload 形状（来自参考实现，superset 优先于文档子集）
- `snapshot`(quote)：`{symbol,name,currency:"HKD",price,open,high,low,volume(=Σbar volume),turnover(=Σbar turnover),updatedAt,tradeDate}`。
- `minute_bars[]`：`{timestamp(ISO),price(=close),open,high,low,close,volume(int),turnover}`，按 timestamp 去重升序，留最近 420。
- `alerts[]`：`{id:"big-<sym>-<tick.id>",timestamp,tradeDate,sourceDate,historical,source:"mock_hktransaction",price,volume,turnover,side,brokerCode,thresholdVolume,thresholdRatio:0.0005,baselineVolume}`，按 id 去重、newest-first、cap 100。
- `broker_queue`：`{ask[],bid[],sourceDate,historical,fallback}`；`historical==fallback==bool(sourceDate && effective_day && sourceDate!=effective_day)`；每 side 按 position 升序。
- level：`{id:"<side>-<pos>-<price>",side,position(原始/派生档位，**永不重编号**),gear(==position),price,volume(=Σ cell),brokerCount,brokers[]}`。
- cell：`{brokerCode,displayName,volume}`；码 `"0"` → `displayName="未披露"`。
- `freshness`：`{runtime_state("WARM" 水合后 / "LIVE" 有 live 事件后),effective_day,source_dates{kind->ISO}}`；候选额外加 `mock_rows{minute_bars,broker_queue}`（`test_smoke` 需要 `mock_rows.minute_bars>0`）。

### 0.4 真实样本数据形状（写 fixture/断言用真名真值）
- `silver_broker_queue_v1`(parquet)：列 `…,side('bid'/'ask'),position,broker_code,price,volume,queue_ts,…`，**无 gear 列**；OHLCV/price/volume 字符串需 cast。真实 position 是**连续 1..N**（不是稀疏）；深度：`02723.HK=10/10`(最佳小 fixture)，`02675.HK bid=137`，其余 `1000/1000`。
- **混源日（fallback 测试点，已核实）**：minute/ticks 跨 `20260601..20260609`(7 天)，但 broker_queue 每 symbol 只有一天：`02723.HK=20260603`，其余=`20260601`。→ effective_day=20260609 时队列必然落后 → `historical=fallback=True`。
- `silver_minute_bars_v1`：时间列 `bar_ts`(+08:00)，OHLCV 为**字符串**。`silver_trade_ticks_v1`：时间列 `tick_ts`(+08:00)，`side` ∈ `neutral/buy/sell`。
- `silver_daily_bars_v1.csv`：63 行仅 5 symbol，OHLCV 数值，**无 previous_close/suspend_flag**（那是 strategy 的 research-data，**勿混**）；用于 baseline。
- `silver_broker_mapping_v1.csv`：`broker_code(int)->broker_name/participant_name`；`silver_instruments_v1.csv`：`symbol->name`。
- 「稀疏不重编号」不变量由**单测 fixture**（position 1/3/11）强制，真实数据是连续的。

### 0.5 测试即规范
- `test_contracts.py` import 的是 **mock-feed 参考实现**（snapshot/effective-day/broker-queue 断言校验的是参考，不是候选），唯一校验候选的是 `frame()` 的 `source=='candidate-backend'`。→ **候选引擎必须自带一套镜像断言**（`test_engine_contract.py`），否则 hydrate/effective-day/fallback 全程无人验证。
- `test_smoke.py` 是唯一跑骨架的：`MarketStateEngine(['02723.HK'])`(单参) → `.hydrate()`(无参) → `.snapshots['02723.HK'].payload`，断言 `freshness.runtime_state=='WARM'` 且 `freshness.mock_rows.minute_bars>0`。**重构必须保住这个构造/方法面**。⚠️ `update_quote_from_bar` 会 `touch_freshness→LIVE`，所以 hydrate 末尾**必须把 runtime_state 复位回 WARM**，否则 test_smoke 挂。

---

## 文件结构

```
backend-project/src/market_state_engine/
├── __init__.py                      # 既有
├── models.py            (新) 常量 + frame() + SymbolState + now_iso   —— 无 xtquant/asyncio/pandas
├── transforms.py        (新) 参考实现纯转换逐字复制 + flatten_broker_levels + ms_to_hk_iso + latest_daily_volume
├── adapters/
│   ├── __init__.py      (新)
│   └── xtquant_adapter.py (新) 全部且仅此处碰 xtdata：hydrate 取数(含 queue_ts 修复/bar_ts 本地化) + subscribe
├── state/
│   ├── __init__.py      (新)
│   └── engine.py        (新) MarketStateEngine 状态机 + BaselineStore —— effective-day/apply/seq/resume/onboard
├── bridge.py            (新) ThreadAsyncBridge：daemon 线程 → asyncio 单写者
├── gateway/
│   ├── __init__.py      (新)
│   └── ws.py            (新) WS 协议：hello/heartbeat/ack/snapshot/delta/error/resume/onboard + 并发广播
└── app.py              (改) composition root + 回出口 frame/MarketStateEngine（保 test 兼容）

backend-project/tests/
├── test_smoke.py        (既有，保持通过)
├── test_contracts.py    (既有，保持通过)
├── test_transforms.py   (新) flatten/broker-queue/alert/filter/localize/upsert
├── test_adapter.py      (新) queue_ts 保留 / count=1<3s / bar_ts 本地化
├── test_engine_contract.py (新) 候选引擎镜像 test_contracts 的 effective-day 契约
├── test_reconnect.py    (新) resume 三态 + seq 不回退 + day-switch
├── test_bridge.py       (新) 桥接路由 + 关闭 loop 容错
├── test_gateway.py      (新) 协议帧 / 错误帧 / resume 分支（fake ws）
└── test_integration_live.py (新) 真 subscribe → bridge → apply → broadcast 端到端
```

每个源文件单一职责、可独立 hold-in-context；`transforms.py` 纯函数、`engine.py` 不碰 socket、`adapters` 不碰 WS、`gateway` 不碰业务数学 —— 直接对应评分「组件/模块边界清晰:8」。

---

## Task 0：包脚手架 + models.py（frame / 常量 / SymbolState）

**Files:**
- Create: `backend-project/src/market_state_engine/adapters/__init__.py`
- Create: `backend-project/src/market_state_engine/state/__init__.py`
- Create: `backend-project/src/market_state_engine/gateway/__init__.py`
- Create: `backend-project/src/market_state_engine/models.py`
- Test: `backend-project/tests/test_models.py`

- [ ] **Step 1: 写失败测试** `backend-project/tests/test_models.py`

```python
from market_state_engine.models import frame, SymbolState, DEFAULT_SYMBOLS, DELTA_RING_CAPACITY


def test_frame_source_is_candidate_backend():
    msg = frame("hello", payload={"symbols": ["02723.HK"]})
    assert msg["schema_version"] == 1
    assert msg["protocol"] == "terminal-message-v3"
    assert msg["type"] == "hello"
    assert msg["source"] == "candidate-backend"   # test_contracts.py:62 的同一断言
    assert msg["server_ts"]
    assert msg["payload"]["symbols"] == ["02723.HK"]
    assert "symbol" not in msg and "seq" not in msg and "request_id" not in msg


def test_frame_conditional_fields():
    msg = frame("delta", symbol="02723.HK", seq=5, request_id="r1", payload={"delta_type": "minute_bar"})
    assert msg["symbol"] == "02723.HK"
    assert msg["seq"] == 5
    assert msg["request_id"] == "r1"
    # seq=0 时省略
    assert "seq" not in frame("snapshot", symbol="X", seq=0)


def test_symbol_state_defaults():
    st = SymbolState(symbol="02723.HK", name="深演智能", baseline_volume=1000, effective_day="20260609")
    assert st.seq == 0 and st.base_seq == 0
    assert st.deltas.maxlen == DELTA_RING_CAPACITY
    assert st.last_queue_ts == "" and st.seen_tick_ids == set()
    assert len(DEFAULT_SYMBOLS) == 5
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend-project && XTMOCK_SILVER_ROOT=../sample-data python -m pytest tests/test_models.py -q` （仓库根已 `source .venv/bin/activate`）
Expected: FAIL —— `ModuleNotFoundError: market_state_engine.models`

> 注：从仓库根跑时用 `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_models.py -q`（`pytest.ini` 已设 pythonpath）。下文命令统一以**仓库根**为 cwd。

- [ ] **Step 3: 创建三个 `__init__.py`**

`backend-project/src/market_state_engine/adapters/__init__.py`、`state/__init__.py`、`gateway/__init__.py` 内容均为：

```python
```
（空文件即可，仅作包标记。）

- [ ] **Step 4: 实现 `backend-project/src/market_state_engine/models.py`**

```python
from __future__ import annotations

import collections
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PROTOCOL = "terminal-message-v3"
SCHEMA_VERSION = 1
SOURCE = "candidate-backend"  # test_contracts.py:62 —— 不可写成参考实现的 internship-mock-feed
DEFAULT_SYMBOLS = ("02723.HK", "02675.HK", "00100.HK", "02513.HK", "06082.HK")
DELTA_RING_CAPACITY = 512  # per-symbol delta 环形缓冲深度；超出则 resume 退化为 snapshot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def frame(message_type: str, *, symbol: str = "", seq: int = 0, request_id: str = "",
          payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "type": message_type,
        "source": SOURCE,
        "server_ts": now_iso(),
        "payload": payload or {},
    }
    if symbol:
        result["symbol"] = symbol
    if seq:
        result["seq"] = seq
    if request_id:
        result["request_id"] = request_id
    return result


@dataclass
class SymbolState:
    symbol: str
    name: str
    baseline_volume: int
    effective_day: str
    seq: int = 0
    base_seq: int = 0                       # 当前 snapshot 反映的 seq；< base_seq 的 delta 已失效
    payload: dict[str, Any] = field(default_factory=dict)
    deltas: "collections.deque[dict]" = field(
        default_factory=lambda: collections.deque(maxlen=DELTA_RING_CAPACITY))
    sub_ids: dict[str, int] = field(default_factory=dict)   # {period: xtdata subscription seq}
    seen_tick_ids: set[str] = field(default_factory=set)    # 回放 wraparound 去重，抑制重复 trade_tick delta
    last_queue_ts: str = ""                                 # 抑制相同 broker_queue 重发
    lock: "threading.Lock" = field(default_factory=threading.Lock)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_models.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: 提交**

```bash
git add backend-project/src/market_state_engine/adapters backend-project/src/market_state_engine/state backend-project/src/market_state_engine/gateway backend-project/src/market_state_engine/models.py backend-project/tests/test_models.py
git commit -m "feat(backend): add models.py (frame/SymbolState) + package scaffolding"
```

---

## Task 1：transforms.py（参考纯转换逐字复制 + 候选新增纯函数）

**Files:**
- Create: `backend-project/src/market_state_engine/transforms.py`
- Test: `backend-project/tests/test_transforms.py`

新增的候选专属纯函数：`ms_to_hk_iso`（1m epoch 时间戳按量级（秒/毫秒）→+08:00 ISO，修复 minute-bar 时区 blocker）、`flatten_broker_levels`（SDK 嵌套 level→扁平行，**保留 SDK 派生 gear、永不重编号**，把 `queue_ts` 写到每一行，防御缺失/空 side）、`upsert_bar_changed`（带「是否变更」返回值，供 live 路径抑制 no-op delta）、`latest_daily_volume`（baseline）。其余 14 个函数从 `mock-feed/server.py` 逐字复制（签名/实现一致以保证逐字节同输出）。

- [ ] **Step 1: 写失败测试** `backend-project/tests/test_transforms.py`

```python
from datetime import datetime, timezone, timedelta

import pandas as pd
from dataclasses import dataclass

from market_state_engine.transforms import (
    ms_to_hk_iso, minute_bar, trade_tick, broker_queue_from_rows, flatten_broker_levels,
    filter_current_day, big_trade_alert, merge_alert, upsert_bar_changed, empty_snapshot,
    latest_daily_volume, trade_date_from_timestamp,
)

HK_TZ = timezone(timedelta(hours=8))


@dataclass
class FakeState:                       # big_trade_alert 鸭子类型只需 symbol/baseline_volume
    symbol: str
    baseline_volume: int


def _hk_ms(year, month, day, hour, minute):
    # 由 datetime 反推 epoch ms，避免硬编码魔数（自洽，不依赖手算）
    return int(datetime(year, month, day, hour, minute, tzinfo=HK_TZ).timestamp() * 1000)


def test_ms_to_hk_iso_localizes_to_plus08():
    iso = ms_to_hk_iso(_hk_ms(2026, 6, 9, 9, 30))         # 13 位毫秒分支
    assert iso.endswith("+08:00")
    assert iso[:10].replace("-", "") == "20260609"
    assert iso.startswith("2026-06-09T09:30")
    # 真实 SDK 形态：10 位 epoch 秒（pandas 3.0 datetime64[us]）也必须正确本地化——
    # 这条专门防止「单测用伪造的毫秒而掩盖了秒级 bug」的回归
    assert trade_date_from_timestamp(ms_to_hk_iso(1780992600)) == "20260609"


def test_minute_bar_from_sdk_payload_only_time_ms():
    # SDK 1m payload 只有 time(epoch 秒/毫秒)；适配层注入 bar_ts 后 minute_bar 应产出 +08:00 时间戳
    ms = _hk_ms(2026, 6, 9, 9, 30)
    row = {"time": ms, "bar_ts": ms_to_hk_iso(ms),
           "open": 350.0, "high": 351.0, "low": 349.0, "close": 350.5, "volume": 1200, "amount": 420000.0}
    bar = minute_bar(row)
    assert bar["timestamp"].endswith("+08:00")
    assert bar["close"] == 350.5 and bar["price"] == 350.5 and bar["volume"] == 1200
    assert trade_date_from_timestamp(bar["timestamp"]) == "20260609"


def test_broker_queue_preserves_sparse_positions_never_renumber():
    # 镜像 test_contracts.py:43-54 —— 1/3/11 不连续，position 与 gear 都要原样保留
    q = broker_queue_from_rows([
        {"side": "ask", "position": 1, "gear": 1, "price": 10.0, "broker_code": "1", "volume": 100, "queue_ts": "2026-06-01T09:30:00+08:00"},
        {"side": "ask", "position": 3, "gear": 3, "price": 10.2, "broker_code": "2", "volume": 200, "queue_ts": "2026-06-01T09:30:00+08:00"},
        {"side": "ask", "position": 11, "gear": 11, "price": 11.0, "broker_code": "3", "volume": 300, "queue_ts": "2026-06-01T09:30:00+08:00"},
    ], {}, effective_day="20260601")
    assert [l["position"] for l in q["ask"]] == [1, 3, 11]
    assert [l["gear"] for l in q["ask"]] == [1, 3, 11]


def test_flatten_then_group_preserves_sdk_gear_and_sums_cells_with_fallback_flags():
    # 对抗评审 blocker-1：LIVE/hydrate 路径（flatten→group）必须保 SDK 派生 gear、档位量=Σcell、且 sourceDate/historical/fallback 正确
    payload = {
        "queue_ts": "2026-06-03T11:29:08.935+08:00",
        "askbrokerqueues": [{"gear": 819, "position": 819, "price": 710.5, "brokers": ["6389", "0"], "volumes": [60, 40]}],
        "bidbrokerqueues": [],
    }
    rows = flatten_broker_levels(payload)
    q = broker_queue_from_rows(rows, {}, effective_day="20260609")
    assert q["ask"][0]["position"] == 819 and q["ask"][0]["gear"] == 819
    assert q["ask"][0]["volume"] == 100 and q["ask"][0]["brokerCount"] == 2
    assert q["ask"][0]["brokers"][1]["displayName"] == "未披露"   # 码 0
    assert q["sourceDate"] == "20260603"
    assert q["historical"] is True and q["fallback"] is True       # 20260603 != 20260609


def test_flatten_is_defensive_on_empty_and_missing():
    assert flatten_broker_levels({"askbrokerqueues": [], "bidbrokerqueues": []}) == []
    # volumes 短于 brokers 时缺失补 0，不抛
    rows = flatten_broker_levels({"queue_ts": "2026-06-01T09:30:00+08:00",
                                  "askbrokerqueues": [{"gear": 5, "price": 10.0, "brokers": ["1", "2"], "volumes": [100]}]})
    assert rows[1]["volume"] == 0 and rows[0]["position"] == 5


def test_big_trade_alert_threshold_truncation_and_fallback():
    s = FakeState("02723.HK", baseline_volume=10_000_000)         # threshold=max(1,int(5000.0))=5000
    tick = {"id": "T1", "timestamp": "2026-06-09T10:00:00+08:00", "tradeDate": "20260609",
            "price": 350.0, "volume": 5000, "turnover": 1.75e6, "side": "buy", "brokerCode": "1234"}
    alert = big_trade_alert(s, tick)
    assert alert["thresholdVolume"] == 5000 and alert["id"] == "big-02723.HK-T1"
    assert alert["sourceDate"] == "20260609" and alert["thresholdRatio"] == 0.0005
    tick_small = {**tick, "volume": 4999}
    assert big_trade_alert(s, tick_small) is None                 # 低于阈值返回 None
    s0 = FakeState("X", baseline_volume=0)                        # baseline<=0 → 硬 fallback 1000
    assert big_trade_alert(s0, {**tick, "volume": 999})  is None
    assert big_trade_alert(s0, {**tick, "volume": 1000})["thresholdVolume"] == 1000


def test_merge_alert_dedup_by_id_and_cap_100():
    alerts = []
    a = {"id": "big-X-1"}
    merge_alert(alerts, a)
    merge_alert(alerts, dict(a))                                   # 同 id 不重复
    assert len(alerts) == 1
    for i in range(120):
        merge_alert(alerts, {"id": f"big-X-{i+2}"})
    assert len(alerts) == 100 and alerts[0]["id"] == "big-X-121"   # newest-first, cap 100


def test_filter_current_day_drops_stale():
    rows = [{"timestamp": "2026-06-09T10:00:00+08:00"}, {"timestamp": "2026-06-08T10:00:00+08:00"}]
    assert filter_current_day(rows, "20260609") == [rows[0]]


def test_upsert_bar_changed_detects_noop():
    bars = []
    bar = {"timestamp": "2026-06-09T09:30:00+08:00", "close": 1.0}
    assert upsert_bar_changed(bars, bar) is True
    assert upsert_bar_changed(bars, dict(bar)) is False           # 完全相同 → no-op
    assert upsert_bar_changed(bars, {**bar, "close": 2.0}) is True


def test_latest_daily_volume_keeps_latest_positive():
    df = pd.DataFrame([
        {"symbol": "02723.HK", "trade_date": 20260520, "volume": 100},
        {"symbol": "02723.HK", "trade_date": 20260521, "volume": 200},
        {"symbol": "X.HK", "trade_date": 20260521, "volume": 0},
    ])
    assert latest_daily_volume(df) == {"02723.HK": 200}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_transforms.py -q`
Expected: FAIL —— `ModuleNotFoundError: market_state_engine.transforms`

- [ ] **Step 3: 实现 `backend-project/src/market_state_engine/transforms.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd

from .models import now_iso

HK_TZ = timezone(timedelta(hours=8))


# ============ 候选专属纯函数 ============
def ms_to_hk_iso(value: Any) -> str:
    """epoch 时间戳 → Asia/Shanghai(+08:00) ISO，匹配参考实现的 bar_ts 形态。
    ⚠️ 按量级兼容秒/毫秒：本 lab 下 silver_store._timestamp_ms 在 pandas 3.0(datetime64[us]) 时
    实际产出 epoch 秒(10 位，如 1780992600)，pandas 2.2 时是毫秒(13 位)。1e12 边界干净区分
    （2026 秒≈1.78e9 < 1e12 ≤ 2026 毫秒≈1.78e12），故对 pandas 版本无关。"""
    v = int(value)
    seconds = v / 1000 if v >= 1_000_000_000_000 else v
    return datetime.fromtimestamp(seconds, tz=HK_TZ).isoformat(timespec="milliseconds")


def flatten_broker_levels(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把 SDK hkbrokerqueueex 的嵌套 level dict 还原成 broker_queue_from_rows 需要的扁平行。
    关键不变量：position 直接取 SDK 已派生的 gear（绝不重编号 0..N）；queue_ts 写到每一行（否则 sourceDate 丢失）。
    防御：缺失/空 side、volumes 短于 brokers、price/position 类型。"""
    rows: list[dict[str, Any]] = []
    qts = payload.get("queue_ts") or payload.get("timestamp") or ""
    for side in ("ask", "bid"):
        levels = payload.get(f"{side}brokerqueues") or payload.get(f"{side}Queues") or []
        for level in levels:
            try:
                pos = int(level.get("gear") or level.get("position") or 0)
                price = float(level.get("price") or 0.0)
            except (TypeError, ValueError):
                continue
            brokers = level.get("brokers") or []
            volumes = level.get("volumes") or []
            for i, code in enumerate(brokers):
                try:
                    vol = int(volumes[i]) if i < len(volumes) else 0
                except (TypeError, ValueError):
                    vol = 0
                rows.append({"side": side, "position": pos, "gear": pos, "price": price,
                             "broker_code": str(code), "volume": vol, "queue_ts": qts})
    return rows


def upsert_bar_changed(bars: list[dict[str, Any]], bar: dict[str, Any]) -> bool:
    """upsert_bar 的带「是否变更」返回值版本，用于 live 路径抑制回放 wraparound 的 no-op delta。"""
    for index, item in enumerate(bars):
        if item.get("timestamp") == bar["timestamp"]:
            if item == bar:
                return False
            bars[index] = bar
            return True
    bars.append(bar)
    bars.sort(key=lambda item: str(item.get("timestamp") or ""))
    del bars[:-420]
    return True


def latest_daily_volume(frame: pd.DataFrame) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in frame.sort_values("trade_date").to_dict("records"):
        symbol = str(row.get("symbol") or "").upper()
        try:
            volume = int(float(row.get("volume") or 0))
        except ValueError:
            volume = 0
        if symbol and volume > 0:
            result[symbol] = volume
    return result


# ============ 以下逐字复制自 mock-feed/src/market_mock_feed/server.py（保持逐字节同输出；
# 唯一例外：iso_from_any 的 digit 分支做了量级防御，对真实输入仍与参考逐字节一致） ============
def iso_from_any(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    text = str(value)
    if text and text != "nan":
        if text.isdigit():
            # 防御性：按量级兼容秒/毫秒（happy path 不会走到这里——adapter 已注入 bar_ts；
            # 仅在某条 1m 路径漏注入时兜底，避免把秒当毫秒回到 1970）。真·毫秒输入与参考逐字节一致。
            v = int(text)
            secs = v / 1000 if v >= 1_000_000_000_000 else v
            return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat(timespec="milliseconds")
        return text
    return ""


def trade_date_from_timestamp(value: Any) -> str:
    text = iso_from_any(value)
    return text[:10].replace("-", "") if len(text) >= 10 else ""


def compact_name(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("证券有限公司", "證券有限公司", "证券国际(香港)有限公司", "證券國際(香港)有限公司", "有限公司", "证券", "證券"):
        text = text.replace(suffix, "")
    return text[:8] or "未披露"


def minute_bar(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_from_any(row.get("bar_ts") or row.get("timestamp") or row.get("time"))
    close = float(row.get("close") or row.get("price") or 0.0)
    return {
        "timestamp": timestamp,
        "price": close,
        "open": float(row.get("open") or close),
        "high": float(row.get("high") or close),
        "low": float(row.get("low") or close),
        "close": close,
        "volume": int(float(row.get("volume") or 0)),
        "turnover": float(row.get("turnover") or row.get("amount") or 0.0),
    }


def trade_tick(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_from_any(row.get("tick_ts") or row.get("timestamp") or row.get("time"))
    return {
        "id": str(row.get("trade_id") or row.get("tradeID") or row.get("seq") or row.get("row_hash") or timestamp),
        "timestamp": timestamp,
        "tradeDate": trade_date_from_timestamp(timestamp),
        "price": float(row.get("price") or 0.0),
        "volume": int(float(row.get("volume") or row.get("qty") or 0)),
        "turnover": float(row.get("turnover") or row.get("amount") or 0.0),
        "side": str(row.get("side") or "neutral").lower(),
        "brokerCode": str(row.get("active_broker_code") or row.get("broker_code") or row.get("brokerNo") or ""),
    }


def queue_source_date(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        trade_date = trade_date_from_timestamp(row.get("queue_ts"))
        if trade_date:
            return trade_date
    return ""


def broker_queue_from_rows(rows: list[dict[str, Any]], brokers: dict[str, str], *, effective_day: str = "") -> dict[str, Any]:
    source_date = queue_source_date(rows)
    result: dict[str, Any] = {
        "ask": [],
        "bid": [],
        "sourceDate": source_date,
        "historical": bool(source_date and effective_day and source_date != effective_day),
        "fallback": bool(source_date and effective_day and source_date != effective_day),
    }
    if not rows:
        return result
    frame = pd.DataFrame(rows)
    for (side, price), group in frame.groupby(["side", "price"], sort=True):
        side_text = str(side).lower()
        position = int(float(group["position"].dropna().astype(float).min())) if "position" in group.columns and not group.empty else len(result.get(side_text, [])) + 1
        cells = []
        for row in group.to_dict("records"):
            code = str(row.get("broker_code") or "0")
            volume = int(float(row.get("volume") or 0))
            cells.append({"brokerCode": code, "displayName": brokers.get(code, code if code != "0" else "未披露"), "volume": volume})
        entry = {
            "id": f"{side_text}-{int(position)}-{float(price)}",
            "side": side_text,
            "position": int(position),
            "gear": int(position),
            "price": float(price),
            "volume": sum(item["volume"] for item in cells),
            "brokerCount": len(cells),
            "brokers": cells,
        }
        if side_text in result:
            result[side_text].append(entry)
    for side in ("ask", "bid"):
        result[side].sort(key=lambda item: int(item["position"]))
    return result


def filter_current_day(rows: list[dict[str, Any]], effective_day: str) -> list[dict[str, Any]]:
    if not effective_day:
        return rows
    filtered = []
    for row in rows:
        timestamp = row.get("timestamp") or row.get("updatedAt") or row.get("bar_ts") or row.get("tick_ts")
        if trade_date_from_timestamp(timestamp) == effective_day or row.get("tradeDate") == effective_day:
            filtered.append(row)
    return filtered


def update_quote_from_bar(state, bar: dict[str, Any]) -> None:
    quote = state.payload["snapshot"]
    quote.update(
        {
            "price": bar["close"],
            "open": bar["open"],
            "high": max(float(quote.get("high") or 0.0), bar["high"]),
            "low": bar["low"] if not quote.get("low") else min(float(quote["low"]), bar["low"]),
            "volume": sum(int(item.get("volume") or 0) for item in state.payload["minute_bars"]),
            "turnover": sum(float(item.get("turnover") or 0.0) for item in state.payload["minute_bars"]),
            "updatedAt": bar["timestamp"],
            "tradeDate": trade_date_from_timestamp(bar["timestamp"]),
        }
    )
    touch_freshness(state, bar["timestamp"], "minute_bars")


def update_quote_from_tick(state, tick: dict[str, Any]) -> None:
    quote = state.payload["snapshot"]
    quote["price"] = tick["price"]
    quote["updatedAt"] = tick["timestamp"]
    quote["tradeDate"] = tick["tradeDate"]


def upsert_bar(bars: list[dict[str, Any]], bar: dict[str, Any]) -> None:
    for index, item in enumerate(bars):
        if item.get("timestamp") == bar["timestamp"]:
            bars[index] = bar
            return
    bars.append(bar)
    bars.sort(key=lambda item: str(item.get("timestamp") or ""))
    del bars[:-420]


def big_trade_alert(state, tick: dict[str, Any]) -> dict[str, Any] | None:
    threshold = max(1, int(state.baseline_volume * 0.0005)) if state.baseline_volume > 0 else 1000
    if tick["volume"] < threshold:
        return None
    return {
        "id": f"big-{state.symbol}-{tick['id']}",
        "timestamp": tick["timestamp"],
        "tradeDate": tick["tradeDate"],
        "sourceDate": tick["tradeDate"],
        "historical": False,
        "source": "mock_hktransaction",
        "price": tick["price"],
        "volume": tick["volume"],
        "turnover": tick["turnover"],
        "side": tick["side"],
        "brokerCode": tick["brokerCode"],
        "thresholdVolume": threshold,
        "thresholdRatio": 0.0005,
        "baselineVolume": state.baseline_volume,
    }


def merge_alert(alerts: list[dict[str, Any]], alert: dict[str, Any]) -> None:
    if any(item.get("id") == alert.get("id") for item in alerts):
        return
    alerts.insert(0, alert)
    del alerts[100:]


def touch_freshness(state, timestamp: Any, key: str) -> None:
    state.payload["freshness"]["runtime_state"] = "LIVE"
    state.payload["freshness"].setdefault("source_dates", {})[key] = iso_from_any(timestamp) or str(timestamp or now_iso())


def empty_snapshot(symbol: str, name: str, effective_day: str = "") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "snapshot": {"symbol": symbol, "name": name, "currency": "HKD", "price": 0.0, "updatedAt": "", "tradeDate": effective_day},
        "minute_bars": [],
        "alerts": [],
        "broker_queue": {"ask": [], "bid": [], "sourceDate": "", "historical": False, "fallback": False},
        "freshness": {"runtime_state": "WARM", "effective_day": effective_day, "source_dates": {}},
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_transforms.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: 提交**

```bash
git add backend-project/src/market_state_engine/transforms.py backend-project/tests/test_transforms.py
git commit -m "feat(backend): transforms.py (reference transforms verbatim + flatten/localize/upsert-changed)"
```

---

## Task 2：adapters/xtquant_adapter.py（全部 xtdata 访问 + 两处 blocker 修复）

**Files:**
- Create: `backend-project/src/market_state_engine/adapters/xtquant_adapter.py`
- Test: `backend-project/tests/test_adapter.py`

修复点：`fetch_latest_queue_payload` 显式传 `field_list` 保住 `queue_ts`（否则 fallback 标记失效）；`fetch_minute_rows` 与 1m 订阅回调都注入 `bar_ts(+08:00)`；订阅断言 period 合法、解包 `{symbol:[payload]}` 的单元素 list。

- [ ] **Step 1: 写失败测试** `backend-project/tests/test_adapter.py`

```python
import time

from market_state_engine.adapters.xtquant_adapter import XtquantAdapter
from market_state_engine.transforms import flatten_broker_levels, broker_queue_from_rows, trade_date_from_timestamp
from market_state_engine.models import DEFAULT_SYMBOLS


def test_fetch_latest_queue_payload_retains_queue_ts():
    # 对抗评审 blocker：缺省 field_list 会丢 queue_ts，使 sourceDate 空、fallback 失效
    ad = XtquantAdapter(names={})
    payload = ad.fetch_latest_queue_payload("02723.HK")
    assert payload is not None
    assert payload.get("queue_ts") or payload.get("timestamp")
    rows = flatten_broker_levels(payload)
    q = broker_queue_from_rows(rows, {}, effective_day="20260609")
    assert q["sourceDate"] == "20260603"          # 02723.HK 的队列日
    assert q["historical"] is True and q["fallback"] is True


def test_hkbrokerqueueex_count_one_is_fast_for_default_symbols():
    # 镜像 test_contracts.py:14-20 的性能/数量契约
    ad = XtquantAdapter(names={})
    started = time.perf_counter()
    for symbol in DEFAULT_SYMBOLS:
        payload = ad.fetch_latest_queue_payload(symbol)
        assert payload is not None
    assert time.perf_counter() - started < 3.0


def test_fetch_minute_rows_localized_to_plus08():
    ad = XtquantAdapter(names={})
    rows = ad.fetch_minute_rows("02723.HK", count=60)
    assert rows
    assert all(r.get("bar_ts", "").endswith("+08:00") for r in rows)
    dates = {trade_date_from_timestamp(r["bar_ts"]) for r in rows}
    assert "20260609" in dates                      # 数据跨到 20260609


def test_fetch_daily_baseline_is_zero_via_xtdata_in_lab():
    # 本 lab xtdata 无 1d 周期，应返回 0（baseline 由 BaselineStore 的 CSV 兜底）
    ad = XtquantAdapter(names={})
    assert ad.fetch_daily_baseline("02723.HK") == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_adapter.py -q`
Expected: FAIL —— `ModuleNotFoundError: ...adapters.xtquant_adapter`

- [ ] **Step 3: 实现 `backend-project/src/market_state_engine/adapters/xtquant_adapter.py`**

```python
from __future__ import annotations

from typing import Any, Callable, Iterable

from xtquant import xtdata

from ..transforms import ms_to_hk_iso

LIVE_PERIODS = ("1m", "hktransaction", "hkbrokerqueueex")
# hkbrokerqueueex 缺省 field_list 会被裁成 ['time','askbrokerqueues','bidbrokerqueues']，丢掉 queue_ts。
# 显式带上 queue_ts/timestamp 才能保住 sourceDate / historical / fallback。
QUEUE_FIELDS = ["time", "queue_ts", "timestamp", "askbrokerqueues", "bidbrokerqueues"]


class XtquantAdapter:
    """唯一接触 xtquant 的层。hydrate 用 get_market_data_ex（count 有效），live 用 subscribe_quote。
    不知道 WS 帧、不知道 seq。回调极薄：只解包 {symbol:[payload]} 并交给注入的 sink。"""

    def __init__(self, *, names: dict[str, str]):
        self._names = names
        self._subs: dict[int, tuple[str, str]] = {}   # sub_id -> (symbol, period)

    # ---------- hydrate（历史，count 受限；subscribe 不能回填） ----------
    def fetch_minute_rows(self, symbol: str, *, count: int = 420) -> list[dict[str, Any]]:
        data = xtdata.get_market_data_ex([], [symbol], period="1m", count=count)
        df = data.get(symbol)
        if df is None or len(df) == 0:
            return []
        rows: list[dict[str, Any]] = []
        for record in df.to_dict("records"):
            if not record.get("bar_ts") and record.get("time") is not None:
                record["bar_ts"] = ms_to_hk_iso(record["time"])   # 修复：SDK 1m 只有 epoch 整数(本 lab 为秒)，按量级本地化为 +08:00
            rows.append(record)
        return rows

    def fetch_latest_queue_payload(self, symbol: str) -> dict[str, Any] | None:
        data = xtdata.get_market_data_ex(QUEUE_FIELDS, [symbol], period="hkbrokerqueueex", count=1)
        df = data.get(symbol)
        if df is None or len(df) == 0:
            return None
        return df.iloc[-1].to_dict()

    def fetch_daily_baseline(self, symbol: str) -> int:
        # 先尝试 SDK（本 lab 无 1d 周期 → {} → 0）；BaselineStore 的 CSV 是真正的 baseline 主源。
        try:
            data = xtdata.get_market_data_ex([], [symbol], period="1d", count=1)
        except Exception:
            return 0
        df = data.get(symbol)
        if df is None or len(df) == 0:
            return 0
        try:
            return int(float(df.iloc[-1].get("volume") or 0))
        except (TypeError, ValueError):
            return 0

    # ---------- live ----------
    def subscribe(self, symbol: str, period: str, sink: "Callable[[str, str, dict], None]") -> int:
        assert period in LIVE_PERIODS, f"非法 period: {period}"

        def _cb(message: dict, period: str = period, symbol: str = symbol) -> None:
            # 在 daemon 后台线程上触发：只解包并转交，绝不碰 asyncio 对象
            bucket = message.get(symbol) or next(iter(message.values()), [])
            for payload in bucket:
                if period == "1m" and not payload.get("bar_ts") and payload.get("time") is not None:
                    payload["bar_ts"] = ms_to_hk_iso(payload["time"])
                sink(period, symbol, payload)

        sub_id = xtdata.subscribe_quote(symbol, period=period, callback=_cb)
        self._subs[sub_id] = (symbol, period)
        return sub_id

    def unsubscribe(self, sub_id: int) -> None:
        xtdata.unsubscribe_quote(sub_id)
        self._subs.pop(sub_id, None)

    def unsubscribe_symbol_subs(self, sub_ids: Iterable[int]) -> None:
        for sub_id in list(sub_ids):
            self.unsubscribe(sub_id)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_adapter.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
git add backend-project/src/market_state_engine/adapters/xtquant_adapter.py backend-project/tests/test_adapter.py
git commit -m "feat(backend): xtquant_adapter with queue_ts retention + 1m bar_ts localization fixes"
```

---

## Task 3：state/engine.py（状态机 + BaselineStore）—— 核心

**Files:**
- Create: `backend-project/src/market_state_engine/state/engine.py`
- Test: `backend-project/tests/test_engine_contract.py`

要点：`BaselineStore` 读三个 CSV（baseline 主源 + 券商名 + 标的名，**唯一非 SDK 读取**）；`MarketStateEngine.__init__(symbols, adapter=None, store=None)` 保 `test_smoke` 单参兼容；`hydrate_symbol` 顺序严格镜像参考（先 minute 滚 quote → filter_current_day → broker_queue 最后），**末尾复位 runtime_state='WARM' 并写 mock_rows**；`apply` 内三处 effective-day 隔离 + 变更检测抑制回放 no-op；`resume_since` 三态；onboard 拆成 prepare/hydrate/start_live 三步以消除竞态。

- [ ] **Step 1: 写失败测试** `backend-project/tests/test_engine_contract.py`

```python
import os

from market_state_engine.state.engine import MarketStateEngine, BaselineStore
from market_state_engine.adapters.xtquant_adapter import XtquantAdapter
from market_state_engine.models import DEFAULT_SYMBOLS
from market_state_engine.transforms import trade_date_from_timestamp


def build_engine(symbols):
    store = BaselineStore().load()
    engine = MarketStateEngine(list(symbols), XtquantAdapter(names=store.names), store)
    engine.hydrate()
    return engine


def test_hydrate_is_warm_with_mock_rows():
    # test_smoke 的强约束：hydrate 后 runtime_state 必须 WARM（不能被 touch_freshness 漏成 LIVE），mock_rows.minute_bars>0
    engine = build_engine(["02723.HK"])
    payload = engine.snapshots["02723.HK"].payload
    assert payload["freshness"]["runtime_state"] == "WARM"
    assert payload["freshness"]["mock_rows"]["minute_bars"] > 0


def test_candidate_snapshot_effective_day_contract():
    # 镜像 test_contracts.py:23-40，但跑在【候选引擎】上（test_contracts 只校验参考实现）
    engine = build_engine(DEFAULT_SYMBOLS)
    for symbol in DEFAULT_SYMBOLS:
        payload = engine.snapshot_frame(symbol)["payload"]
        effective_day = payload["snapshot"]["tradeDate"]
        assert effective_day
        assert payload["freshness"]["effective_day"] == effective_day
        assert {b["timestamp"][:10].replace("-", "") for b in payload["minute_bars"]} == {effective_day}
        assert {a["tradeDate"] for a in payload["alerts"]} <= {effective_day}
        q = payload["broker_queue"]
        assert set(q) >= {"ask", "bid", "sourceDate", "historical", "fallback"}
        if q["sourceDate"] and q["sourceDate"] != effective_day:
            assert q["historical"] is True and q["fallback"] is True


def test_broker_queue_fallback_flags_for_02723():
    engine = build_engine(["02723.HK"])
    q = engine.snapshots["02723.HK"].payload["broker_queue"]
    assert q["sourceDate"] == "20260603"          # 队列日 != effective_day(20260609)
    assert q["historical"] is True and q["fallback"] is True


def test_apply_drops_off_effective_day_event():
    engine = build_engine(["02723.HK"])
    st = engine.snapshots["02723.HK"]
    before = st.seq
    stale = {"time": 0, "bar_ts": "2025-01-01T09:30:00+08:00", "close": 1.0, "open": 1.0, "high": 1.0, "low": 1.0, "volume": 1, "amount": 1.0}
    assert engine.apply("1m", "02723.HK", stale) is None          # 旧日事件被丢
    assert st.seq == before                                       # 不 bump seq


def test_apply_broker_queue_full_overwrite_never_accumulate():
    engine = build_engine(["02723.HK"])
    st = engine.snapshots["02723.HK"]
    eff = st.effective_day
    p1 = {"queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:00+08:00",
          "askbrokerqueues": [{"gear": 1, "price": 10.0, "brokers": ["1"], "volumes": [100]}], "bidbrokerqueues": []}
    p2 = {"queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:01+08:00",
          "askbrokerqueues": [{"gear": 2, "price": 10.1, "brokers": ["2"], "volumes": [200]}], "bidbrokerqueues": []}
    engine.apply("hkbrokerqueueex", "02723.HK", p1)
    engine.apply("hkbrokerqueueex", "02723.HK", p2)
    ask = st.payload["broker_queue"]["ask"]
    assert len(ask) == 1 and ask[0]["position"] == 2 and ask[0]["volume"] == 200   # 覆盖，非累加


def test_apply_seq_monotonic_and_suppresses_noop():
    engine = build_engine(["02723.HK"])
    st = engine.snapshots["02723.HK"]
    eff = st.effective_day
    p = {"queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:00+08:00",
         "askbrokerqueues": [{"gear": 1, "price": 10.0, "brokers": ["1"], "volumes": [100]}], "bidbrokerqueues": []}
    f1 = engine.apply("hkbrokerqueueex", "02723.HK", p)
    s1 = st.seq
    f2 = engine.apply("hkbrokerqueueex", "02723.HK", dict(p))      # 同 queue_ts → no-op
    assert f1["seq"] == s1 and f2 is None and st.seq == s1         # seq 不膨胀
```

- [ ] **Step 2: 跑测试确认失败**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_engine_contract.py -q`
Expected: FAIL —— `ModuleNotFoundError: ...state.engine`

- [ ] **Step 3: 实现 `backend-project/src/market_state_engine/state/engine.py`**

```python
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import pandas as pd

from ..adapters.xtquant_adapter import XtquantAdapter
from ..models import SymbolState, frame
from ..transforms import (
    broker_queue_from_rows, big_trade_alert, compact_name, empty_snapshot,
    filter_current_day, flatten_broker_levels, latest_daily_volume, merge_alert,
    minute_bar, now_iso, touch_freshness, trade_date_from_timestamp, trade_tick,
    update_quote_from_bar, update_quote_from_tick, upsert_bar, upsert_bar_changed,
)


class BaselineStore:
    """唯一的非 SDK 读取：baseline 日量 + 券商名映射 + 标的名。
    因为 xtdata mock 不暴露这些（无 1d 周期、get_instrument_detail 返回 {}），
    与参考实现的 SampleDataStore 同源（sample-data/*.csv）。"""

    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(root or os.getenv("XTMOCK_SILVER_ROOT", "sample-data"))
        self.names: dict[str, str] = {}
        self.brokers: dict[str, str] = {}
        self._baseline: dict[str, int] = {}

    def load(self) -> "BaselineStore":
        instruments = pd.read_csv(self.root / "silver_instruments_v1.csv")
        self.names = {
            str(r["symbol"]).upper(): str(r["name"])
            for r in instruments.to_dict("records") if str(r.get("symbol") or "").strip()
        }
        mapping = pd.read_csv(self.root / "silver_broker_mapping_v1.csv")
        self.brokers = {
            str(r["broker_code"]).strip(): compact_name(r.get("participant_name") or r.get("broker_name"))
            for r in mapping.to_dict("records") if str(r.get("broker_code") or "").strip()
        }
        daily = pd.read_csv(self.root / "silver_daily_bars_v1.csv")   # 63 行 OHLCV，front/back baseline，勿混 research-data
        self._baseline = latest_daily_volume(daily)
        return self

    def baseline_for(self, symbol: str) -> int:
        return self._baseline.get(symbol.upper(), 0)


class MarketStateEngine:
    """per-symbol 状态机，与传输层彻底解耦。apply() 在单写者（loop 线程）调用，
    变更 payload、bump per-symbol seq、append delta 环形缓冲，并返回 delta 帧给 gateway 广播。
    effective-day 隔离只在此层。"""

    def __init__(self, symbols: list[str], adapter: XtquantAdapter | None = None, store: BaselineStore | None = None):
        # test_smoke: MarketStateEngine(['02723.HK']) 单参 → 默认构造 store+adapter
        if store is None:
            store = BaselineStore().load()
        if adapter is None:
            adapter = XtquantAdapter(names=store.names)
        self.adapter = adapter
        self.store = store
        self.snapshots: dict[str, SymbolState] = {}   # 名字保留为 snapshots 以兼容 test_smoke
        self._global_lock = threading.Lock()          # 守护 snapshots 字典结构（onboard/offboard）
        for symbol in symbols:
            self._init_state(symbol)

    # ---------- 构造 / effective-day ----------
    def _init_state(self, symbol: str) -> SymbolState:
        name = self.store.names.get(symbol, symbol)
        baseline = self.store.baseline_for(symbol)
        eff = os.getenv("MARKET_EFFECTIVE_DAY", "").strip().replace("-", "")  # 覆盖优先；否则 hydrate 时按 max 日定
        st = SymbolState(symbol=symbol, name=name, baseline_volume=baseline, effective_day=eff)
        self.snapshots[symbol] = st
        return st

    def _effective_day_from_rows(self, rows: list[dict[str, Any]]) -> str:
        configured = os.getenv("MARKET_EFFECTIVE_DAY", "").strip()
        if configured:
            return configured.replace("-", "")
        dates = {d for d in (trade_date_from_timestamp(r.get("bar_ts") or r.get("timestamp") or r.get("time")) for r in rows) if d}
        return max(dates) if dates else ""

    # ---------- hydrate（阻塞 I/O；boot 前调用安全，onboard 经 executor 卸载） ----------
    def hydrate(self) -> None:
        for symbol in list(self.snapshots):
            self.hydrate_symbol(symbol)

    def hydrate_symbol(self, symbol: str) -> None:
        st = self.snapshots[symbol]
        rows = self.adapter.fetch_minute_rows(symbol, count=420)   # 阻塞读，放锁外
        eff = self._effective_day_from_rows(rows)
        queue_payload = self.adapter.fetch_latest_queue_payload(symbol)
        with st.lock:
            st.effective_day = eff
            st.payload = empty_snapshot(symbol, st.name, eff)
            for row in rows:
                bar = minute_bar(row)
                if trade_date_from_timestamp(bar["timestamp"]) != eff:  # hydrate 期日 guard
                    continue
                upsert_bar(st.payload["minute_bars"], bar)
                update_quote_from_bar(st, bar)                          # 注意：这里会把 runtime_state 置 LIVE
            st.payload["alerts"] = filter_current_day(st.payload["alerts"], eff)
            st.payload["minute_bars"] = filter_current_day(st.payload["minute_bars"], eff)
            queue_rows = flatten_broker_levels(queue_payload) if queue_payload else []
            st.payload["broker_queue"] = broker_queue_from_rows(queue_rows, self.store.brokers, effective_day=eff)
            # —— hydrate 收尾：复位 WARM（水合不是 live）+ 写 mock_rows（test_smoke 需要）——
            st.payload["freshness"]["runtime_state"] = "WARM"
            st.payload["freshness"]["effective_day"] = eff
            st.payload["freshness"]["source_dates"] = {}
            st.payload["freshness"]["mock_rows"] = {
                "minute_bars": len(st.payload["minute_bars"]),
                "broker_queue": len(st.payload["broker_queue"]["ask"]) + len(st.payload["broker_queue"]["bid"]),
            }
            st.base_seq = st.seq            # snapshot 现反映 seq=base_seq（seq 本身不回退）
            st.deltas.clear()
            st.seen_tick_ids.clear()
            st.last_queue_ts = ""

    # ---------- live apply（单写者；effective-day 隔离 + 回放变更检测） ----------
    def apply(self, period: str, symbol: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        st = self.snapshots.get(symbol)
        if st is None:
            return None
        with st.lock:
            if period == "1m":
                bar = minute_bar(payload)
                if trade_date_from_timestamp(bar["timestamp"]) != st.effective_day:
                    return None                                    # effective-day 隔离
                if not upsert_bar_changed(st.payload["minute_bars"], bar):
                    return None                                    # 回放 wraparound 同 bar → 不发 delta/不 bump seq
                update_quote_from_bar(st, bar)
                body = {"delta_type": "minute_bar", "minute_bar": bar}
            elif period == "hktransaction":
                tick = trade_tick(payload)
                if tick["tradeDate"] != st.effective_day:
                    return None                                    # effective-day 隔离
                if tick["id"] in st.seen_tick_ids:
                    return None                                    # 重复 tick（wraparound）
                st.seen_tick_ids.add(tick["id"])
                update_quote_from_tick(st, tick)                   # 仅更新 price/updatedAt/tradeDate
                alert = big_trade_alert(st, tick)
                if alert is not None:
                    merge_alert(st.payload["alerts"], alert)       # 按 id 去重
                    touch_freshness(st, alert["timestamp"], "alerts")
                body = {"delta_type": "trade_tick", "tick": tick, "alert": alert}
            elif period == "hkbrokerqueueex":
                qts = payload.get("queue_ts") or payload.get("timestamp") or ""
                if qts and qts == st.last_queue_ts:
                    return None                                    # 同快照重发 → 抑制
                st.last_queue_ts = qts
                queue = broker_queue_from_rows(flatten_broker_levels(payload), self.store.brokers, effective_day=st.effective_day)
                st.payload["broker_queue"] = queue                 # 整快照覆盖，绝不累加
                touch_freshness(st, qts or now_iso(), "broker_queue")
                body = {"delta_type": "broker_queue", "broker_queue": queue}
            else:
                return None
            st.seq += 1
            delta = frame("delta", symbol=symbol, seq=st.seq, payload=body)
            st.deltas.append(delta)
            return delta

    # ---------- 读 ----------
    def snapshot_frame(self, symbol: str) -> dict[str, Any] | None:
        st = self.snapshots.get(symbol)
        if st is None:
            return None
        with st.lock:
            return frame("snapshot", symbol=symbol, seq=max(1, st.seq), payload=st.payload)

    def resume_since(self, symbol: str, last_seq: int) -> tuple[str, list[dict[str, Any]]]:
        st = self.snapshots.get(symbol)
        if st is None:
            return ("snapshot", [])
        with st.lock:
            if last_seq >= st.seq:
                return ("deltas", [])                              # 客户端已最新
            oldest = st.deltas[0]["seq"] if st.deltas else st.seq + 1
            if last_seq >= st.base_seq and last_seq + 1 >= oldest:  # 连续且不落后于快照地板
                return ("deltas", [f for f in st.deltas if f["seq"] > last_seq])
            return ("snapshot", [frame("snapshot", symbol=symbol, seq=max(1, st.seq), payload=st.payload)])

    # ---------- live 订阅 ----------
    def start_live(self, bridge) -> None:
        for symbol in list(self.snapshots):
            self.start_live_symbol(symbol, bridge)

    def start_live_symbol(self, symbol: str, bridge) -> None:
        st = self.snapshots[symbol]
        st.sub_ids = {p: self.adapter.subscribe(symbol, p, bridge.make_sink()) for p in ("1m", "hktransaction", "hkbrokerqueueex")}

    def stop_live(self) -> None:
        for st in self.snapshots.values():
            self.adapter.unsubscribe_symbol_subs(st.sub_ids.values())
            st.sub_ids = {}

    # ---------- 动态 onboard / offboard（拆三步消竞态） ----------
    def prepare_onboard(self, symbol: str) -> bool:
        with self._global_lock:
            if symbol in self.snapshots:
                return False
            self._init_state(symbol)
            return True

    def offboard(self, symbol: str) -> None:
        with self._global_lock:
            st = self.snapshots.pop(symbol, None)
        if st:
            self.adapter.unsubscribe_symbol_subs(st.sub_ids.values())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_engine_contract.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 确认既有 test_smoke 仍通过（接口兼容回归）**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_smoke.py -q`
Expected: FAIL —— test_smoke 仍 import 旧骨架 `MarketStateEngine`（在 `app.py`）。Task 6 会把 `app.py` 改为回出口新 engine 后转 PASS。此处只需确认引擎本体逻辑正确（test_engine_contract 已覆盖 WARM+mock_rows）。

- [ ] **Step 6: 提交**

```bash
git add backend-project/src/market_state_engine/state/engine.py backend-project/tests/test_engine_contract.py
git commit -m "feat(backend): state engine + BaselineStore (effective-day isolation, full-overwrite, seq, noop-suppression)"
```

---

## Task 4：bridge.py（daemon 线程 → asyncio 单写者）

**Files:**
- Create: `backend-project/src/market_state_engine/bridge.py`
- Test: `backend-project/tests/test_bridge.py`

机制：`loop.call_soon_threadsafe` 是唯一线程安全调度原语；让 loop 线程成为**唯一写者**，per-symbol 顺序天然保持、seq 无竞态。`sink` 包 `try/except RuntimeError` 吞掉「loop 正在关闭」的 TOCTOU。

- [ ] **Step 1: 写失败测试** `backend-project/tests/test_bridge.py`

```python
import asyncio

from market_state_engine.bridge import ThreadAsyncBridge


class FakeEngine:
    def __init__(self):
        self.calls = []
    def apply(self, period, symbol, payload):
        self.calls.append((period, symbol, payload))
        return {"type": "delta", "symbol": symbol, "seq": len(self.calls)}


def test_sink_routes_through_loop_and_enqueues():
    async def main():
        engine = FakeEngine()
        bridge = ThreadAsyncBridge(engine)
        bridge.bind(asyncio.get_running_loop())
        sink = bridge.make_sink()
        sink("1m", "02723.HK", {"x": 1})          # 模拟 daemon 线程调用（此处同线程，但走 call_soon_threadsafe）
        await asyncio.sleep(0.05)                  # 让 call_soon 回调跑
        frame = await asyncio.wait_for(bridge.aqueue.get(), timeout=1.0)
        assert frame["symbol"] == "02723.HK" and frame["seq"] == 1
        assert engine.calls == [("1m", "02723.HK", {"x": 1})]
    asyncio.run(main())


def test_sink_noop_when_loop_unbound_or_closed():
    engine = FakeEngine()
    bridge = ThreadAsyncBridge(engine)
    sink = bridge.make_sink()                      # 未 bind，loop is None
    sink("1m", "X", {})                            # 不抛
    assert engine.calls == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_bridge.py -q`
Expected: FAIL —— `ModuleNotFoundError: ...bridge`

- [ ] **Step 3: 实现 `backend-project/src/market_state_engine/bridge.py`**

```python
from __future__ import annotations

import asyncio
from typing import Any, Callable


class ThreadAsyncBridge:
    """SDK 在每订阅各自的 daemon 线程触发回调；WS 跑单 asyncio loop。
    用 call_soon_threadsafe 把执行交回 loop 线程（唯一写者），apply 在那里跑、seq 在那里分配 → 无竞态、顺序天然保持。
    apply 产出的 delta 帧推入 asyncio.Queue，由 gateway 排空广播，从而把状态变更与慢客户端的网络扇出解耦。"""

    def __init__(self, engine):
        self.engine = engine
        self.loop: asyncio.AbstractEventLoop | None = None
        self.aqueue: "asyncio.Queue[dict]" | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        # 在 run_server 内、loop 跑起来后调用一次
        self.loop = loop
        self.aqueue = asyncio.Queue()

    def make_sink(self) -> "Callable[[str, str, dict], None]":
        loop = self.loop

        def sink(period: str, symbol: str, payload: dict[str, Any]) -> None:
            # 运行在 SDK daemon 线程：绝不直接碰 asyncio 对象
            if loop is None or loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(self._on_loop, period, symbol, payload)
            except RuntimeError:
                return    # loop 关闭中的 TOCTOU：吞掉，别让 daemon 线程抛栈

        return sink

    def _on_loop(self, period: str, symbol: str, payload: dict[str, Any]) -> None:
        # 运行在 loop 线程（单写者）
        delta = self.engine.apply(period, symbol, payload)
        if delta is not None and self.aqueue is not None:
            self.aqueue.put_nowait(delta)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_bridge.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
git add backend-project/src/market_state_engine/bridge.py backend-project/tests/test_bridge.py
git commit -m "feat(backend): ThreadAsyncBridge (call_soon_threadsafe single-writer, shutdown-safe sink)"
```

---

## Task 5：gateway/ws.py（WS 协议 + 并发广播 + error/resume/onboard）

**Files:**
- Create: `backend-project/src/market_state_engine/gateway/ws.py`
- Test: `backend-project/tests/test_gateway.py`

要点：连接发 hello+heartbeat；每命令先 ack；`snapshot_request/visible_set/watchlist_set` 回逐 symbol snapshot；`health_request` 回 heartbeat；`resume_request` 走 `resume_since`；`onboard_request` 先把 snapshot 发给请求方再订阅、并广播更新后的 hello；坏 JSON / 未知命令 → error 帧；广播用 `asyncio.gather` 并发，一个慢客户端不拖垮全体。

- [ ] **Step 1: 写失败测试** `backend-project/tests/test_gateway.py`

```python
import asyncio
import json

from market_state_engine.gateway.ws import Gateway


class FakeWS:
    def __init__(self, incoming=None):
        self.sent = []
        self._incoming = list(incoming or [])
    async def send(self, raw):
        self.sent.append(json.loads(raw))
    def __aiter__(self):
        self._it = iter(self._incoming)
        return self
    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeEngine:
    def __init__(self):
        self.snapshots = {"02723.HK": object()}
    def snapshot_frame(self, symbol):
        if symbol not in self.snapshots:
            return None
        return {"type": "snapshot", "symbol": symbol, "seq": 1, "payload": {"symbol": symbol}}
    def resume_since(self, symbol, last_seq):
        return ("deltas", [{"type": "delta", "symbol": symbol, "seq": last_seq + 1}])


def types(ws):
    return [m["type"] for m in ws.sent]


def run(coro):
    return asyncio.run(coro)


def test_hello_then_heartbeat_then_ack_snapshot():
    ws = FakeWS([json.dumps({"command": "snapshot_request", "request_id": "r1", "symbols": ["02723.HK"]})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "snapshot"]
    assert ws.sent[2]["payload"] == {"command": "snapshot_request", "accepted": True}
    assert ws.sent[3]["symbol"] == "02723.HK"


def test_health_request_returns_heartbeat():
    ws = FakeWS([json.dumps({"command": "health_request", "request_id": "h1"})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "heartbeat"]
    assert ws.sent[-1]["request_id"] == "h1" and ws.sent[-1]["payload"] == {"ready": True}


def test_bad_json_returns_error():
    ws = FakeWS(["{not json"])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "error"]
    assert ws.sent[-1]["payload"]["code"] == "bad_json"


def test_unknown_command_returns_error():
    ws = FakeWS([json.dumps({"command": "frobnicate", "request_id": "x"})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "error"]
    assert ws.sent[-1]["payload"]["code"] == "unknown_command"


def test_resume_request_streams_deltas():
    ws = FakeWS([json.dumps({"command": "resume_request", "request_id": "r", "symbols": ["02723.HK"], "cursors": {"02723.HK": 5}})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "delta"]
    assert ws.sent[-1]["seq"] == 6
```

- [ ] **Step 2: 跑测试确认失败**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_gateway.py -q`
Expected: FAIL —— `ModuleNotFoundError: ...gateway.ws`

- [ ] **Step 3: 实现 `backend-project/src/market_state_engine/gateway/ws.py`**

```python
from __future__ import annotations

import asyncio
import json
from typing import Any

from ..models import frame


class Gateway:
    """WS 协议层（asyncio）。拥有 client 集合，连接握手，命令分发，并发广播。
    从 bridge.aqueue 取现成 delta 帧扇出。不碰 xtquant、不碰业务数学。"""

    def __init__(self, engine, bridge):
        self.engine = engine
        self.bridge = bridge
        self.clients: set[Any] = set()

    async def handle_client(self, ws) -> None:
        self.clients.add(ws)
        try:
            await self._send(ws, frame("hello", payload={"symbols": list(self.engine.snapshots)}))
            await self._send(ws, frame("heartbeat", payload={"ready": True}))
            async for raw in ws:
                try:
                    command = json.loads(raw)
                except Exception:
                    await self._send(ws, frame("error", payload={"code": "bad_json", "message": "invalid JSON"}))
                    continue
                await self._dispatch(ws, command)
        finally:
            self.clients.discard(ws)

    async def _dispatch(self, ws, command: dict[str, Any]) -> None:
        request_id = str(command.get("request_id") or "")
        name = str(command.get("command") or "")
        symbols = [str(s).upper() for s in command.get("symbols", []) if str(s).strip()] or list(self.engine.snapshots)
        await self._send(ws, frame("ack", request_id=request_id, payload={"command": name, "accepted": True}))

        if name in {"snapshot_request", "visible_set", "watchlist_set"}:
            for symbol in symbols:                              # visible_set 仅请求快照，不改 universe、不 re-hydrate
                snap = self.engine.snapshot_frame(symbol)
                if snap is not None:
                    await self._send(ws, snap)
        elif name == "health_request":
            await self._send(ws, frame("heartbeat", request_id=request_id, payload={"ready": True}))
        elif name == "resume_request":
            cursors = command.get("cursors") or {}
            for symbol in symbols:
                last = int(cursors.get(symbol, command.get("last_seq", 0)) or 0)
                _kind, frames = self.engine.resume_since(symbol, last)
                for fr in frames:
                    await self._send(ws, fr)
        elif name == "onboard_request":
            await self._onboard(ws, symbols)
        else:
            await self._send(ws, frame("error", payload={"code": "unknown_command", "message": name, "request_id": request_id}))

    async def _onboard(self, ws, symbols: list[str]) -> None:
        loop = asyncio.get_running_loop()
        changed = False
        for symbol in symbols:
            if self.engine.prepare_onboard(symbol):
                # 阻塞 xtdata 读卸到 executor，避免冻结事件循环
                await loop.run_in_executor(None, self.engine.hydrate_symbol, symbol)
                snap = self.engine.snapshot_frame(symbol)
                if snap is not None:
                    await self._send(ws, snap)                 # 请求方先拿到 snapshot，再开 live（消竞态）
                self.engine.start_live_symbol(symbol, self.bridge)
                changed = True
            else:
                snap = self.engine.snapshot_frame(symbol)
                if snap is not None:
                    await self._send(ws, snap)
        if changed:                                            # 通知所有客户端 universe 变化
            await self.broadcast(frame("hello", payload={"symbols": list(self.engine.snapshots)}))

    async def run_broadcast_loop(self) -> None:
        assert self.bridge is not None and self.bridge.aqueue is not None
        while True:
            delta = await self.bridge.aqueue.get()
            await self.broadcast(delta)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.clients:
            return
        encoded = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(*(self._safe_send(c, encoded) for c in list(self.clients)), return_exceptions=True)

    async def _safe_send(self, ws, encoded: str) -> None:
        try:
            await ws.send(encoded)
        except Exception:
            self.clients.discard(ws)

    async def _send(self, ws, message: dict[str, Any]) -> None:
        await ws.send(json.dumps(message, ensure_ascii=False))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_gateway.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 提交**

```bash
git add backend-project/src/market_state_engine/gateway/ws.py backend-project/tests/test_gateway.py
git commit -m "feat(backend): WS gateway (hello/ack/snapshot/delta/error/resume/onboard, concurrent broadcast)"
```

---

## Task 6：app.py（composition root + 回出口，恢复既有测试）

**Files:**
- Modify: `backend-project/src/market_state_engine/app.py`（整文件替换）
- Test: `backend-project/tests/test_smoke.py`（既有）、`backend-project/tests/test_contracts.py`（既有）

`app.py` 必须保持 `from market_state_engine.app import frame`（test_contracts）与 `from market_state_engine.app import MarketStateEngine`（test_smoke）可 import，且 `frame` 的 `source=='candidate-backend'`。

- [ ] **Step 1: 替换 `backend-project/src/market_state_engine/app.py`**

```python
from __future__ import annotations

import asyncio
import os

import websockets

# 回出口，保持既有测试 import 不变：
from .models import frame, now_iso, DEFAULT_SYMBOLS, SCHEMA_VERSION, PROTOCOL, SymbolState  # noqa: F401
from .state.engine import MarketStateEngine, BaselineStore
from .adapters.xtquant_adapter import XtquantAdapter
from .bridge import ThreadAsyncBridge
from .gateway.ws import Gateway


def parse_symbols() -> list[str]:
    raw = os.getenv("MARKET_SYMBOLS", ",".join(DEFAULT_SYMBOLS))
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def build_engine(symbols: list[str]) -> tuple[MarketStateEngine, XtquantAdapter, BaselineStore]:
    store = BaselineStore().load()
    adapter = XtquantAdapter(names=store.names)
    engine = MarketStateEngine(symbols, adapter, store)
    return engine, adapter, store


async def run_server(host: str = "0.0.0.0", port: int = 9031) -> None:
    engine, _adapter, _store = build_engine(parse_symbols())
    bridge = ThreadAsyncBridge(engine)
    gateway = Gateway(engine, bridge)

    loop = asyncio.get_running_loop()
    bridge.bind(loop)                 # 捕获 loop（必须在 start_live 前）
    engine.hydrate()                  # boot 期阻塞读 OK（尚未 serve）
    engine.start_live(bridge)         # 启动 15 个 daemon 订阅（5 symbol × 3 period）
    asyncio.create_task(gateway.run_broadcast_loop())

    async with websockets.serve(lambda ws: gateway.handle_client(ws), host, port):
        print(f"candidate backend listening on ws://{host}:{port}/ws", flush=True)
        try:
            await asyncio.Future()
        finally:
            engine.stop_live()        # 协作式停 daemon（unsubscribe 置 stop_event）


def main() -> int:
    asyncio.run(run_server())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 跑既有两个测试确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_smoke.py backend-project/tests/test_contracts.py -q`
Expected: PASS（test_smoke：1 passed；test_contracts：4 passed）

> test_smoke 现 import 新 `MarketStateEngine`（单参构造→默认 store/adapter；hydrate 后 WARM + mock_rows.minute_bars>0）。test_contracts 的 `frame` 仍来自 app（source=candidate-backend）。

- [ ] **Step 3: 提交**

```bash
git add backend-project/src/market_state_engine/app.py
git commit -m "feat(backend): app.py composition root + re-exports (test_smoke/test_contracts pass)"
```

---

## Task 7：reconnect + 集成测试（resume 三态 / seq 不回退 / 端到端）

**Files:**
- Test: `backend-project/tests/test_reconnect.py`
- Test: `backend-project/tests/test_integration_live.py`

纯验证任务（无新源码）。`test_integration_live` 设 `XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION` 限制回放，驱动真实 subscribe→bridge→apply→broadcast。

- [ ] **Step 1: 写 `backend-project/tests/test_reconnect.py`**

```python
import os

from market_state_engine.state.engine import MarketStateEngine, BaselineStore
from market_state_engine.adapters.xtquant_adapter import XtquantAdapter


def fresh_engine():
    store = BaselineStore().load()
    engine = MarketStateEngine(["02723.HK"], XtquantAdapter(names=store.names), store)
    engine.hydrate()
    return engine


def push_queue_events(engine, n):
    st = engine.snapshots["02723.HK"]
    eff = st.effective_day
    for i in range(n):
        engine.apply("hkbrokerqueueex", "02723.HK", {
            "queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:{i:02d}+08:00",
            "askbrokerqueues": [{"gear": 1, "price": 10.0 + i, "brokers": ["1"], "volumes": [100 + i]}],
            "bidbrokerqueues": [],
        })


def test_resume_within_buffer_returns_deltas():
    engine = fresh_engine()
    push_queue_events(engine, 5)
    kind, frames = engine.resume_since("02723.HK", 2)
    assert kind == "deltas"
    assert [f["seq"] for f in frames] == [3, 4, 5]


def test_resume_already_current_returns_empty():
    engine = fresh_engine()
    push_queue_events(engine, 3)
    kind, frames = engine.resume_since("02723.HK", 3)
    assert kind == "deltas" and frames == []


def test_resume_beyond_buffer_returns_snapshot():
    engine = fresh_engine()
    push_queue_events(engine, 600)            # > DELTA_RING_CAPACITY(512)
    kind, frames = engine.resume_since("02723.HK", 1)
    assert kind == "snapshot"
    assert frames and frames[0]["type"] == "snapshot"


def test_seq_never_resets_on_rehydrate_day_switch(monkeypatch):
    engine = fresh_engine()
    push_queue_events(engine, 4)
    st = engine.snapshots["02723.HK"]
    seq_before = st.seq
    # 强制切到另一交易日并重新水合
    monkeypatch.setenv("MARKET_EFFECTIVE_DAY", "20260608")
    engine.hydrate_symbol("02723.HK")
    assert st.seq == seq_before                # seq 单调，绝不回退
    assert st.base_seq == st.seq and len(st.deltas) == 0
    assert st.effective_day == "20260608"
    assert {b["timestamp"][:10].replace("-", "") for b in st.payload["minute_bars"]} == {"20260608"}  # 旧日 bar 已丢
    kind, _ = engine.resume_since("02723.HK", 1)   # 旧 last_seq 落后于 base_seq
    assert kind == "snapshot"
```

- [ ] **Step 2: 跑确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_reconnect.py -q`
Expected: PASS (4 passed)

- [ ] **Step 3: 写 `backend-project/tests/test_integration_live.py`**

```python
import asyncio
import os

from market_state_engine.state.engine import MarketStateEngine, BaselineStore
from market_state_engine.adapters.xtquant_adapter import XtquantAdapter
from market_state_engine.bridge import ThreadAsyncBridge


def test_live_event_flows_to_broadcast_with_monotonic_seq(monkeypatch):
    # 限制每订阅回放事件数，避免无限回放；驱动真实 subscribe → daemon → bridge → apply → aqueue。
    # 关键：回放从最早日(20260601)开始，而默认 effective_day 是最新日(20260609)，会把早期 1m/tick 全部按日隔离丢弃。
    # 故把 effective_day 钉到 20260601，让早期 1m/tick 事件命中有效日，真正走通三类 delta（含 trade_tick）。
    monkeypatch.setenv("XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION", "8")
    monkeypatch.setenv("MARKET_EFFECTIVE_DAY", "20260601")

    async def main():
        store = BaselineStore().load()
        engine = MarketStateEngine(["02723.HK"], XtquantAdapter(names=store.names), store)
        engine.hydrate()
        assert engine.snapshots["02723.HK"].effective_day == "20260601"
        bridge = ThreadAsyncBridge(engine)
        bridge.bind(asyncio.get_running_loop())
        engine.start_live(bridge)
        collected = []
        try:
            while len(collected) < 20:                          # 收满 20 或超时即止（总量 ≤ 8×3 - 抑制）
                try:
                    delta = await asyncio.wait_for(bridge.aqueue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    break
                collected.append(delta)
        finally:
            engine.stop_live()
        assert collected, "应至少收到一个 live delta"
        # 单 symbol → seq 严格单调（apply 在 loop 单写者按序分配并 FIFO 入队）
        seqs = [d["seq"] for d in collected]
        assert seqs == sorted(seqs)
        # 时间戳本地化正确(秒级修复)后，effective_day=20260601 的 tick 不再被丢 → 至少一个 trade_tick delta
        assert any(d["payload"].get("delta_type") == "trade_tick" for d in collected), \
            "effective_day 正确时应有 trade_tick delta；若为 0 说明时间尺度/日隔离回归"
        # broker_queue delta 的 sourceDate 在 live 路径必须被填充（queue_ts 未丢；02723 队列日=20260603）
        bq = [d for d in collected if d["payload"].get("delta_type") == "broker_queue"]
        if bq:
            assert bq[0]["payload"]["broker_queue"]["sourceDate"] == "20260603"

    asyncio.run(main())
```

- [ ] **Step 4: 跑确认通过**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests/test_integration_live.py -q`
Expected: PASS (1 passed)

> 若超时偶发，提高 `wait_for` timeout 或确认 `XTMOCK_REPLAY_SPEED` 默认 1.0（事件间隔 ≤1s）。

- [ ] **Step 5: 跑整个后端测试套件**

Run: `XTMOCK_SILVER_ROOT=sample-data python -m pytest backend-project/tests -q`
Expected: PASS（test_models 3 + test_transforms 10 + test_adapter 4 + test_engine_contract 6 + test_bridge 2 + test_gateway 5 + test_reconnect 4 + test_integration_live 1 + test_smoke 1 + test_contracts 4 = 40 passed）

- [ ] **Step 6: 提交**

```bash
git add backend-project/tests/test_reconnect.py backend-project/tests/test_integration_live.py
git commit -m "test(backend): reconnect resume tri-state + seq-no-reset + live integration"
```

---

## Task 8：serve 入口、README、PR 说明（Communication 15 分）

**Files:**
- Modify: `Makefile`（新增 `serve-backend` target，可选）
- Modify: `backend-project/README.md`（追加「实现说明」）
- Create: `backend-project/SUBMISSION.md`（PR 描述草稿）

- [ ] **Step 1: 在 `Makefile` 末尾追加 serve-backend（设回放上限，避免无限重放刷屏）**

```makefile
serve-backend:
	PYTHONPATH=mock-xtquant/src:backend-project/src XTMOCK_SILVER_ROOT=sample-data \
		MARKET_SYMBOLS="$(SYMBOLS)" XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION=2000 \
		$(PYTHON) -m market_state_engine.app
```

- [ ] **Step 2: 在 `backend-project/README.md` 追加「## 实现说明」**（写明状态机设计、snapshot/delta 协议、effective-day 处理、broker queue 为何覆盖而非累加、测试覆盖的坑——README 的 Submit 清单逐条对应）。内容要点：

  - **状态机**：每 symbol 一个 `SymbolState`（payload/seq/base_seq/deltas 环形缓冲/seen_tick_ids/last_queue_ts/lock）。三态 freshness：水合 WARM → 首个 live 事件 LIVE。
  - **snapshot/delta 协议**：`terminal-message-v3` schema 1；`frame()` source=`candidate-backend`；per-symbol 单调 seq；snapshot `seq=max(1,seq)`；delta 三型。
  - **桥接**：SDK daemon 线程回调 → `call_soon_threadsafe` → loop 单写者 apply → asyncio.Queue → 并发广播。状态变更与网络扇出解耦。
  - **effective-day**：三处隔离（派生 max 日 / hydrate filter / live apply drop）；broker queue 落后日用 `historical+fallback` 标记而非丢弃。
  - **broker queue 覆盖而非累加**：每个 `hkbrokerqueueex` 事件整快照覆盖；档位 = SDK 派生 gear，永不重编号；档位量 = Σ 券商 cell。
  - **测试覆盖的坑**：见 §Task1-7 的对抗式断言。

- [ ] **Step 3: 创建 `backend-project/SUBMISSION.md`**（PR 草稿，含「已知限制与下一步」，对应评分「能说明已知限制和下一步:5」）。必含以下**诚实披露**（评审强调诚实加分、发明未验证行为会触发 ad-hoc-patch 红旗）：

  - **baseline 的 SDK 限制**：xtdata 无 `1d`（返回 `{}`），`get_instrument_detail` 返回 `{}`，故 daily baseline / 券商名 / 标的名由 `BaselineStore` 直读 `sample-data/*.csv`（与参考 `SampleDataStore` 同源、隔离在单一边界）。`fetch_daily_baseline` 保留「先试 SDK」路径以备未来 SILVER_FAMILIES 增加 `1d`。
  - **error 帧是无契约发明**：文档列了 `error` 但参考实现从不发、无字段规范；本实现用最小 `{code,message}`，坏输入不让 `handle_client` 崩溃。
  - **无限回放与 resume 退化**：未设回放上限时 SDK daemon 无限重放同 symbol 行；apply 用「重复 tick-id / 同 queue_ts / 同 bar 不发 delta」抑制 seq 膨胀；长时间离线客户端的 resume 会优雅退化为整 snapshot（512 深 ring 之外）。`serve-backend` 设 `XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION=2000`。
  - **不存在「live tick 到今天就清 fallback alert」机制**：因为 hydrate 从不注入历史 alert（`alerts=[]` + `filter_current_day`），「历史 alert 仅当 sourceDate==effectiveTradeDate 才入快照」是**空真**满足（emitted alert 的 tick 已过日 guard，sourceDate==effective_day）。不要新增注入历史 alert 的代码路径。
  - **effective_day 的数据形状耦合**：`_effective_day_from_rows` 取自 `fetch_minute_rows(count=420)` 的 tail-420 行的 max 日；参考实现 `SampleDataStore.effective_day` 扫的是该 symbol 全部 minute 行。样本每 symbol 每日 ~341 bar、tail-420 仍含最后一日(20260609)，故两者一致；但若某单日 bar 数 > 420 则 effective_day 可能偏差——已在此显式标注，必要时改为专门的全量 max-date 扫描。
  - **1m `time` 的 epoch 量级与 pandas 版本相关**：本 lab pandas 3.0(`datetime64[us]`) 下 `silver_store._timestamp_ms` 实际产出 epoch 秒(10 位)，pandas 2.2(`datetime64[ns]`) 下是毫秒(13 位)。`ms_to_hk_iso` 以 1e12 边界按量级兼容两者，故对 pandas 版本无关；不依赖在 `requirements.txt` 钉死 pandas。
  - **下一步**：每客户端独立 bounded 队列做背压、midnight roll 自动切日、periodic heartbeat keepalive。

- [ ] **Step 4: 全量回归 + 提交**

Run: `XTMOCK_SILVER_ROOT=sample-data RESEARCH_DATA_ROOT=research-data python -m pytest -q`（全仓库套件，确认未破坏 research-api/strategy 测试）
Expected: PASS（后端 41 + 其余既有测试）

```bash
git add Makefile backend-project/README.md backend-project/SUBMISSION.md
git commit -m "docs(backend): README impl notes + SUBMISSION PR draft + serve-backend target"
```

---

## 已知限制 / 评分映射（自查）

| 评分项 | 分 | 计划落点 |
|---|---|---|
| 数据跑通核心功能完整 | 10 | Task2-6 全链路；test_integration_live 端到端 |
| broker queue 档位语义正确 | 10 | transforms.broker_queue_from_rows 逐字复制 + flatten 保 gear；test_transforms / test_engine_contract |
| effective day / alerts 不串日 | 10 | engine 三处隔离；test_engine_contract 镜像断言；test_reconnect day-switch |
| WS snapshot/delta/reconnect 正确 | 10 | gateway + resume_since 三态；test_gateway / test_reconnect |
| 组件/模块边界清晰 | 8 | 8 模块单一职责；xtquant 仅 adapter、业务仅 engine、协议仅 gateway |
| 状态管理可解释 | 7 | SymbolState + 单写者 + seq/base_seq/ring 文档化 |
| 测试覆盖关键坑 | 7 | 41 个对抗式断言覆盖每个 red flag |
| 错误处理和空状态合理 | 3 | error 帧、flatten 防御、empty_snapshot、慢客户端并发广播 |
| 状态机设计简洁 | 8 | apply 单函数三分支；transforms 纯函数 |
| payload contract 稳定 | 8 | 与参考逐字节同形；source=candidate-backend |
| freshness/source evidence | 4 | freshness.runtime_state/effective_day/source_dates + broker_queue.sourceDate/historical/fallback |
| PR 描述/tradeoff/已知限制 | 15 | SUBMISSION.md + README 实现说明 |

**Red flags 规避**：① 队列整覆盖（apply hkbrokerqueueex 分支 `=` 覆盖）；② 不重编号（flatten 保 SDK gear，test 断言 [1,3,11]）；③ 不混旧日大额（apply 日 guard + alert sourceDate==effective_day）；④ 自动刷新（WS delta 推送，非手动）；⑤ 有测试说明（SUBMISSION + 41 测试）。

---

## Self-Review（写完计划后的回查）

- **Spec coverage**：评分表 12 项 + 5 red flags + README Submit 5 问 + test_contracts 4 断言 + test_smoke 2 断言 —— 均有对应 Task。✓
- **两轮对抗验证的 blocker/major 已内建修复**：
  - 架构评审（Workflow #1）：queue_ts 显式 field_list（Task2/§0.1）；1m bar_ts 本地化（Task1-2）；hydrate 末尾复位 WARM + mock_rows（Task3）；无限回放 no-op 抑制（Task3 apply）；onboard executor 卸载 + 先 snapshot 后订阅（Task5）；并发广播（Task5）；sink try/except + loop guard（Task4）；seq 不回退（Task3/Task7 断言）；flatten 防御（Task1）；移除「清 fallback alert」伪机制 + error 帧诚实披露（Task8）。✓
  - 计划经验性验证（Workflow #2，4 审查 agent 实跑真实数据收敛）：**根因 blocker——SDK 1m `time` 在本 lab(pandas 3.0)是 epoch 秒非毫秒**，`ms_to_hk_iso` 误 `/1000` 会落到 1970、effective_day 退化 19700121、打挂 3 个测试。已改为 1e12 边界按量级兼容（Task1 `ms_to_hk_iso` + `iso_from_any` 防御分支），并加 10 位秒单测、强化集成测试断言 ≥1 trade_tick（Task1/Task7）。✓ 一个过度断言（"tail-420 无 20260608 bar，需加大 count"）经实测驳回（tail(420) 含 79 条 20260608），故 `count=420` 不改。✓
- **类型/签名一致性**：`SymbolState`(models) 字段被 engine/bridge/transforms 一致引用；`frame()` 单一定义；`broker_queue_from_rows`/`flatten_broker_levels`/`apply` 跨 Task 命名一致。✓
- **No placeholders**：每个代码步给完整代码、每个命令给期望输出。✓
- **DRY/YAGNI**：转换逐字复用参考；未引入 Redis/Kafka/真 xtquant。✓

---

## Execution Handoff

计划已存至 `docs/plans/2026-06-17-backend-market-state-engine-fullscore.md`。两种执行方式：

1. **Subagent-Driven（推荐）** —— 每个 Task 派新 subagent，Task 间两阶段评审、快速迭代（`superpowers:subagent-driven-development`）。
2. **Inline Execution** —— 本会话内按 Task 批量执行 + checkpoint（`superpowers:executing-plans`）。

按全局 CLAUDE.md：每完成一个 Task/里程碑，向本文件追加进度更新。

---

## 进度记录

- **2026-06-17 计划制定完成（subagent/workflow 驱动）**：
  - Workflow #1（理解+设计，7 agents / 44 万 token）：4 路并行深挖 SDK 数据路径/WS 契约/参考实现映射/测试与真实数据，逐字段核实回调形状、parquet 列名、混源日；1 架构师 + 2 对抗评审产出含 10 项 blocker/major 修复的架构。
  - 据此撰写本计划（8 模块 + 10 测试文件，全部含可直接落地的完整代码）。
  - Workflow #2（计划对抗验证，5 agents / 42 万 token）：4 审查 agent **实跑真实数据**（py_compile + 真实 `get_market_data_ex`/`subscribe_quote`）+ 1 裁决。捕获我与 Workflow #1 都搞错的根因 blocker（1m `time` 是 epoch 秒非毫秒），并驳回 1 个过度断言。
  - 全部 must-fix（`ms_to_hk_iso`/`iso_from_any` 按量级兼容）+ 高价值 nice-to-have（10 位秒单测、集成测试断言 ≥1 trade_tick、SUBMISSION 补两条已知限制）已内建。裁决判定：应用 must-fix 后 **40 个测试全通过、100/100 高置信**。
  - 状态：**计划就绪（仅产出文档，未动 `backend-project/src`）**，等待执行决策。
