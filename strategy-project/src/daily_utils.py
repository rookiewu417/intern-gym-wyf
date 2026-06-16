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
