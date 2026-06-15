# Strategy Internship Project

项目名称：

```text
IPO / New Listing Intraday Strategy Research
```

目标是让策略实习生从数据下载开始，独立完成一个完整研究闭环：

1. 下载和校验数据。
2. 复现 baseline 策略。
3. 加入手续费和滑点。
4. 完成回测和结果分析。
5. 自主调研 IPO / 暗盘数据。
6. 构建至少一个改进特征。
7. 输出研究报告。

这个项目不要求接生产交易系统，也不要求做前端页面。重点考察策略研究能力、数据处理能力、回测正确性和报告表达。

## Research Question

港股新股上市初期存在较强日内波动和信息不对称。候选人需要研究：

```text
Opening range breakout 类策略在港股新股上市初期是否有效？
加入交易成本后是否仍有可交易性？
IPO / 暗盘相关公开信息能否改善策略过滤效果？
```

## Provided Data API

我们提供稳定 API 或本地等价数据包，候选人需要自己写 `download_data.py` 拉取并缓存。

建议 API 形态：

```text
GET /api/symbols/new-listings?start=2026-01-01&end=2026-06-30
GET /api/daily?symbol=02723.HK&start=2026-06-08&end=2026-06-12
GET /api/bars/1m?symbol=02723.HK&start=2026-06-08&end=2026-06-12
GET /api/trades?symbol=02723.HK&date=2026-06-08
GET /api/broker-queue?symbol=02723.HK&date=2026-06-08
GET /api/ipo-info?symbol=02723.HK
GET /api/cost-model
```

本地 parquet 等价形态：

```text
data/
  new_listings.parquet
  daily_bars.parquet
  minute_bars/
    trade_date=20260608/part-00000.parquet
  trade_ticks/
    trade_date=20260608/part-00000.parquet
  broker_queue/
    trade_date=20260608/part-00000.parquet
  ipo_info_seed.csv
  grey_market_template.csv
  cost_model.json
```

候选人可以先用本仓库 `sample-data` 开发，但代码结构必须支持替换成 HTTP API 或更大 parquet 数据包。

## Required Data

### New Listing Universe

用于定义股票池。

字段：

```text
symbol
name
listing_date
ipo_price
lot_size
board
sector
```

如可获取，建议包含：

```text
offer_price_low
offer_price_high
final_offer_price
shares_offered
public_offer_shares
international_offer_shares
market_cap_at_listing
```

### Daily Bars

用于判断交易日、停牌、daily baseline volume、上市后第 N 天。

字段：

```text
symbol
trade_date
open
high
low
close
volume
turnover
previous_close
suspend_flag
```

### Minute Bars

baseline 策略主数据。

字段：

```text
symbol
trade_date
bar_ts
open
high
low
close
volume
turnover
```

### Trade Ticks

用于滑点估计、大额交易确认、主动买卖方向特征。

字段：

```text
symbol
trade_date
tick_ts
price
volume
turnover
side
trade_id
active_broker_code
active_broker_name
```

### Broker Queue / L2 Queue

用于 bonus 或策略改进。

字段：

```text
symbol
trade_date
queue_ts
side
position
price
volume
broker_code
broker_name
participant_id
participant_name
```

注意：

- broker queue 是快照状态，不是订单流。
- 不能把 queue rows 简单累计为新增挂单。

### Cost Model

Baseline 必须考虑手续费和滑点。

建议提供：

```json
{
  "currency": "HKD",
  "buy_cost_bps": 12.0,
  "sell_cost_bps": 22.0,
  "slippage_bps": 10.0,
  "min_fee": 5.0
}
```

候选人需要在报告里说明：

- 买入成本；
- 卖出成本；
- 滑点模型；
- 最小费用；
- 是否按成交额或订单笔数计费。

如果候选人采用更细模型，应解释每一项来源：

```text
commission_bps
platform_fee_per_order
stamp_duty_bps
trading_fee_bps
sfc_levy_bps
ccass_fee_bps
min_commission
slippage_bps
```

