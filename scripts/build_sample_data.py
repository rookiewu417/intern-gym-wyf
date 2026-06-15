from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DEFAULT_SYMBOLS = ("02723.HK", "02675.HK", "00100.HK", "02513.HK", "06082.HK")
PARQUET_FAMILIES = {
    "silver_minute_bars_v1",
    "silver_trade_ticks_v1",
    "silver_broker_queue_v1",
    "silver_ccass_holdings_v1",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a small internship sample-data package from a full silver root.")
    parser.add_argument("--source-silver-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    args = parser.parse_args()

    symbols = tuple(item.strip().upper() for item in args.symbols.split(",") if item.strip())
    if not symbols:
        raise SystemExit("--symbols must contain at least one symbol")

    source = args.source_silver_root.resolve()
    output = args.output_root.resolve()
    if not source.exists():
        raise SystemExit(f"source silver root does not exist: {source}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    tables: dict[str, dict[str, int | str]] = {}
    for family in (
        "silver_minute_bars_v1",
        "silver_trade_ticks_v1",
        "silver_broker_queue_v1",
        "silver_ccass_holdings_v1",
        "silver_daily_bars_v1",
        "silver_instruments_v1",
    ):
        frame = read_family(source, family)
        if "symbol" in frame.columns:
            frame = frame[frame["symbol"].astype(str).str.upper().isin(symbols)].copy()
        write_family(output, family, frame)
        tables[family] = {"rows": int(len(frame)), "format": "parquet" if family in PARQUET_FAMILIES else "csv"}

    mapping = read_family(source, "silver_broker_mapping_v1")
    mapping.to_csv(output / "silver_broker_mapping_v1.csv", index=False)
    tables["silver_broker_mapping_v1"] = {"rows": int(len(mapping)), "format": "csv"}

    manifest = {
        "package": "market-terminal-internship-lab",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_label": source.name,
        "symbols": list(symbols),
        "tables": tables,
        "notes": [
            "This package is intentionally small and safe for internship exercises.",
            "Do not use it for trading, production freshness checks, or financial decisions.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def read_family(root: Path, family: str) -> pd.DataFrame:
    parquet_dir = root / family
    csv_path = root / f"{family}.csv"
    if parquet_dir.exists() and any(parquet_dir.rglob("*.parquet")):
        return pd.read_parquet(parquet_dir)
    if csv_path.exists():
        return pd.read_csv(csv_path)
    raise FileNotFoundError(f"missing silver family: {family}")


def write_family(root: Path, family: str, frame: pd.DataFrame) -> None:
    if family in PARQUET_FAMILIES:
        table_dir = root / family
        table_dir.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(table_dir / "part-00000.parquet", index=False)
    else:
        frame.to_csv(root / f"{family}.csv", index=False)


if __name__ == "__main__":
    raise SystemExit(main())
