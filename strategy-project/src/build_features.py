from __future__ import annotations

import argparse
import json

import pandas as pd

from daily_utils import normalize_daily
from external_data import load_external
from paths import PROCESSED_DIR, RAW_DIR

_EXTERNAL_FEATURE_COLS = [
    "grey_change_pct", "premium_to_ipo_price",
    "public_subscription_multiple", "one_lot_success_rate", "sponsor", "industry",
]


def safe_return(end: float, start: float) -> float:
    return end / start - 1.0 if start else 0.0


def build_daily_ipo_features(
    universe: pd.DataFrame,
    daily_bars: pd.DataFrame,
    *,
    threshold: float = 0.05,
    ipo_info: pd.DataFrame | None = None,
    grey_market: pd.DataFrame | None = None,
) -> pd.DataFrame:
    daily = normalize_daily(daily_bars)
    universe = universe.copy()
    universe["symbol"] = universe["symbol"].astype(str).str.upper()
    rows = []

    for symbol, group in daily.groupby("symbol", sort=True):
        bars = group.sort_values("trade_date").reset_index(drop=True)
        tradable = bars[bars["tradable"]].reset_index(drop=True)
        if len(tradable) < 1:
            continue
        first = tradable.iloc[0]
        has_tradable_day2 = len(tradable) >= 2
        entry = tradable.iloc[1] if has_tradable_day2 else None
        first_day_return = safe_return(float(first["close"]), float(first["open"]))
        listing_row = universe[universe["symbol"] == symbol].head(1)
        coverage_start = str(first["trade_date"])
        name = ""
        if not listing_row.empty:
            coverage_start = str(listing_row.iloc[0].get("coverage_start") or coverage_start)
            name = str(listing_row.iloc[0].get("name") or "")
        rows.append({
            "symbol": symbol,
            "name": name,
            "coverage_start": coverage_start,
            "trade_date_1": str(first["trade_date"]),
            "first_day_open": float(first["open"]),
            "first_day_close": float(first["close"]),
            "first_day_high": float(first["high"]),
            "first_day_low": float(first["low"]),
            "first_day_return_vs_open": first_day_return,
            "first_day_volume": int(first["volume"]),
            "first_day_turnover": float(first["turnover"]),
            "entry_date": str(entry["trade_date"]) if entry is not None else "",
            "entry_open": float(entry["open"]) if entry is not None else float("nan"),
            "baseline_signal": bool(
                has_tradable_day2
                and first_day_return > threshold
                and float(entry["open"]) > 0
            ),
            # reversal 对照：首日大跌（< -threshold）后预期反转，day2 open 做多
            "reversal_signal": bool(
                has_tradable_day2
                and first_day_return < -threshold
                and float(entry["open"]) > 0
            ),
        })

    features = pd.DataFrame(rows)
    if features.empty:
        for col in _EXTERNAL_FEATURE_COLS:
            features[col] = pd.Series(dtype="object")
        return features

    features = _join_external(features, ipo_info, ["public_subscription_multiple", "one_lot_success_rate", "sponsor", "industry"])
    features = _join_external(features, grey_market, ["grey_change_pct", "premium_to_ipo_price"])
    for col in _EXTERNAL_FEATURE_COLS:
        if col not in features.columns:
            features[col] = pd.NA
    return features


def _join_external(features: pd.DataFrame, ext: pd.DataFrame | None, cols: list[str]) -> pd.DataFrame:
    if ext is None or ext.empty:
        for col in cols:
            features[col] = pd.NA
        return features
    ext = ext.copy()
    ext["symbol"] = ext["symbol"].astype(str).str.upper()
    keep = ["symbol"] + [c for c in cols if c in ext.columns]
    return features.merge(ext[keep].drop_duplicates("symbol"), on="symbol", how="left")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build daily first-trading-day IPO features.")
    parser.add_argument("--threshold", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = pd.read_parquet(RAW_DIR / "ipo_universe.parquet")
    daily = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    ipo_info, grey_market = load_external(RAW_DIR.parent / "external")
    features = build_daily_ipo_features(universe, daily, threshold=args.threshold, ipo_info=ipo_info, grey_market=grey_market)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    features.to_parquet(PROCESSED_DIR / "features.parquet", index=False)
    print(json.dumps({"rows": int(len(features)), "signals": int(features["baseline_signal"].sum())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