## Bonus Data: IPO / Grey Market

Bonus 要求候选人自己搜索和调研公开来源，整理成结构化数据。

我们提供 schema 和少量 seed/template，但不替候选人完成调研。

### IPO Info

字段建议：

```text
symbol
name
listing_date
ipo_price
offer_price_low
offer_price_high
sponsor
underwriters
industry
market_cap
public_subscription_multiple
international_subscription_multiple
one_lot_success_rate
clawback_triggered
cornerstone_investors
```

可构建特征：

```text
pricing_position = (ipo_price - offer_price_low) / (offer_price_high - offer_price_low)
log_public_subscription_multiple
low_one_lot_success_rate_flag
top_sponsor_flag
industry_group
market_cap_bucket
```

### Grey Market / 暗盘

字段建议：

```text
symbol
grey_market_date
source
grey_open
grey_high
grey_low
grey_close
grey_volume
grey_change_pct
premium_to_ipo_price
```

可构建特征：

```text
grey_return = grey_close / ipo_price - 1
grey_intraday_range = grey_high / grey_low - 1
grey_volume_rank
grey_positive_flag
```

要求：

- 记录数据来源 URL 或来源说明。
- 说明数据可靠性。
- 缺失值不能随意填 0，需要明确处理。

## Baseline Strategy

策略：

```text
Opening Range Breakout for New Listings
```

股票池：

- 港股新股。
- 上市首日到上市后第 N 个交易日。
- 默认 N 可设为 5 或 10。

观察窗口：

```text
09:30 - 09:45
```

规则：

1. 记录 opening range high / low。
2. 如果 09:45 后价格向上突破 opening range high，做多。
3. 每只股票每天最多一笔交易。
4. 入场价使用下一根 bar open，或用 tick 数据模拟可成交价。
5. 止损：
   - 跌回 opening range midpoint；或
   - 固定亏损阈值，例如 `-2%`。
6. 止盈：
   - 固定盈利阈值，例如 `+4%`；或
   - 收盘前平仓。
7. 所有持仓必须在当日收盘前平掉。
8. 等权资金分配。
9. 必须扣除手续费和滑点。

禁止：

- 用 09:45 之后的数据决定是否入场。
- 用当日完整 K 线提前计算 signal。
- 直接用 close-to-close 收益替代可成交价格。
- 忽略停牌、无成交、缺失 K 线。

## Required Improvement

候选人需要在 baseline 之外实现一个改进版本。

改进方向可以任选一个：

1. Volume Confirmation

突破时当前 1m volume 大于过去 10 分钟均值。

2. Big Trade Confirmation

突破前后出现大额主动买入才入场。

3. Broker Queue Imbalance

买队列强于卖队列才入场。

4. IPO Feature Filter

使用超购倍数、一手中签率、定价位置、行业等特征过滤。

5. Grey Market Feature Filter

使用暗盘涨跌幅、暗盘成交量、暗盘溢价过滤。

6. Risk Management

动态止损、波动率调整仓位、交易成本约束。

要求：

- 只实现 1 个主要改进即可。
- 必须说明假设。
- 必须和 baseline 做对照。
- 不鼓励堆参数或过拟合。

## Backtest Requirements

### No Lookahead

任何 signal 在时间 `t` 生成，只能使用 `<= t` 的数据。

### Execution Model

候选人必须明确：

- 信号 bar；
- 入场 bar；
- 入场价格；
- 出场规则；
- 滑点；
- 手续费；
- 无成交时如何处理。

建议默认：

```text
entry_price = next_bar.open * (1 + slippage_bps / 10000)
exit_price = exit_bar.open_or_close * (1 - slippage_bps / 10000)
net_pnl = gross_pnl - buy_cost - sell_cost
```

如果使用 tick 数据，可以更精细，但必须解释。

### Portfolio Model

默认：

- 每笔固定资金；
- 或每日等权分配；
- 不允许无限资金重复买入。

必须输出 trade log。

