# Strategy Project — 修复与优化计划（2026-06-15）

## 背景
对照 `docs/strategy-project.md` rubric 的公正评审给出 92/100，并定位四处确切缺陷。本计划用 TDD 逐项修复，目标是消除"误导性头条指标"和"执行价建模偏粗"，让逐策略对照与受控实验之外的呈现也站得住。

## 修复项（TDD：先红后绿）

### Fix 1 — profit_factor 无亏损报 inf
- 文件：`src/metrics.py`
- 现状：`gross_loss == 0` 时返回 `0.0`（全胜看起来像最差）。
- 目标：`gross_profit > 0 and gross_loss == 0 → inf`；全 0 → `0.0`。
- 测试：`tests/test_metrics.py::test_profit_factor_infinite_when_no_losses`

### Fix 2 — 指标口径统一为复利百分比
- 文件：`src/metrics.py`、`src/plots.py`
- 现状：`total_return` = 逐笔收益之和；`max_drawdown` = 累计 net_pnl 的绝对港币。量纲不一致、难解读。
- 目标：按 exit_date 排序构造序贯等额复利权益 `equity=(1+return).cumprod()`：
  - `total_return = equity[-1] - 1`
  - `max_drawdown = ((equity-equity.cummax())/equity.cummax()).min()`（≤0 的百分比）
  - equity_curve.png 改画归一化权益（起点 1.0）。
- 测试：`test_total_return_is_compounded`、`test_max_drawdown_is_percentage`

### Fix 3 — 止损/止盈按触发价成交
- 文件：`src/strategy.py`
- 现状：触发止损/止盈时仍用当日 `close` 成交，系统性错估。
- 目标：止损→`stop_level`、止盈→`take_level` 成交（再叠加卖出滑点）；未触发→末个有效交易日 close。
- 测试：`test_stop_loss_fills_at_stop_level`、`test_take_profit_fills_at_take_level`

### Fix 4 — 消除重复计数（overall + cost-sensitivity）
- 文件：`src/backtest.py`、`src/report_tables.py`、`tests/test_backtest_integration.py`
- 现状：`improved ⊆ baseline`，concat 成 26 笔，`overall` 与 `cost_sensitivity` 重复计 12 笔。
- 目标：
  - `cost_sensitivity` 返回 `{version: {scale: metrics}}`（按版本，无重复计数）。
  - 去掉 union `overall`；metrics.json 顶层以 `by_version` 为权威。
  - Executive Summary 并列 baseline / improved（不再合并）。
- 测试：更新 `test_run_backtest_writes_outputs` 结构断言。

## 收尾
- `pixi run test` 全绿。
- `pixi run pipeline` 重跑，确认幂等。
- 用新生成的 `research_report.md` 数字同步手写的 `README.md`（total_return 等口径已变）。
- 提交（git: rookiewu417）。

## 进度

### 2026-06-15 完成
- [x] **Fix 1** profit_factor 无亏损 → inf（`metrics.py`）；测试 `test_profit_factor_infinite_when_no_losses`。
- [x] **Fix 2** 复利权益口径：`total_return`=复利、`max_drawdown`=百分比（`metrics.py`、`plots.py`）；测试 `test_total_return_is_compounded`、`test_max_drawdown_is_percentage`。
- [x] **Fix 3** 止损/止盈按触发价成交（`strategy.py`）；测试 `test_stop_loss_fills_at_stop_level`、`test_take_profit_fills_at_take_level`。
- [x] **Fix 4** 去重复计数：`cost_sensitivity` 按版本、去 union `overall`、IPO 分层基于 baseline（`backtest.py`、`report_tables.py`）；测试更新 `test_run_backtest_writes_outputs`。
- [x] **连带修复** 受控实验 verdict 稳健化（单调性 + 全样本秩相关，不被首尾误导），删除冗余分层 bullet；测试 `test_analysis_*`。修正成交价后 **Spearman 由 +0.38 → −0.12**，verdict 自动转为"区分力有限/尾部驱动"。
- [x] **优化** `metrics.json` 转标准 JSON（inf/nan → null，`allow_nan=False`）；测试断言无 `Infinity`/`NaN`，jq 可解析。
- [x] 重跑 pipeline 幂等（两次零 diff）；README 数字与结论同步。
- [x] `pixi run test` → **30 passed**（原 23 + 新增 7）。

