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