Trade log 字段：

```text
symbol
trade_date
entry_ts
entry_price
exit_ts
exit_price
shares
gross_pnl
fees
slippage
net_pnl
return
exit_reason
strategy_version
```

## Metrics

必须输出：

```text
trade_count
win_rate
average_return
average_win
average_loss
profit_factor
total_return
max_drawdown
turnover
average_holding_minutes
```

建议输出：

```text
daily_pnl
symbol_level_pnl
listing_day_bucket_pnl
cost_sensitivity
```

成本敏感性建议：

```text
slippage_bps = 0, 5, 10, 20, 50
```

## Expected Repo Structure

```text
strategy-project/
  README.md
  data/
    raw/
    processed/
  notebooks/
  src/
    download_data.py
    build_features.py
    strategy.py
    backtest.py
    costs.py
    metrics.py
    report_tables.py
  tests/
  reports/
    research_report.md
    trades.csv
    metrics.json
```

## Required Scripts

### download_data.py

职责：

- 调 API 或读取 sample-data。
- 下载 universe、daily、minute、ticks、broker queue、cost model。
- 写入 `data/raw`。
- 输出数据覆盖 summary。

### build_features.py

职责：

- 构建 opening range features。
- 构建 volume / big trade / queue / IPO / grey market 特征。
- 写入 `data/processed/features.parquet`。

### backtest.py

职责：

- 运行 baseline。
- 运行 improved strategy。
- 输出 trade log 和 metrics。

### metrics.py

职责：

- 计算收益、回撤、胜率、profit factor、成本敏感性。

## Research Report

报告位置：

```text
reports/research_report.md
```

必须包含：

1. Executive Summary

- baseline 是否有效；
- 加入成本后结果如何；
- 改进是否有效；
- 最大风险是什么。

2. Data

- 数据来源；
- 股票池；
- 日期范围；
- 缺失值；
- 停牌/无成交处理；
- IPO / 暗盘数据来源。

3. Strategy Definition

- baseline 规则；
- 改进版规则；
- 交易成本；
- 滑点；
- 执行假设。

4. Results

- baseline metrics；
- improved metrics；
- trade count；
- drawdown；
- 分股票或分 listing day 分析。

5. Analysis

- 哪些股票贡献收益；
- 哪些环境下失效；
- 成本敏感性；
- 是否存在过拟合风险。

6. Next Steps

- 需要更多数据；
- 需要更真实撮合；
- 需要更严格风险控制。

## Evaluation Rubric

总分 100。

### Data Work - 30

- 能独立下载/缓存数据：8
- 数据 schema 清楚：6
- 数据校验和覆盖 summary：6
- 处理缺失、停牌、无成交：5
- IPO / 暗盘数据来源记录：5

### Backtest Correctness - 25

- 无未来函数：8
- 成本和滑点正确：6
- 交易时间和执行价格合理：5
- trade log 完整：3
- 可复现：3

### Strategy Reasoning - 20

- baseline 规则清楚：5
- 改进假设明确：5
- 对照实验合理：5
- 能解释收益和亏损来源：5

### Engineering Quality - 15

- 代码结构清楚：5
- 参数配置合理：3
- 测试覆盖关键函数：4
- README 可运行：3

### Communication - 10

- 报告清楚：4
- 图表/表格有解释：3
- 能说明限制和下一步：3

## Red Flags

- 忽略手续费和滑点。
- 使用未来数据。
- 只调参数不解释假设。
- 没有 trade log。
- 没有数据覆盖说明。
- IPO / 暗盘数据没有来源。
- 把 broker queue 当订单流累计。
- 结果只报收益，不报回撤和交易次数。

## Bonus

可加分项：

- 使用 IPO / 暗盘公开数据构建有效特征。
- 做成本敏感性分析。
- 做上市首日 vs 上市后第 N 日分层。
- 使用 tick 数据估计更真实滑点。
- 使用 broker queue imbalance 做过滤。
- 输出一份可复现 notebook 或 dashboard。

