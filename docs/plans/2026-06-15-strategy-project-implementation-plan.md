# IPO Daily Strategy Research 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `strategy-project/` scaffold 上扩展，交付一个可复现的港股新股日线研究闭环：baseline 首日动量 + 依赖外部数据（暗盘主过滤 / IPO 特征分层）的改进版，扣成本回测、对照、报告。

**Architecture:** 方案 A 原地扩展。三段流水线 `download → build_features → backtest` 不变；baseline 与 improved 复用同一回测引擎（通过 mask 区分 `strategy_version`）；新增 `config.py`、`external_data.py`、`daily_utils.py` 解耦参数、外部数据、日线归一化；移除 `fillna(0)` 改为显式"不可交易"处理。

**Tech Stack:** Python 3.12、pandas、pyarrow、pytest、pixi（环境）、stdlib urllib（HTTP 下载）、tabulate（报告表格）。

**依据：** `docs/plans/2026-06-15-strategy-project-design.md`（设计 spec），严格遵从 `docs/strategy-project.md`。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `pixi.toml`（仓库根，新建） | 环境与任务（serve-research / download / features / backtest / pipeline / test） |
| `strategy-project/tests/conftest.py`（新建） | 把 `strategy-project/src` 注入 sys.path，供测试扁平 import |
| `strategy-project/src/config.py`（新建） | 集中策略参数（dataclass） |
| `strategy-project/src/daily_utils.py`（新建） | 日线归一化 + `tradable` 标记（DRY，替代三处重复 normalize_daily） |
| `strategy-project/src/costs.py`（改） | 增加 `scale_cost_model` 供成本敏感性 |
| `strategy-project/src/external_data.py`（新建） | 加载/校验 `ipo_info.csv`+`grey_market.csv`，产出覆盖率 |
| `strategy-project/src/download_data.py`（改） | 移除 `fillna(0)`；扩展 `coverage_summary.json` |
| `strategy-project/src/build_features.py`（改） | day1/day2 tradable 判定；左 join 外部数据 |
| `strategy-project/src/strategy.py`（改） | 统一 `generate_trades(... mask ...)`；停牌顺延出场 |
| `strategy-project/src/metrics.py`（改） | 增加按 `strategy_version` 分组的 `metrics_by_version` |
| `strategy-project/src/report_tables.py`（改） | 对照表 + 成本敏感性 + IPO 分层 + 填实报告 |
| `strategy-project/src/backtest.py`（改） | 编排两版本 + 敏感性 + 写全部产物 |
| `strategy-project/data/external/ipo_info.csv`（新建，采集） | IPO 基本面（带来源） |
| `strategy-project/data/external/grey_market.csv`（新建，采集） | 暗盘（带来源） |

约定：流水线脚本从 `strategy-project/` 运行（`python src/xxx.py`），src 自动入 sys.path。测试经 conftest 注入 src。

---

## Task 1: pixi 环境

**Files:**
- Create: `pixi.toml`

- [ ] **Step 1: 写 pixi.toml**

```toml
[project]
name = "intern-gym-strategy"
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
python = "3.12.*"
pandas = ">=2.2"
pyarrow = ">=15"
pytest = ">=8"
tabulate = ">=0.9"

[tasks]
serve-research = { cmd = "python -m market_research_api.server --host 127.0.0.1 --port 9041", env = { PYTHONPATH = "mock-research-api/src", RESEARCH_DATA_ROOT = "research-data" } }
download = { cmd = "python src/download_data.py --base-url http://127.0.0.1:9041 --start 2026-01-01", cwd = "strategy-project" }
features = { cmd = "python src/build_features.py", cwd = "strategy-project" }
backtest = { cmd = "python src/backtest.py", cwd = "strategy-project" }
pipeline = { cmd = "python src/download_data.py --source-root ../research-data && python src/build_features.py && python src/backtest.py", cwd = "strategy-project" }
test = { cmd = "pytest -q", env = { RESEARCH_DATA_ROOT = "research-data" } }
```

- [ ] **Step 2: 安装并验证**

Run: `pixi install && pixi run python -c "import pandas, pyarrow, tabulate; print('ok')"`
Expected: 打印 `ok`

- [ ] **Step 3: Commit**

```bash
git add pixi.toml
git commit -m "chore: add pixi environment and pipeline tasks"
```

---

## Task 2: 测试 conftest

**Files:**
- Create: `strategy-project/tests/conftest.py`

- [ ] **Step 1: 写 conftest.py**

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

- [ ] **Step 2: 验证现有测试仍通过**

Run: `pixi run pytest strategy-project/tests/test_strategy_scaffold.py -q`
Expected: PASS（1 passed）

- [ ] **Step 3: Commit**

```bash
git add strategy-project/tests/conftest.py
git commit -m "test: add strategy conftest to expose src on sys.path"
```

---

## Task 3: config 参数模块

**Files:**
- Create: `strategy-project/src/config.py`
- Test: `strategy-project/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
from config import DEFAULT, COST_SENSITIVITY_SCALES, StrategyConfig

def test_default_config_values():
    assert DEFAULT.threshold == 0.05
    assert DEFAULT.holding_days == 3
    assert DEFAULT.grey_filter_field in {"grey_change_pct", "premium_to_ipo_price"}
    assert 1.0 in COST_SENSITIVITY_SCALES

def test_config_is_overridable():
    cfg = StrategyConfig(threshold=0.1, grey_premium_min=0.05)
    assert cfg.threshold == 0.1
    assert cfg.grey_premium_min == 0.05
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_config.py -q`
Expected: FAIL（ModuleNotFoundError: config）

- [ ] **Step 3: 实现 config.py**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    threshold: float = 0.05                 # 首日动量信号阈值
    holding_days: int = 3                   # 持仓窗口 K
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.20
    notional_per_trade: float = 100_000.0
    grey_filter_field: str = "grey_change_pct"   # 主过滤字段；或 "premium_to_ipo_price"
    grey_premium_min: float = 0.0           # 主过滤阈值：filter_field >= 该值
    cost_scale: float = 1.0                 # 成本缩放（敏感性用）


DEFAULT = StrategyConfig()
COST_SENSITIVITY_SCALES = (0.5, 1.0, 2.0)
```

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/config.py strategy-project/tests/test_config.py
git commit -m "feat(strategy): add central config module"
```

