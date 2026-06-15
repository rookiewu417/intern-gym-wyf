from __future__ import annotations

import json
from functools import lru_cache
from typing import Iterable

import pandas as pd
import pyarrow.dataset as ds

from .catalog import RecordingCatalog


class ParquetStore:
    def __init__(self, catalog: RecordingCatalog):
        self.catalog = catalog

    @lru_cache(maxsize=32)
    def dataframe(self, dataset: str) -> pd.DataFrame:
        path = self.catalog.dataset_path(dataset)
        table = ds.dataset(str(path), format="parquet", partitioning="hive").to_table()
        df = table.to_pandas()
        if "event_time" in df.columns:
            df = df.sort_values(["symbol", "event_time", "sequence"], kind="mergesort")
        return df.reset_index(drop=True)

    def symbols(self, dataset: str) -> list[str]:
        df = self.dataframe(dataset)
        if "symbol" not in df.columns:
            return []
        return sorted(str(x) for x in df["symbol"].dropna().unique())

    def payload_records(self, dataset: str, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        df = self.dataframe(dataset)
        if symbols is not None:
            wanted = {str(s) for s in symbols}
            df = df[df["symbol"].astype(str).isin(wanted)]
        if df.empty:
            return pd.DataFrame(columns=["symbol", "event_time", "recorded_at", "payload"])

        records = df[["symbol", "event_time", "recorded_at", "payload_json"]].copy()
        records["payload"] = records["payload_json"].map(json.loads)
        return records.drop(columns=["payload_json"]).reset_index(drop=True)

