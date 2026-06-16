from __future__ import annotations

from pathlib import Path

import pandas as pd

IPO_COLS = (
    "symbol", "listing_date", "ipo_price", "offer_price_low", "offer_price_high",
    "sponsor", "industry", "public_subscription_multiple", "one_lot_success_rate",
    "source_url", "source_note", "collected_at",
)
GREY_COLS = (
    "symbol", "grey_market_date", "grey_close", "grey_change_pct",
    "premium_to_ipo_price", "source_url", "source_note", "collected_at",
)
_NUMERIC = {
    "ipo_price", "offer_price_low", "offer_price_high",
    "public_subscription_multiple", "one_lot_success_rate",
    "grey_close", "grey_change_pct", "premium_to_ipo_price",
}


def _read(path: Path, cols: tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(cols))
    df = pd.read_csv(path, dtype=str)
    for col in cols:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[list(cols)].copy()
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    for col in cols:
        if col in _NUMERIC:
            df[col] = pd.to_numeric(df[col], errors="coerce")  # 缺失 -> NaN，绝不填 0
    return df[df["symbol"].notna() & (df["symbol"] != "") & (df["symbol"] != "NAN")].reset_index(drop=True)


def load_external(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(root)
    return _read(root / "ipo_info.csv", IPO_COLS), _read(root / "grey_market.csv", GREY_COLS)