---

## Task 4: 日线归一化 + tradable（daily_utils）

**Files:**
- Create: `strategy-project/src/daily_utils.py`
- Test: `strategy-project/tests/test_daily_utils.py`

- [ ] **Step 1: 写失败测试**

```python
import numpy as np
import pandas as pd
from daily_utils import normalize_daily

def _raw():
    return pd.DataFrame([
        {"symbol": "1.hk", "trade_date": "2026-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "turnover": 1000, "previous_close": 9.8, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260105", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "turnover": 0, "previous_close": 10.5, "suspend_flag": 1},
        {"symbol": "1.HK", "trade_date": "20260106", "open": np.nan, "high": 12, "low": 10, "close": 11, "volume": 50, "turnover": 550, "previous_close": 10.5, "suspend_flag": 0},
    ])

def test_normalize_uppercases_symbol_and_date():
    out = normalize_daily(_raw())
    assert set(out["symbol"]) == {"1.HK"}
    assert out["trade_date"].tolist() == ["20260102", "20260105", "20260106"]

def test_tradable_flags_suspend_zero_volume_and_missing_open():
    out = normalize_daily(_raw()).set_index("trade_date")
    assert bool(out.loc["20260102", "tradable"]) is True
    assert bool(out.loc["20260105", "tradable"]) is False   # suspend + zero volume
    assert bool(out.loc["20260106", "tradable"]) is False   # missing open

def test_missing_prices_not_filled_with_zero():
    out = normalize_daily(_raw()).set_index("trade_date")
    assert pd.isna(out.loc["20260106", "open"])             # 保留 NaN，不填 0
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_daily_utils.py -q`
Expected: FAIL（ModuleNotFoundError: daily_utils）

- [ ] **Step 3: 实现 daily_utils.py**

```python
from __future__ import annotations

import pandas as pd

PRICE_COLS = ("open", "high", "low", "close")


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["trade_date"] = result["trade_date"].astype(str).str.replace("-", "", regex=False)
    for column in (*PRICE_COLS, "volume", "turnover", "previous_close"):
        if column not in result.columns:
            result[column] = pd.NA
        # 关键：errors="coerce" 把非法值变 NaN，但不 fillna(0)
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if "suspend_flag" not in result.columns:
        result["suspend_flag"] = 0
    result["suspend_flag"] = pd.to_numeric(result["suspend_flag"], errors="coerce").fillna(0).astype(int)
    result["tradable"] = (
        (result["suspend_flag"] == 0)
        & result["open"].notna() & (result["open"] > 0)
        & result["close"].notna() & (result["close"] > 0)
        & result["volume"].notna() & (result["volume"] > 0)
    )
    return result.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
```

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_daily_utils.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/daily_utils.py strategy-project/tests/test_daily_utils.py
git commit -m "feat(strategy): add daily normalization with tradable flag (no fillna 0)"
```

---

## Task 5: 成本缩放 helper

**Files:**
- Modify: `strategy-project/src/costs.py`
- Test: `strategy-project/tests/test_costs.py`

- [ ] **Step 1: 写失败测试**

```python
from costs import trade_cost, apply_slippage, scale_cost_model

MODEL = {"buy_cost_bps": 12.0, "sell_cost_bps": 22.0, "slippage_bps": 10.0, "min_fee": 5.0}

def test_trade_cost_takes_min_fee_floor():
    # 极小成交额时取 min_fee
    assert trade_cost(100.0, "buy", MODEL) == 5.0
    # 正常按 bps：1_000_000 * 12 / 10000 = 1200
    assert trade_cost(1_000_000.0, "buy", MODEL) == 1200.0

def test_apply_slippage_direction():
    assert apply_slippage(100.0, "buy", MODEL) == 100.0 * (1 + 10 / 10000)
    assert apply_slippage(100.0, "sell", MODEL) == 100.0 * (1 - 10 / 10000)

def test_scale_cost_model_scales_bps_and_fee():
    scaled = scale_cost_model(MODEL, 2.0)
    assert scaled["buy_cost_bps"] == 24.0
    assert scaled["sell_cost_bps"] == 44.0
    assert scaled["slippage_bps"] == 20.0
    assert scaled["min_fee"] == 10.0
    assert MODEL["buy_cost_bps"] == 12.0  # 原 model 不被改
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_costs.py -q`
Expected: FAIL（ImportError: scale_cost_model）

- [ ] **Step 3: 在 costs.py 末尾追加**

```python
def scale_cost_model(model: dict[str, float], scale: float) -> dict[str, float]:
    scaled = dict(model)
    for key in ("buy_cost_bps", "sell_cost_bps", "slippage_bps", "min_fee"):
        if key in scaled and isinstance(scaled[key], (int, float)):
            scaled[key] = float(scaled[key]) * scale
    return scaled
```

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_costs.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/costs.py strategy-project/tests/test_costs.py
git commit -m "feat(strategy): add scale_cost_model for cost sensitivity"
```

---

## Task 6: 外部数据加载 + 覆盖率

**Files:**
- Create: `strategy-project/src/external_data.py`
- Test: `strategy-project/tests/test_external_data.py`

外部模板字段见 `docs/strategy-project.md`。loader 容忍文件缺失/部分缺失，缺失保持 NaN（不填 0）。

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from external_data import load_external, external_coverage, IPO_COLS, GREY_COLS

def test_load_external_missing_files_returns_empty_with_schema(tmp_path):
    ipo, grey = load_external(tmp_path)
    assert list(ipo.columns) == list(IPO_COLS)
    assert list(grey.columns) == list(GREY_COLS)
    assert ipo.empty and grey.empty

