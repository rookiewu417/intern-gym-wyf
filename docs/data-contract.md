# Data Contract

样本数据位于：

```text
sample-data/
```

默认包含 5 支股票：

```text
02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK
```

## Tables

| table | format | 用途 |
| --- | --- | --- |
| `silver_minute_bars_v1/part-00000.parquet` | parquet | 分钟 K 线 |
| `silver_trade_ticks_v1/part-00000.parquet` | parquet | 逐笔成交，用于大额交易 |
| `silver_broker_queue_v1/part-00000.parquet` | parquet | broker queue 历史快照/回放 |
| `silver_ccass_holdings_v1/part-00000.parquet` | parquet | CCASS 持仓，可作为 bonus |
| `silver_daily_bars_v1.csv` | csv | daily baseline |
| `silver_instruments_v1.csv` | csv | 股票中文名 |
| `silver_broker_mapping_v1.csv` | csv | broker code 到券商名映射 |
| `manifest.json` | json | 数据包说明 |

## Regenerate

```bash
make build-data SILVER_ROOT=/path/to/full/silver-root
```

或：

```bash
python scripts/build_sample_data.py \
  --source-silver-root /path/to/full/silver-root \
  --output-root sample-data \
  --symbols 02723.HK,02675.HK,00100.HK,02513.HK,06082.HK
```

## Important Semantics

- 样本数据可能包含不同 source date，这是故意保留的测试点。
- 前端和后端都不能把旧日期 alerts 混进当前 effective day。
- broker queue 的价格档可能稀疏；不要假设档位连续。
- broker queue 是快照，不是增量。
