# 策略项目 — 已知问题记录

日期：2026-06-15
范围：`strategy-project/` scaffold 正确性审计（目标：稳健达标交付）

四条问题，两类：现存代码可立即修的真 bug ×2，需在策略设计阶段端到端处理 ×2。

## ① [已修] strategy.py 持仓窗口变量覆盖（跨交易污染）

- 位置：`strategy-project/src/strategy.py` `generate_baseline_trades`
- 问题：循环内 `holding_days = int(path[...].shape[0])` 重新赋值了**函数入参** `holding_days`（默认 3）。下一只股票计算 `path = symbol_bars.iloc[entry_index : entry_index + max(1, holding_days)]` 时，用的是上一笔交易实际持有天数，而非预期的固定窗口。导致持仓窗口被前一笔交易结果污染、结果不可复现。
- 修复：计算值改名 `held_days`，trade dict 的 `"holding_days"` 用 `held_days`；入参 `holding_days` 只用于切片窗口，保持不变。

## ② [已修] metrics.py 回撤按非时间顺序计算

- 位置：`strategy-project/src/metrics.py` `calculate_metrics`
- 问题：`equity = pnl.cumsum()` 直接对传入顺序的 trades 累加。trades 来自按 symbol 排序的 features 迭代，**不是时间顺序**，因此 `max_drawdown` 是 symbol 序列下的回撤，无金融意义。
- 修复：计算权益曲线前 `ordered = trades.sort_values("exit_date")`，回撤基于按平仓日排序的已实现 PnL 序列。其余 order-independent 指标（win_rate/均值等）不受影响。报告需注明回撤为"已实现 PnL 按平仓日排序"口径。

## ③ [设计阶段处理] fillna(0) 伪造缺失/停牌 bar（红线）

- 位置：`download_data.normalize_daily`、`build_features.normalize_daily`、`strategy.normalize_daily` 三层均 `fillna(0)`
- 问题：缺失或停牌日的 OHLC/previous_close 被填成 0，会污染收益计算。评分红线"缺失值随意填 0""停牌/缺失处理不合理"。
- 为何不在此处单独修：正确修复需配合回测端的跳过/终止逻辑（否则 NaN 向下游传播），属端到端设计决策，归入策略设计。
- 计划：在设计中定义统一策略 —— `suspend_flag==1` / 无 open / `volume==0` / 缺失 daily 的行，从信号、入场、出场显式跳过或提前终止，而非填 0。对应 Task #7。

## ④ [已取代] 成交量确认分位的横截面未来函数（改进方向已变更）

- 原背景：若改进版用全样本成交量分位做阈值，会引入横截面未来函数。
- 现状：改进方向已由「成交量确认」改为「依赖外部数据（暗盘 + IPO 特征）过滤」，本条不再适用。
- 取而代之的外部数据设计约束见正式设计 spec：外部特征均为上市前/上市时点信息（暗盘=上市前夜、超购倍数=招股结束），相对 day2 入场无未来函数；缺失外部数据按缺失策略处理、不填 0，并报告覆盖率。对应 Task #8（已更新）。

## 验证（已执行 2026-06-15）

- strategy scaffold pytest：通过。
- 针对性校验（threshold=-1 全样本 65 笔）：`holding_days` 最大值 = 窗口 3（①修复生效，无跨笔污染）；`max_drawdown` = -79843.82，与按 `exit_date` 重排重算一致（②修复生效）。