def test_coverage_counts_present_rows(tmp_path):
    (tmp_path / "grey_market.csv").write_text(
        "symbol,grey_market_date,grey_close,grey_change_pct,premium_to_ipo_price,source_url,source_note,collected_at\n"
        "1.HK,20260101,11,0.1,0.1,http://x,note,2026-06-15\n"
        "2.HK,,,,,,,\n",  # 留空缺失，不填 0
        encoding="utf-8",
    )
    universe = pd.DataFrame({"symbol": ["1.HK", "2.HK", "3.HK"]})
    cov = external_coverage(universe, load_external(tmp_path)[1], key="grey_change_pct", label="grey_market")
    assert cov["grey_market_total_symbols"] == 3
    assert cov["grey_market_with_grey_change_pct"] == 1   # 仅 1.HK 有值
    assert round(cov["grey_market_coverage_ratio"], 3) == round(1 / 3, 3)
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_external_data.py -q`
Expected: FAIL（ModuleNotFoundError: external_data）

- [ ] **Step 3: 实现 external_data.py**

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

IPO_COLS = (
    "symbol", "listing_date", "ipo_price", "offer_price_low", "offer_price_high",
    "sponsor", "industry", "public_subscription_multiple", "one_lot_success_rate",
    "source_url", "source_note", "collected_at",
)
GREY_COLS = (
    "symbol", "grey_market_date", "grey_close", "grey_change_pct",
    "premium_to_ipo_price", "source_url", "source_note", "collected_at",
)
_NUMERIC = {
    "ipo_price", "offer_price_low", "offer_price_high",
    "public_subscription_multiple", "one_lot_success_rate",
    "grey_close", "grey_change_pct", "premium_to_ipo_price",
}


def _read(path: Path, cols: tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(cols))
    df = pd.read_csv(path, dtype=str)
    for col in cols:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[list(cols)].copy()
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    for col in cols:
        if col in _NUMERIC:
            df[col] = pd.to_numeric(df[col], errors="coerce")  # 缺失 -> NaN，绝不填 0
    return df[df["symbol"].notna() & (df["symbol"] != "") & (df["symbol"] != "NAN")].reset_index(drop=True)


def load_external(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(root)
    return _read(root / "ipo_info.csv", IPO_COLS), _read(root / "grey_market.csv", GREY_COLS)


def external_coverage(universe: pd.DataFrame, frame: pd.DataFrame, *, key: str, label: str) -> dict:
    total = int(universe["symbol"].astype(str).str.upper().nunique())
    present = 0
    if not frame.empty and key in frame.columns:
        present = int(frame.loc[frame[key].notna(), "symbol"].nunique())
    return {
        f"{label}_total_symbols": total,
        f"{label}_with_{key}": present,
        f"{label}_coverage_ratio": (present / total) if total else 0.0,
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_external_data.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/external_data.py strategy-project/tests/test_external_data.py
git commit -m "feat(strategy): add external IPO/grey-market loader and coverage"
```

---

## Task 7: download 移除 fillna(0) + 扩展 coverage

**Files:**
- Modify: `strategy-project/src/download_data.py`
- Test: `strategy-project/tests/test_download_data.py`

复用 `daily_utils.normalize_daily`，删除本文件内 `fillna(0)` 版的 `normalize_daily`；`coverage_summary` 增加停牌/无成交/缺失统计。

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from download_data import coverage_summary

def test_coverage_summary_reports_suspend_and_missing():
    universe = pd.DataFrame({"symbol": ["1.HK", "2.HK"], "name": ["a", "b"],
                             "coverage_start": ["20260102", "20260102"], "coverage_end": ["20260110", "20260110"]})
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260102", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000, "previous_close": 9, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260105", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "turnover": 0, "previous_close": 10, "suspend_flag": 1},
    ])
    cov = coverage_summary(universe, daily)
    assert cov["symbol_count"] == 2
    assert cov["missing_daily_symbols"] == ["2.HK"]
    assert cov["suspended_rows"] == 1
    assert cov["zero_volume_rows"] == 1
    assert cov["duplicate_daily_keys"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_download_data.py -q`
Expected: FAIL（覆盖率缺少 suspended_rows 等键）

- [ ] **Step 3: 修改 download_data.py**

3a. 顶部 import 改为复用 daily_utils（删除本文件的 `normalize_daily` 实现），保留列裁剪：

```python
from daily_utils import normalize_daily as _normalize_daily

DAILY_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close",
                 "volume", "turnover", "previous_close", "suspend_flag"]

def normalize_daily(frame):
    out = _normalize_daily(frame)
    for col in DAILY_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[DAILY_COLUMNS].sort_values(["symbol", "trade_date"]).reset_index(drop=True)