### 关键结论变化（修复带来的真实影响）
- baseline：−2.9%→**−15.3%**；improved：+24.0%→**+0.9%**（口径改复利 + 止盈封顶在 +20%，不再用 close 高估热门标的）。
- 暗盘溢价的"正向区分力"在修正成交价后**消失/转负**（Spearman −0.12、分层非单调、末档仅 2 笔），报告诚实改写。

### 2026-06-15 二次审计（再查 bug + 逐条核对文档）
- [x] **真 bug 修复**：复利 `max_drawdown` 漏算初始资金 1.0 峰值（首笔即亏会漏掉从起点跌下的回撤）→ `peak = equity.cummax().clip(lower=1.0)`；测试 `test_max_drawdown_counts_drop_from_initial_capital`。当前数据两版本 mdd 未变（最深回撤都在涨过 1.0 之后），但逻辑已在所有情况下正确。
- [x] **跳空验证**：14 笔触发全部为「盘中触及」（止损日 open>stop_level、止盈日 open<take_level），触发价成交在本数据集零失真。记录 gap-handling 为健壮性 Next Step（换数据集才需要）。
- [x] 文档逐条核对：Required Outputs / Trade log 15 字段 / Metrics 10 字段 / Baseline 规则 1–8 / 禁止项 4 / Red Flags 6 全部满足。
- [x] 观察（非 bug，可选优化）：① `ipo_universe.parquet` 未保留 `daily_rows` 列；② 报告未列具体 bps 数值（12/22/10/5）；③ 外部覆盖率分母用 universe 65 而非信号标的 14；④ sweep 表 profit_factor 报告显示 `inf` 而 metrics.json 为 `null`。
- [x] `pixi run test` → **31 passed**；pipeline 幂等。

### 2026-06-15 三次迭代（A 全部 + B + reversal baseline）
- [x] **A1** 报告列出具体成本数值（买入 12bps / 卖出 22bps / 滑点 10bps / 最低费 5 HKD）：`write_report_template` 加 `cost_model` 参数。
- [x] **A2** `ipo_universe.parquet` 保留 `daily_rows`：`normalize_universe`；测试 `test_normalize_universe_keeps_daily_rows`。
- [x] **A3** 外部覆盖率加报「信号标的」口径（grey 12/14 ≈ 85.7%，vs universe 0.18）：`external_coverage_from_features`。
- [x] **A4** inf/null 统一：报告显示 `∞`、metrics.json 记 `null`，Executive Summary 注释说明；`_pf` helper + `comparison_table`/`grey_sweep_table`；测试 `test_grey_sweep_table_shows_infinity_symbol`。
- [x] **B** gap-handling：止损 `min(stop_level, open)`、止盈 `max(take_level, open)`，跳空越过按当日 open 成交；测试 `test_stop_loss_gap_down_*`、`test_take_profit_gap_up_*`。当前数据 14 笔触发全为盘中触及，结果不变但逻辑健壮。
- [x] **reversal baseline**：`reversal_signal`（首日跌 > 5%）+ `reversal_mask` + `VERSIONS` 第三版 + Strategy Definition/Analysis/对照表纳入；测试 `test_reversal_signal_*`、`test_reversal_mask_*`、`test_analysis_includes_reversal_*`。真实结果 27 笔 −11.5%（pf 1.04），首日反转做多同样不可交易。momentum baseline 已保留作对照（合规）。
- [x] `pixi run test` → **38 passed**（+7）；pipeline 幂等；jq 解析 OK。

### 待用户决定
- [ ] 提交（当前分支 `strategy/optimize-100`）。
