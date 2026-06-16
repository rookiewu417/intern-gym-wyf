# 策略项目正式设计 — IPO / New Listing Daily Strategy Research

日期：2026-06-15
依据：严格遵从 `docs/strategy-project.md`（一切以该文档为准）
范围：`strategy-project/`（方案 A：在现有 scaffold 上扩展，不重写）

---

## 1. 目标与研究问题

复现并改进港股新股「首日表现 → 后续数日收益」的日线策略，扣成本后评估可交易性，并用自行调研的 IPO/暗盘外部数据改善过滤与分层。对应文档「闭环 7 步」与「Research Question」。

## 2. 决策摘要（已与用户确认）

| 维度 | 决策 |
|---|---|
| 工程方案 | A — 原地扩展 scaffold，最小改动，遵循既有结构 |
| 交付定位 | 稳健达标（正确性优先），但纳入外部数据以完全遵从文档第 6 步 |
| Baseline | First-Trading-Day Daily Momentum（保留为对照，文档规则 1–8） |
| 改进方向 | 依赖外部数据：**主过滤 = 暗盘溢价**，**分层 = IPO 特征**（超购倍数/中签率/保荐人/行业） |
| 外部数据 | 同时采集 `grey_market` + `ipo_info` 两模板，记录来源，缺失留空不填 0 |
| 环境 | pixi |

## 3. 架构与流水线（方案 A）

保持文档「Expected Workflow」的三段命令不变，内部扩展：

```
download_data.py  →  build_features.py  →  backtest.py
   data/raw/            data/processed/        reports/
```

新增/修改：
- `src/config.py`：集中参数（threshold、holding_days、stop/take、notional、暗盘溢价阈值、分位、cost 缩放系数、外部数据缺失策略开关）。集中可调，避免散落硬编码（对应 Engineering Quality「参数配置合理」）。
- `strategy_version` 维度：baseline 与 improved 复用**同一回测引擎** `generate_trades(...)`，输出合并 `trades.csv`（含 `strategy_version` 列），`metrics.json` 内含每版本 metrics + 对照。
- `src/external_data.py`（新）：加载/校验 `data/external/ipo_info.csv`、`grey_market.csv`，产出覆盖率统计。
- 现有正确性修复见 `2026-06-15-strategy-known-issues.md`（① 持仓窗口变量覆盖、② 回撤排序口径，均已修并验证）。

单元边界：download（取数+归一化+coverage）/ external_data（外部加载+覆盖率）/ build_features（首日特征+外部 join）/ strategy（信号+回测引擎）/ costs / metrics / report_tables，各司其职、可独立测试。

## 4. 数据层

### 4.1 下载与 coverage 自查（文档 Provided API）
- 默认 HTTP API（`http://127.0.0.1:9041`，`--start 2026-01-01`）；`--source-root ../research-data` 本地兜底（测试/离线）。
- `data/raw/` 产出：`ipo_universe.parquet`、`daily_bars.parquet`、`cost_model.json`、`coverage_summary.json`。
- `coverage_summary.json` 扩展字段：`symbol_count`、`daily_rows`、`date_min/max`、`missing_daily_symbols`、`duplicate_daily_keys`、`suspended_rows`、`zero_volume_rows`、`missing_ohlc_rows`、以及外部数据覆盖率（见 4.3）。

### 4.2 缺失/停牌处理（文档红线；替换 fillna(0)；对应 Task #7）
统一口径：`suspend_flag==1` / 无 open / `volume==0` / 缺失 daily 行 = **不可交易**。
- 信号/入场：若 day1 或 day2 不可交易 → 该 symbol 不产生 trade。
- 持仓期：不可交易日不触发止损/止盈；若到期日落在不可交易日，顺延至下一有效交易日 close 出场。
- 实现：移除三层 `fillna(0)`；保留缺失为 NaN 并在回测前显式筛除/标记，不伪造 0 价 bar。文档禁止「随意填 0」「忽略停牌/无成交」。

### 4.3 外部数据采集（文档 Candidate External Data；两模板都填）
- `data/external/ipo_info.csv`（字段照模板）：symbol, listing_date, ipo_price, offer_price_low, offer_price_high, sponsor, industry, public_subscription_multiple, one_lot_success_rate, source_url, source_note, collected_at。
- `data/external/grey_market.csv`（字段照模板）：symbol, grey_market_date, grey_close, grey_change_pct, premium_to_ipo_price, source_url, source_note, collected_at。
- 采集方式：对 65 支标的通过公开来源（HKEX/AAStocks/财华社等）研究，**每行必须记 `source_url`/`source_note`**；缺失值**留空，不填 0**（文档强制）。
- 现实约束（诚实声明）：助手知识截止 2026-01，2026 新股数据需联网检索，覆盖率可能不全；`coverage_summary.json` 与报告需如实给出外部数据覆盖率与可靠性评估（Data Work 评分项）。

## 5. 特征工程（build_features.py）
对每个 symbol 取前两条有效日线：
- day1 特征：`first_day_open/high/low/close`、`first_day_return_vs_open = close/open-1`、`first_day_volume/turnover`。
- entry：`entry_date = day2.trade_date`、`entry_open`。
- `baseline_signal = first_day_return_vs_open > threshold (默认 0.05) AND day2 可交易`。
- 左 join 外部数据（按 symbol），带入 `grey_change_pct`、`premium_to_ipo_price`、`public_subscription_multiple`、`one_lot_success_rate`、`sponsor`、`industry`（缺失为 NaN）。
- 产出 `data/processed/features.parquet`。

