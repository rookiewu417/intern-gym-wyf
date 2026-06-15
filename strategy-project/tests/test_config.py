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
