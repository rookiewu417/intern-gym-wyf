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

def test_reversal_signal_on_first_day_drop():
    # 3.HK：day1 跌 20%（close/open-1=-0.2），day2 可交易 -> reversal 命中、momentum 不命中
    daily = pd.DataFrame([
        {"symbol": "3.HK", "trade_date": "20260102", "open": 10, "high": 10, "low": 7, "close": 8, "volume": 100, "turnover": 1000, "previous_close": 12, "suspend_flag": 0},
        {"symbol": "3.HK", "trade_date": "20260105", "open": 8, "high": 9, "low": 8, "close": 8.5, "volume": 80, "turnover": 900, "previous_close": 8, "suspend_flag": 0},
    ])
    uni = pd.DataFrame({"symbol": ["3.HK"], "name": ["z"], "coverage_start": ["20260102"], "coverage_end": ["20260110"]})
    feats = build_daily_ipo_features(uni, daily, threshold=0.05).set_index("symbol")
    assert bool(feats.loc["3.HK", "reversal_signal"]) is True
    assert bool(feats.loc["3.HK", "baseline_signal"]) is False


def test_external_columns_joined():
    ipo, grey = _external()
    feats = build_daily_ipo_features(_universe(), _daily(), threshold=0.05, ipo_info=ipo, grey_market=grey).set_index("symbol")
    assert feats.loc["1.HK", "grey_change_pct"] == 0.2
    assert feats.loc["1.HK", "public_subscription_multiple"] == 50.0
    assert pd.isna(feats.loc["2.HK", "grey_change_pct"])  # 无外部数据 -> NaN