## 6. Baseline 策略（文档规则 1–8，保留为对照）
1. 第一条有效 daily bar 为 day1；2. `first_day_return=close/open-1`；3. `>threshold` 出多头信号；4. 入场 = day2 open（含滑点）；5. 持有 K=3 交易日；6. 止损 8% / 止盈 20%（可配）；7. 扣买卖费+滑点+最低费；8. 每股票最多一笔。`strategy_version="baseline_first_day_momentum_daily"`。

## 7. 改进策略（依赖外部数据）
`strategy_version="improved_grey_market_filter"`。
- **主过滤（暗盘溢价）**：在 baseline_signal 基础上，额外要求 `grey_change_pct >= g`（默认 g=0，即暗盘未破发）或 `premium_to_ipo_price >= p`（二选一，config 可切）。
- **缺失外部数据处理**：某 symbol 无暗盘数据 → 不进入 improved 多头集（不填 0、不默认通过），并计入覆盖率报告。
- **分层分析（IPO 特征）**：对 baseline/improved 交易按 `public_subscription_multiple` 分位、`one_lot_success_rate`、`industry`、`sponsor` 分层统计收益，作为「调研作为分层分析」的落地（文档第 6 步）。
- **无未来函数论证**：暗盘发生在上市前夜、超购倍数在招股结束即知，均为 day2 入场前的 point-in-time 信息；过滤不使用 day2 之后任何数据，符合文档两条禁止。
- **不堆参数**：仅 1 个主过滤阈值；分层不参与择时，只做解释。

## 8. 成本模型（costs.py，文档 Cost Model）
买 12bps / 卖 22bps / 滑点 10bps / 最低 5 HKD；费用 = max(min_fee, notional×bps/1e4)，**按成交额计 + 最低收费**。滑点：买价上抬、卖价下压。报告明确口径。

## 9. 回测引擎（统一，strategy.py）
- 单一 `generate_trades(features, daily, cost_model, *, version, filter_fn, config)`：baseline 与 improved 仅传入不同 `filter_fn`，共用执行/成本/出场逻辑。
- 出场：持仓窗口内命中止损/止盈即出，否则末有效日 close 出场；含 4.2 的停牌顺延。
- 输出 trade log（字段见 §11），`holding_days` 用已修正的 `held_days`（窗口上界 = K）。

## 10. 指标与对照（metrics.py + report_tables.py）
- 每 `strategy_version` 输出文档 10 项 metrics：`trade_count, win_rate, average_return, average_win, average_loss, profit_factor, total_return, max_drawdown, turnover, average_holding_days`。
- `max_drawdown` 按 `exit_date` 排序的已实现 PnL 序列（已修，口径在报告注明）。
- **baseline vs improved 对照表** + **成本敏感性**（0.5×/1×/2× 成本各跑一遍）+ **IPO 特征分层表**。

## 11. 输出产物（文档 Required Outputs，路径/字段一字不差）
```
data/raw/ipo_universe.parquet
data/raw/daily_bars.parquet
data/raw/cost_model.json
data/raw/coverage_summary.json
data/processed/features.parquet
reports/trades.csv
reports/metrics.json
reports/research_report.md
```
Trade log 15 字段：`symbol, coverage_start, entry_date, entry_price, exit_date, exit_price, shares, gross_pnl, fees, slippage, net_pnl, return, exit_reason, holding_days, strategy_version`。

## 12. 研究报告（reports/research_report.md，替换模板占位）
按现有模板章节填实：Executive Summary、Data（API 覆盖、缺失/停牌、外部 IPO/暗盘来源与覆盖率可靠性）、Strategy Definition（baseline + improved + 执行/成本模型 + 无未来函数保障）、Results（baseline vs improved、trade log、成本敏感性、分层）、Analysis（收益/亏损来源、稳健性）、Next Steps。

## 13. 测试计划（pytest，覆盖关键坑）
- 无未来函数：信号仅依赖 day1/外部 point-in-time，扰动 day2 之后数据不改变信号。
- 成本/滑点数学：trade_cost 取 max(min_fee, …)、滑点方向正确。
- 停牌/缺失：suspend/无 open/zero-volume 行被正确跳过，不产生 0 价交易。
- 外部数据：缺失外部数据的 symbol 不进入 improved 集；覆盖率统计正确。
- 持仓窗口：`holding_days ≤ K`（回归 bug①）。
- 回撤口径：max_drawdown 与按 exit_date 重排一致（回归 bug②）。
- 改进过滤确实改变交易集（improved ⊆ baseline，且数量/收益不同）。

## 14. 环境（pixi）
- 仓库根 `pixi.toml`：python 3.12；deps `pandas>=2.2, pyarrow>=15, pytest>=8, tabulate`（报告表格）。
- tasks：`serve-research`（起 API）、`download`/`features`/`backtest`（cwd=strategy-project，包装文档原命令）、`pipeline`（串联）、`test`（仓库根 pytest）。
- 不引入真实 token/生产服务（文档 Boundaries）。

## 15. 已知限制与下一步
- 65 支样本量小，结论统计力有限；报告需声明。
- 外部数据覆盖率受公开可得性/知识截止限制；缺失部分如实报告。
- 暗盘横截面阈值为固定值；下一步可做按上市月滚动或多因子组合。

## 16. 文档合规对照（自查）
Required Outputs ✅ / Trade log 15 字段 ✅ / Metrics 10 字段 ✅ / Baseline 规则 1–8 ✅ / 4 条禁止 ✅ / Required Improvement（外部数据方向 + 说明假设 + 对照 + 不堆参数）✅ / Candidate External Data（两模板 + 来源 + 缺失不填 0 + 覆盖率说明）✅ / Expected Workflow 命令 ✅。
