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