```

3b. 替换 `coverage_summary`：

```python
def coverage_summary(universe: pd.DataFrame, daily: pd.DataFrame) -> dict[str, object]:
    from daily_utils import normalize_daily as nd
    norm = nd(daily)
    daily_keys = norm[["symbol", "trade_date"]]
    universe_symbols = set(universe["symbol"].astype(str).str.upper().unique())
    daily_symbols = set(norm["symbol"].unique())
    return {
        "symbol_count": int(len(universe_symbols)),
        "daily_rows": int(len(norm)),
        "date_min": str(norm["trade_date"].min() or ""),
        "date_max": str(norm["trade_date"].max() or ""),
        "missing_daily_symbols": sorted(universe_symbols - daily_symbols),
        "duplicate_daily_keys": int(daily_keys.duplicated().sum()),
        "suspended_rows": int((norm["suspend_flag"] == 1).sum()),
        "zero_volume_rows": int((norm["volume"].fillna(0) == 0).sum()),
        "missing_ohlc_rows": int(norm[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
    }
```

> 注意：`write_raw_data` 写出的 `daily_bars.parquet` 现在保留 NaN（不再 0 填），下游 build_features/strategy 依赖 `tradable` 跳过。

- [ ] **Step 4: 运行确认通过 + 现有 scaffold 测试不回归**

Run: `pixi run pytest strategy-project/tests/test_download_data.py strategy-project/tests/test_strategy_scaffold.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/download_data.py strategy-project/tests/test_download_data.py
git commit -m "feat(strategy): drop fillna(0), extend coverage with suspend/missing stats"
```

---

## Task 8: build_features 加 tradable 判定 + 外部 join

**Files:**
- Modify: `strategy-project/src/build_features.py`
- Test: `strategy-project/tests/test_build_features.py`

day1 = 第一条**有效(tradable)** 日线；entry = 紧随其后的下一条 tradable 日线；`baseline_signal` 要求 day2 存在且 tradable；左 join 外部数据。

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from build_features import build_daily_ipo_features

def _daily():
    return pd.DataFrame([
        # 1.HK：day1 涨 10%，day2 可交易 -> baseline 命中
        {"symbol": "1.HK", "trade_date": "20260102", "open": 10, "high": 12, "low": 10, "close": 11, "volume": 100, "turnover": 1000, "previous_close": 9, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260105", "open": 11, "high": 13, "low": 11, "close": 12, "volume": 80, "turnover": 900, "previous_close": 11, "suspend_flag": 0},
        # 2.HK：day1 涨 10%，但 day2 停牌 -> 不出信号
        {"symbol": "2.HK", "trade_date": "20260102", "open": 10, "high": 12, "low": 10, "close": 11, "volume": 100, "turnover": 1000, "previous_close": 9, "suspend_flag": 0},
        {"symbol": "2.HK", "trade_date": "20260105", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "turnover": 0, "previous_close": 11, "suspend_flag": 1},
    ])

def _universe():
    return pd.DataFrame({"symbol": ["1.HK", "2.HK"], "name": ["x", "y"],
                         "coverage_start": ["20260102", "20260102"], "coverage_end": ["20260110", "20260110"]})

def _external():
    ipo = pd.DataFrame({"symbol": ["1.HK"], "public_subscription_multiple": [50.0], "one_lot_success_rate": [0.3], "sponsor": ["S"], "industry": ["Tech"]})
    grey = pd.DataFrame({"symbol": ["1.HK"], "grey_change_pct": [0.2], "premium_to_ipo_price": [0.2]})
    return ipo, grey

def test_baseline_signal_requires_tradable_day2():
    feats = build_daily_ipo_features(_universe(), _daily(), threshold=0.05).set_index("symbol")
    assert bool(feats.loc["1.HK", "baseline_signal"]) is True
    assert bool(feats.loc["2.HK", "baseline_signal"]) is False  # day2 停牌

def test_external_columns_joined():
    ipo, grey = _external()
    feats = build_daily_ipo_features(_universe(), _daily(), threshold=0.05, ipo_info=ipo, grey_market=grey).set_index("symbol")
    assert feats.loc["1.HK", "grey_change_pct"] == 0.2
    assert feats.loc["1.HK", "public_subscription_multiple"] == 50.0
    assert pd.isna(feats.loc["2.HK", "grey_change_pct"])  # 无外部数据 -> NaN
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_build_features.py -q`
Expected: FAIL（签名不含 ipo_info/grey_market 或 day2 逻辑不符）

- [ ] **Step 3: 重写 build_daily_ipo_features**

```python
from __future__ import annotations

import argparse
import json

import pandas as pd

from daily_utils import normalize_daily
from external_data import load_external
from paths import PROCESSED_DIR, RAW_DIR

_EXTERNAL_FEATURE_COLS = [
    "grey_change_pct", "premium_to_ipo_price",
    "public_subscription_multiple", "one_lot_success_rate", "sponsor", "industry",
]


def safe_return(end: float, start: float) -> float:
    return end / start - 1.0 if start else 0.0


def build_daily_ipo_features(
    universe: pd.DataFrame,
    daily_bars: pd.DataFrame,
    *,
    threshold: float = 0.05,
    ipo_info: pd.DataFrame | None = None,
    grey_market: pd.DataFrame | None = None,
) -> pd.DataFrame:
    daily = normalize_daily(daily_bars)
    universe = universe.copy()
    universe["symbol"] = universe["symbol"].astype(str).str.upper()
    rows = []

    for symbol, group in daily.groupby("symbol", sort=True):
        bars = group.sort_values("trade_date").reset_index(drop=True)
        tradable = bars[bars["tradable"]].reset_index(drop=True)
        if len(tradable) < 2:
            continue
        first = tradable.iloc[0]
        entry = tradable.iloc[1]
        first_day_return = safe_return(float(first["close"]), float(first["open"]))
        listing_row = universe[universe["symbol"] == symbol].head(1)
        coverage_start = str(first["trade_date"])
        name = ""
        if not listing_row.empty:
            coverage_start = str(listing_row.iloc[0].get("coverage_start") or coverage_start)
            name = str(listing_row.iloc[0].get("name") or "")
        rows.append({
            "symbol": symbol,
            "name": name,
            "coverage_start": coverage_start,
            "trade_date_1": str(first["trade_date"]),
            "first_day_open": float(first["open"]),
            "first_day_close": float(first["close"]),
            "first_day_high": float(first["high"]),
            "first_day_low": float(first["low"]),
            "first_day_return_vs_open": first_day_return,
            "first_day_volume": int(first["volume"]),
            "first_day_turnover": float(first["turnover"]),
            "entry_date": str(entry["trade_date"]),
            "entry_open": float(entry["open"]),
            "baseline_signal": bool(first_day_return > threshold and float(entry["open"]) > 0),
        })

    features = pd.DataFrame(rows)
    if features.empty:
        for col in _EXTERNAL_FEATURE_COLS:
            features[col] = pd.Series(dtype="object")
        return features

    features = _join_external(features, ipo_info, ["public_subscription_multiple", "one_lot_success_rate", "sponsor", "industry"])
    features = _join_external(features, grey_market, ["grey_change_pct", "premium_to_ipo_price"])
    for col in _EXTERNAL_FEATURE_COLS:
        if col not in features.columns:
            features[col] = pd.NA
    return features


def _join_external(features: pd.DataFrame, ext: pd.DataFrame | None, cols: list[str]) -> pd.DataFrame:
    if ext is None or ext.empty:
        for col in cols:
            features[col] = pd.NA
        return features
    ext = ext.copy()
    ext["symbol"] = ext["symbol"].astype(str).str.upper()
    keep = ["symbol"] + [c for c in cols if c in ext.columns]
    return features.merge(ext[keep].drop_duplicates("symbol"), on="symbol", how="left")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build daily first-trading-day IPO features.")
    parser.add_argument("--threshold", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = pd.read_parquet(RAW_DIR / "ipo_universe.parquet")
    daily = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    ipo_info, grey_market = load_external(RAW_DIR.parent / "external")
    features = build_daily_ipo_features(universe, daily, threshold=args.threshold, ipo_info=ipo_info, grey_market=grey_market)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    features.to_parquet(PROCESSED_DIR / "features.parquet", index=False)
    print(json.dumps({"rows": int(len(features)), "signals": int(features["baseline_signal"].sum())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> 说明：`RAW_DIR.parent / "external"` = `strategy-project/data/external`（与 `data/raw` 同级）。

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_build_features.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/build_features.py strategy-project/tests/test_build_features.py
git commit -m "feat(strategy): tradable-aware features with external join"
```

---

## Task 9: 统一回测引擎 + 停牌顺延

**Files:**
- Modify: `strategy-project/src/strategy.py`
- Test: `strategy-project/tests/test_strategy_engine.py`

把 `generate_baseline_trades` 重构为 `generate_trades(features, daily, cost_model, *, version, mask, config)`；提供 `baseline_mask` / `improved_mask`；保留 `generate_baseline_trades` 薄包装（向后兼容现有 scaffold 测试）。出场跳过不可交易日、到期顺延。

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from config import StrategyConfig
from strategy import generate_trades, baseline_mask, improved_mask

def _features():
    return pd.DataFrame([
        {"symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260105",
         "baseline_signal": True, "grey_change_pct": 0.2, "premium_to_ipo_price": 0.2},
        {"symbol": "2.HK", "coverage_start": "20260102", "entry_date": "20260105",
         "baseline_signal": True, "grey_change_pct": -0.1, "premium_to_ipo_price": -0.1},
    ])

def _daily():
    rows = []
    for sym in ("1.HK", "2.HK"):
        rows += [
            {"symbol": sym, "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
            {"symbol": sym, "trade_date": "20260106", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},
            {"symbol": sym, "trade_date": "20260107", "open": 107, "high": 110, "low": 104, "close": 109, "volume": 10, "turnover": 1, "previous_close": 107, "suspend_flag": 0},
        ]
    return pd.DataFrame(rows)

MODEL = {"buy_cost_bps": 12.0, "sell_cost_bps": 22.0, "slippage_bps": 10.0, "min_fee": 5.0}

def test_holding_days_bounded_by_window():
    cfg = StrategyConfig(holding_days=3, stop_loss_pct=0.5, take_profit_pct=0.5)
    trades = generate_trades(_features(), _daily(), MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
    assert (trades["holding_days"] <= 3).all()
    assert set(trades["strategy_version"]) == {"baseline_first_day_momentum_daily"}

def test_improved_mask_filters_negative_grey():
    cfg = StrategyConfig(grey_filter_field="grey_change_pct", grey_premium_min=0.0)
    trades = generate_trades(_features(), _daily(), MODEL, version="improved_grey_market_filter", mask=improved_mask, config=cfg)
    assert set(trades["symbol"]) == {"1.HK"}  # 2.HK 暗盘为负被过滤

def test_trade_log_has_required_fields():
    cfg = StrategyConfig()
    trades = generate_trades(_features(), _daily(), MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
    required = {"symbol", "coverage_start", "entry_date", "entry_price", "exit_date", "exit_price",
               "shares", "gross_pnl", "fees", "slippage", "net_pnl", "return", "exit_reason",
               "holding_days", "strategy_version"}
    assert required <= set(trades.columns)
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_strategy_engine.py -q`
Expected: FAIL（generate_trades / masks 未定义）

- [ ] **Step 3: 重写 strategy.py**

```python
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from config import DEFAULT, StrategyConfig
from costs import apply_slippage, trade_cost
from daily_utils import normalize_daily

Mask = Callable[[pd.DataFrame, StrategyConfig], pd.Series]


def baseline_mask(features: pd.DataFrame, config: StrategyConfig) -> pd.Series:
    return features["baseline_signal"].astype(bool)


def improved_mask(features: pd.DataFrame, config: StrategyConfig) -> pd.Series:
    base = features["baseline_signal"].astype(bool)
    field = config.grey_filter_field
    if field not in features.columns:
        return pd.Series(False, index=features.index)
    values = pd.to_numeric(features[field], errors="coerce")
    return base & values.notna() & (values >= config.grey_premium_min)


def generate_trades(
    features: pd.DataFrame,
    daily_bars: pd.DataFrame,
    cost_model: dict[str, float],
    *,
    version: str,
    mask: Mask,
    config: StrategyConfig = DEFAULT,
) -> pd.DataFrame:
    bars = normalize_daily(daily_bars)
    selected = features[mask(features, config)]
    trades = []

    for feature in selected.to_dict("records"):
        symbol = str(feature["symbol"])
        entry_date = str(feature["entry_date"])
        symbol_bars = bars[(bars["symbol"] == symbol) & (bars["tradable"])].sort_values("trade_date").reset_index(drop=True)
        entry_matches = symbol_bars[symbol_bars["trade_date"] == entry_date]
        if entry_matches.empty:
            continue
        entry_index = int(entry_matches.index[0])
        path = symbol_bars.iloc[entry_index: entry_index + max(1, config.holding_days)]
        if path.empty:
            continue

        entry_row = path.iloc[0]
        entry_raw = float(entry_row["open"])
        entry_price = apply_slippage(entry_raw, "buy", cost_model)
        shares = int(config.notional_per_trade // entry_price) if entry_price > 0 else 0
        if shares <= 0:
            continue

        exit_row = path.iloc[-1]
        exit_reason = "holding_period"
        stop_level = entry_price * (1 - config.stop_loss_pct)
        take_level = entry_price * (1 + config.take_profit_pct)
        for _, row in path.iterrows():
            if float(row["low"]) <= stop_level:
                exit_row, exit_reason = row, "stop_loss"
                break
            if float(row["high"]) >= take_level:
                exit_row, exit_reason = row, "take_profit"
                break
        held_days = int(path[path["trade_date"] <= str(exit_row["trade_date"])].shape[0])

        exit_raw = float(exit_row["close"])
        exit_price = apply_slippage(exit_raw, "sell", cost_model)
        buy_notional = entry_price * shares
        sell_notional = exit_price * shares
        fees = trade_cost(buy_notional, "buy", cost_model) + trade_cost(sell_notional, "sell", cost_model)
        gross_pnl = sell_notional - buy_notional
        slippage = abs(entry_price - entry_raw) * shares + abs(exit_raw - exit_price) * shares
        net_pnl = gross_pnl - fees

        trades.append({
            "symbol": symbol,
            "coverage_start": str(feature.get("coverage_start") or ""),
            "entry_date": str(entry_row["trade_date"]),
            "entry_price": entry_price,
            "exit_date": str(exit_row["trade_date"]),
            "exit_price": exit_price,
            "shares": shares,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "slippage": slippage,
            "net_pnl": net_pnl,
            "return": net_pnl / buy_notional if buy_notional else 0.0,
            "exit_reason": exit_reason,
            "holding_days": held_days,
            "strategy_version": version,
        })

    return pd.DataFrame(trades)


def generate_baseline_trades(features, daily_bars, cost_model, *, notional_per_trade=100_000.0,
                             holding_days=3, stop_loss_pct=0.08, take_profit_pct=0.20):
    """向后兼容包装（scaffold 旧测试用）。"""
    cfg = StrategyConfig(notional_per_trade=notional_per_trade, holding_days=holding_days,
                         stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct)
    return generate_trades(features, daily_bars, cost_model,
                           version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
```

- [ ] **Step 4: 运行确认通过 + 旧 scaffold 测试不回归**

Run: `pixi run pytest strategy-project/tests/test_strategy_engine.py strategy-project/tests/test_strategy_scaffold.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/strategy.py strategy-project/tests/test_strategy_engine.py
git commit -m "feat(strategy): unified trade engine with masks and tradable exit handling"
```

---

## Task 10: metrics 按版本分组

**Files:**
- Modify: `strategy-project/src/metrics.py`
- Test: `strategy-project/tests/test_metrics.py`

`calculate_metrics` 已修复（按 exit_date 排序的回撤）。新增 `metrics_by_version`。

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from metrics import calculate_metrics, metrics_by_version

def _trades():
    return pd.DataFrame([
        {"strategy_version": "baseline_first_day_momentum_daily", "return": 0.1, "net_pnl": 100, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
        {"strategy_version": "baseline_first_day_momentum_daily", "return": -0.05, "net_pnl": -50, "entry_price": 10, "shares": 10, "exit_date": "20260108", "entry_date": "20260105", "holding_days": 3},
        {"strategy_version": "improved_grey_market_filter", "return": 0.2, "net_pnl": 200, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
    ])

def test_drawdown_uses_exit_date_order():
    m = calculate_metrics(_trades())
    assert m["trade_count"] == 3
    assert m["max_drawdown"] <= 0

def test_metrics_by_version_splits():
    out = metrics_by_version(_trades())
    assert set(out) == {"baseline_first_day_momentum_daily", "improved_grey_market_filter"}
    assert out["improved_grey_market_filter"]["trade_count"] == 1
    assert out["baseline_first_day_momentum_daily"]["trade_count"] == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_metrics.py -q`
Expected: FAIL（metrics_by_version 未定义）

- [ ] **Step 3: 在 metrics.py 末尾追加**

```python
def metrics_by_version(trades: pd.DataFrame) -> dict[str, dict[str, float]]:
    if trades.empty or "strategy_version" not in trades.columns:
        return {}
    return {
        str(version): calculate_metrics(group.reset_index(drop=True))
        for version, group in trades.groupby("strategy_version", sort=True)
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_metrics.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/metrics.py strategy-project/tests/test_metrics.py
git commit -m "feat(strategy): add metrics_by_version"
```

---

## Task 11: 报告表格（对照 + 敏感性 + 分层）

**Files:**
- Modify: `strategy-project/src/report_tables.py`
- Test: `strategy-project/tests/test_report_tables.py`

新增三个纯函数返回 markdown 文本，便于测试；`write_report_template` 升级为接收对照/敏感性/分层并填实。

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from report_tables import comparison_table, sensitivity_table, stratify_by_quantile

def test_comparison_table_lists_versions():
    by_ver = {
        "baseline_first_day_momentum_daily": {"trade_count": 5, "win_rate": 0.4, "total_return": 0.1, "max_drawdown": -100, "average_holding_days": 2.0, "profit_factor": 1.2},
        "improved_grey_market_filter": {"trade_count": 2, "win_rate": 0.5, "total_return": 0.2, "max_drawdown": -50, "average_holding_days": 2.0, "profit_factor": 1.5},
    }
    md = comparison_table(by_ver)
    assert "baseline_first_day_momentum_daily" in md and "improved_grey_market_filter" in md
    assert "trade_count" in md

def test_sensitivity_table_lists_scales():
    rows = {0.5: {"total_return": 0.3}, 1.0: {"total_return": 0.2}, 2.0: {"total_return": 0.0}}
    md = sensitivity_table(rows)
    assert "0.5" in md and "2.0" in md

def test_stratify_by_quantile_groups():
    trades = pd.DataFrame({"return": [0.1, 0.2, -0.1, 0.05], "public_subscription_multiple": [10, 200, 5, 150]})
    out = stratify_by_quantile(trades, "public_subscription_multiple", bins=2)
    assert len(out) >= 1
    assert "count" in out.columns and "avg_return" in out.columns
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_report_tables.py -q`
Expected: FAIL（函数未定义）

- [ ] **Step 3: 重写 report_tables.py**

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

_COMPARE_KEYS = ["trade_count", "win_rate", "total_return", "max_drawdown", "average_holding_days", "profit_factor"]


def comparison_table(by_version: dict[str, dict[str, float]]) -> str:
    df = pd.DataFrame(by_version).T
    cols = [c for c in _COMPARE_KEYS if c in df.columns]
    return df[cols].reset_index(names="strategy_version").to_markdown(index=False)


def sensitivity_table(rows: dict[float, dict[str, float]]) -> str:
    df = pd.DataFrame(rows).T
    return df.reset_index(names="cost_scale").to_markdown(index=False)


def stratify_by_quantile(trades: pd.DataFrame, column: str, *, bins: int = 3) -> pd.DataFrame:
    work = trades.dropna(subset=[column]).copy()
    if work.empty:
        return pd.DataFrame(columns=["bucket", "count", "avg_return"])
    work["bucket"] = pd.qcut(work[column], q=min(bins, work[column].nunique()), duplicates="drop")
    grouped = work.groupby("bucket", observed=True)["return"].agg(count="count", avg_return="mean")
    return grouped.reset_index()


def write_report_template(
    metrics: dict[str, float],
    path: Path,
    *,
    by_version: dict[str, dict[str, float]] | None = None,
    sensitivity: dict[float, dict[str, float]] | None = None,
    coverage: dict | None = None,
    stratification_md: str = "",
) -> None:
    compare_md = comparison_table(by_version) if by_version else "(无对照数据)"
    sens_md = sensitivity_table(sensitivity) if sensitivity else "(无敏感性数据)"
    cov_md = "\n".join(f"- {k}: {v}" for k, v in (coverage or {}).items()) or "(无 coverage)"
    content = f"""# IPO / New Listing Daily Strategy Research

## Executive Summary

- 总 trade_count: {metrics.get("trade_count", 0)}
- win_rate: {metrics.get("win_rate", 0.0):.4f}
- total_return: {metrics.get("total_return", 0.0):.4f}
- max_drawdown: {metrics.get("max_drawdown", 0.0):.2f}

## Data

API 下载覆盖、缺失/停牌/无成交，及自行调研的 IPO/暗盘来源与可靠性：

{cov_md}

## Strategy Definition

- Baseline：首日动量（day1 close/open-1 > 阈值，day2 open 入场，持 K 日，止损/止盈，扣费）。
- Improved：在 baseline 上叠加暗盘溢价主过滤（grey_change_pct >= 阈值），缺暗盘数据者不入场。
- 无未来函数：信号仅用 day1 与上市前/上市时点的外部数据；执行价 day2 open。
- 成本：买/卖 bps + 滑点 + 最低费，按成交额计。

## Results

### Baseline vs Improved

{compare_md}

### Cost Sensitivity（全策略 total_return 等）

{sens_md}

### IPO 特征分层（按超购倍数）

{stratification_md or "(无分层数据)"}

## Analysis

（解释收益/亏损来源、改进是否稳健、暗盘过滤的作用与样本量限制。）

## Next Steps

（按上市月滚动阈值、多因子组合、扩大样本、更真实的执行建模。）
"""
    path.write_text(content, encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过**

Run: `pixi run pytest strategy-project/tests/test_report_tables.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/report_tables.py strategy-project/tests/test_report_tables.py
git commit -m "feat(strategy): report comparison, cost sensitivity, stratification tables"
```

---

## Task 12: backtest 编排（两版本 + 敏感性 + 全产物）

**Files:**
- Modify: `strategy-project/src/backtest.py`
- Test: `strategy-project/tests/test_backtest_integration.py`

- [ ] **Step 1: 写失败测试（用临时目录跑全链路）**

```python
import json
import pandas as pd
import backtest

def test_run_backtest_writes_outputs(tmp_path, monkeypatch):
    # 构造最小 features + daily，落到临时 RAW/PROCESSED/REPORTS
    raw, processed, reports = tmp_path / "raw", tmp_path / "processed", tmp_path / "reports"
    for d in (raw, processed, reports):
        d.mkdir()
    monkeypatch.setattr(backtest, "RAW_DIR", raw)
    monkeypatch.setattr(backtest, "PROCESSED_DIR", processed)
    monkeypatch.setattr(backtest, "REPORTS_DIR", reports)

    features = pd.DataFrame([{
        "symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260105",
        "baseline_signal": True, "grey_change_pct": 0.2, "premium_to_ipo_price": 0.2,
        "public_subscription_multiple": 50.0,
    }])
    features.to_parquet(processed / "features.parquet", index=False)
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260106", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260107", "open": 107, "high": 110, "low": 104, "close": 109, "volume": 10, "turnover": 1, "previous_close": 107, "suspend_flag": 0},
    ])
    daily.to_parquet(raw / "daily_bars.parquet", index=False)
    (raw / "cost_model.json").write_text(json.dumps({"buy_cost_bps": 12, "sell_cost_bps": 22, "slippage_bps": 10, "min_fee": 5}), encoding="utf-8")
    (raw / "coverage_summary.json").write_text(json.dumps({"symbol_count": 1}), encoding="utf-8")

    backtest.main()

    trades = pd.read_csv(reports / "trades.csv")
    assert set(trades["strategy_version"]) <= {"baseline_first_day_momentum_daily", "improved_grey_market_filter"}
    metrics = json.loads((reports / "metrics.json").read_text())
    assert "by_version" in metrics and "overall" in metrics and "cost_sensitivity" in metrics
    assert (reports / "research_report.md").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `pixi run pytest strategy-project/tests/test_backtest_integration.py -q`
Expected: FAIL（metrics.json 无 by_version/cost_sensitivity 等）

- [ ] **Step 3: 重写 backtest.py**

```python
from __future__ import annotations

import json

import pandas as pd

from config import COST_SENSITIVITY_SCALES, DEFAULT
from costs import load_cost_model, scale_cost_model
from metrics import calculate_metrics, metrics_by_version
from paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR
from report_tables import stratify_by_quantile, write_report_template
from strategy import baseline_mask, generate_trades, improved_mask

VERSIONS = (
    ("baseline_first_day_momentum_daily", baseline_mask),
    ("improved_grey_market_filter", improved_mask),
)


def run_all_versions(features, daily, cost_model, config=DEFAULT) -> pd.DataFrame:
    frames = [generate_trades(features, daily, cost_model, version=v, mask=m, config=config) for v, m in VERSIONS]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def cost_sensitivity(features, daily, cost_model, config=DEFAULT) -> dict[float, dict[str, float]]:
    out = {}
    for scale in COST_SENSITIVITY_SCALES:
        trades = run_all_versions(features, daily, scale_cost_model(cost_model, scale), config)
        out[scale] = calculate_metrics(trades)
    return out


def main() -> int:
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    daily = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    cost_model = load_cost_model(RAW_DIR / "cost_model.json")
    coverage = {}
    cov_path = RAW_DIR / "coverage_summary.json"
    if cov_path.exists():
        coverage = json.loads(cov_path.read_text(encoding="utf-8"))

    trades = run_all_versions(features, daily, cost_model)
    by_version = metrics_by_version(trades)
    overall = calculate_metrics(trades)
    sensitivity = cost_sensitivity(features, daily, cost_model)

    strat_md = ""
    if not trades.empty and "public_subscription_multiple" in features.columns:
        merged = trades.merge(features[["symbol", "public_subscription_multiple"]].drop_duplicates("symbol"), on="symbol", how="left")
        strat = stratify_by_quantile(merged, "public_subscription_multiple", bins=3)
        strat_md = strat.to_markdown(index=False) if not strat.empty else ""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    trades.to_csv(REPORTS_DIR / "trades.csv", index=False)
    metrics_payload = {
        "overall": overall,
        "by_version": by_version,
        "cost_sensitivity": {str(k): v for k, v in sensitivity.items()},
    }
    (REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report_template(overall, REPORTS_DIR / "research_report.md",
                          by_version=by_version, sensitivity=sensitivity, coverage=coverage, stratification_md=strat_md)
    print(json.dumps(metrics_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过 + 全测试套件**

Run: `pixi run pytest strategy-project/tests -q`
Expected: PASS（含旧 scaffold 测试）

- [ ] **Step 5: Commit**

```bash
git add strategy-project/src/backtest.py strategy-project/tests/test_backtest_integration.py
git commit -m "feat(strategy): orchestrate baseline+improved with cost sensitivity and report"
```

---

## Task 13: 采集外部数据（ipo_info + grey_market）

**Files:**
- Create: `strategy-project/data/external/ipo_info.csv`
- Create: `strategy-project/data/external/grey_market.csv`

**这是数据采集任务，不是 TDD。** 处理流程：

- [ ] **Step 1: 列出标的**

Run: `pixi run python -c "import pandas as pd; print('\n'.join(pd.read_parquet('research-data/ipo_universe.parquet')['symbol']))"`
得到 65 支 symbol + 名称。

- [ ] **Step 2: 逐 symbol 公开来源调研**

对每支：HKEX 新股页 / AAStocks / 财华社 等，收集 `ipo_info` 与 `grey_market` 字段。规则：
- 每行必须填 `source_url` 或 `source_note`、`collected_at`。
- **缺失值留空（空字符串），绝不填 0**（文档红线）。
- 不确定的值标注于 `source_note`。

> 现实约束：助手知识截止 2026-01，2026 新股需联网检索（WebSearch/WebFetch），覆盖率可能不全——按实际可得填，缺失如实留空，覆盖率由 §Task 6 的 `external_coverage` 统计、写入报告。

- [ ] **Step 3: 按模板表头写两个 CSV**

表头严格用 `external_data.IPO_COLS` / `GREY_COLS` 顺序（见 Task 6）。

- [ ] **Step 4: 校验加载与覆盖率**

Run: `pixi run python -c "import sys; sys.path.insert(0,'strategy-project/src'); from external_data import load_external, external_coverage; import pandas as pd; ipo,grey=load_external('strategy-project/data/external'); uni=pd.read_parquet('research-data/ipo_universe.parquet'); print(external_coverage(uni,grey,key='grey_change_pct',label='grey_market')); print(external_coverage(uni,ipo,key='public_subscription_multiple',label='ipo'))"`
Expected: 打印两个覆盖率字典，比例合理。

- [ ] **Step 5: Commit**

```bash
git add strategy-project/data/external/ipo_info.csv strategy-project/data/external/grey_market.csv
git commit -m "data(strategy): collected IPO fundamentals and grey-market with sources"
```

---

## Task 14: 跑通全链路 + 完稿报告 + 最终验证

**Files:**
- 产物：`data/raw/*`、`data/processed/features.parquet`、`reports/*`
- Modify（完稿）：`strategy-project/reports/research_report.md` 的 Analysis / Next Steps 文字

- [ ] **Step 1: 起 research API 并下载（真实 HTTP 路径）**

Run（后台）：`pixi run serve-research &` 然后 `pixi run download`
Expected: 打印 coverage_summary（含 suspended_rows 等），`data/raw/` 四产物生成。

- [ ] **Step 2: 特征 + 回测**

Run: `pixi run features && pixi run backtest`
Expected: `reports/trades.csv`（含两 strategy_version）、`reports/metrics.json`（overall/by_version/cost_sensitivity）、`reports/research_report.md` 生成。

- [ ] **Step 3: 全测试套件**

Run: `pixi run test`
Expected: 全 PASS。

- [ ] **Step 4: 人工完稿报告 Analysis/Next Steps**

基于实际 metrics 写：改进版相对 baseline 的差异、暗盘过滤是否提升、成本敏感性结论、样本量与外部数据覆盖率局限。

- [ ] **Step 5: 最终 Commit**

```bash
git add strategy-project/reports/research_report.md
git commit -m "docs(strategy): finalize research report with results"
```

> 注：`data/raw`、`data/processed`、`reports/*` 受 `.gitignore` 约束（仅保留 .gitkeep）。报告 `research_report.md` 是否纳入版本控制按提交要求决定；如需提交需 `git add -f`。

---

## Self-Review（对照 spec 与 docs/strategy-project.md）

- **Required Outputs（8 产物）**：Task 7（raw 四件）、Task 8（features）、Task 12（reports 三件）✅
- **Trade log 15 字段**：Task 9 trade dict 完整 ✅
- **Metrics 10 字段**：沿用 `calculate_metrics`（scaffold 已含），Task 10 分版本 ✅
- **Baseline 规则 1–8**：Task 8 信号 + Task 9 执行/每股票一笔 ✅
- **4 条禁止**：无未来函数（Task 8/9 仅用 day1+point-in-time 外部）、扣成本（Task 5/9）、停牌缺失处理（Task 4/7/8/9，移除 fillna0）、非只报 gross（Task 10/11 net+敏感性）✅
- **Required Improvement（外部数据方向 + 假设 + 对照 + 不堆参数）**：Task 6/8/9/11 ✅
- **Candidate External Data（两模板 + 来源 + 缺失不填 0 + 覆盖率）**：Task 6/13，loader 强制 NaN、覆盖率统计、报告说明 ✅
- **Expected Workflow 命令**：Task 1 pixi tasks 包装原命令 ✅
- **占位扫描**：无 TBD；各步含完整代码/命令。
- **类型一致性**：`generate_trades(..., version, mask, config)`、`baseline_mask`/`improved_mask`、`metrics_by_version`、`scale_cost_model`、`normalize_daily`（返回含 `tradable`）跨任务签名一致。
- **已知缺口**：Task 13 外部数据真实覆盖率取决于公开可得性与联网检索，按实际填、缺失如实留空（已在计划与报告中声明）。
