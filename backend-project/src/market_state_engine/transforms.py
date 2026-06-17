from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd

from .models import now_iso

HK_TZ = timezone(timedelta(hours=8))


# ============ 候选专属纯函数 ============
def ms_to_hk_iso(value: Any) -> str:
    """epoch 时间戳 → Asia/Shanghai(+08:00) ISO，匹配参考实现的 bar_ts 形态。
    ⚠️ 按量级兼容秒/毫秒：本 lab 下 silver_store._timestamp_ms 在 pandas 3.0(datetime64[us]) 时
    实际产出 epoch 秒(10 位，如 1780992600)，pandas 2.2 时是毫秒(13 位)。1e12 边界干净区分
    （2026 秒≈1.78e9 < 1e12 ≤ 2026 毫秒≈1.78e12），故对 pandas 版本无关。"""
    v = int(value)
    seconds = v / 1000 if v >= 1_000_000_000_000 else v
    return datetime.fromtimestamp(seconds, tz=HK_TZ).isoformat(timespec="milliseconds")


def flatten_broker_levels(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把 SDK hkbrokerqueueex 的嵌套 level dict 还原成 broker_queue_from_rows 需要的扁平行。
    关键不变量：position 直接取 SDK 已派生的 gear（绝不重编号 0..N）；queue_ts 写到每一行（否则 sourceDate 丢失）。
    防御：缺失/空 side、volumes 短于 brokers、price/position 类型。"""
    rows: list[dict[str, Any]] = []
    qts = payload.get("queue_ts") or payload.get("timestamp") or ""
    for side in ("ask", "bid"):
        levels = payload.get(f"{side}brokerqueues") or payload.get(f"{side}Queues") or []
        for level in levels:
            try:
                pos = int(level.get("gear") or level.get("position") or 0)
                price = float(level.get("price") or 0.0)
            except (TypeError, ValueError):
                continue
            brokers = level.get("brokers") or []
            volumes = level.get("volumes") or []
            for i, code in enumerate(brokers):
                try:
                    vol = int(volumes[i]) if i < len(volumes) else 0
                except (TypeError, ValueError):
                    vol = 0
                rows.append({"side": side, "position": pos, "gear": pos, "price": price,
                             "broker_code": str(code), "volume": vol, "queue_ts": qts})
    return rows


def upsert_bar_changed(bars: list[dict[str, Any]], bar: dict[str, Any]) -> bool:
    """upsert_bar 的带「是否变更」返回值版本，用于 live 路径抑制回放 wraparound 的 no-op delta。"""
    for index, item in enumerate(bars):
        if item.get("timestamp") == bar["timestamp"]:
            if item == bar:
                return False
            bars[index] = bar
            return True
    bars.append(bar)
    bars.sort(key=lambda item: str(item.get("timestamp") or ""))
    del bars[:-420]
    return True


def latest_daily_volume(frame: pd.DataFrame) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in frame.sort_values("trade_date").to_dict("records"):
        symbol = str(row.get("symbol") or "").upper()
        try:
            volume = int(float(row.get("volume") or 0))
        except ValueError:
            volume = 0
        if symbol and volume > 0:
            result[symbol] = volume
    return result


# ============ 以下逐字复制自 mock-feed/src/market_mock_feed/server.py（保持逐字节同输出；
# 唯一例外：iso_from_any 的 digit 分支做了量级防御，对真实输入仍与参考逐字节一致） ============
def iso_from_any(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    text = str(value)
    if text and text != "nan":
        if text.isdigit():
            # 防御性：按量级兼容秒/毫秒（happy path 不会走到这里——adapter 已注入 bar_ts；
            # 仅在某条 1m 路径漏注入时兜底，避免把秒当毫秒回到 1970）。真·毫秒输入与参考逐字节一致。
            v = int(text)
            secs = v / 1000 if v >= 1_000_000_000_000 else v
            return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat(timespec="milliseconds")
        return text
    return ""


def trade_date_from_timestamp(value: Any) -> str:
    text = iso_from_any(value)
    return text[:10].replace("-", "") if len(text) >= 10 else ""


def compact_name(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("证券有限公司", "證券有限公司", "证券国际(香港)有限公司", "證券國際(香港)有限公司", "有限公司", "证券", "證券"):
        text = text.replace(suffix, "")
    return text[:8] or "未披露"


def minute_bar(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_from_any(row.get("bar_ts") or row.get("timestamp") or row.get("time"))
    close = float(row.get("close") or row.get("price") or 0.0)
    return {
        "timestamp": timestamp,
        "price": close,
        "open": float(row.get("open") or close),
        "high": float(row.get("high") or close),
        "low": float(row.get("low") or close),
        "close": close,
        "volume": int(float(row.get("volume") or 0)),
        "turnover": float(row.get("turnover") or row.get("amount") or 0.0),
    }


def trade_tick(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_from_any(row.get("tick_ts") or row.get("timestamp") or row.get("time"))
    return {
        "id": str(row.get("trade_id") or row.get("tradeID") or row.get("seq") or row.get("row_hash") or timestamp),
        "timestamp": timestamp,
        "tradeDate": trade_date_from_timestamp(timestamp),
        "price": float(row.get("price") or 0.0),
        "volume": int(float(row.get("volume") or row.get("qty") or 0)),
        "turnover": float(row.get("turnover") or row.get("amount") or 0.0),
        "side": str(row.get("side") or "neutral").lower(),
        "brokerCode": str(row.get("active_broker_code") or row.get("broker_code") or row.get("brokerNo") or ""),
    }


def queue_source_date(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        trade_date = trade_date_from_timestamp(row.get("queue_ts"))
        if trade_date:
            return trade_date
    return ""


def broker_queue_from_rows(rows: list[dict[str, Any]], brokers: dict[str, str], *, effective_day: str = "") -> dict[str, Any]:
    source_date = queue_source_date(rows)
    result: dict[str, Any] = {
        "ask": [],
        "bid": [],
        "sourceDate": source_date,
        "historical": bool(source_date and effective_day and source_date != effective_day),
        "fallback": bool(source_date and effective_day and source_date != effective_day),
    }
    if not rows:
        return result
    frame = pd.DataFrame(rows)
    for (side, price), group in frame.groupby(["side", "price"], sort=True):
        side_text = str(side).lower()
        position = int(float(group["position"].dropna().astype(float).min())) if "position" in group.columns and not group.empty else len(result.get(side_text, [])) + 1
        cells = []
        for row in group.to_dict("records"):
            code = str(row.get("broker_code") or "0")
            volume = int(float(row.get("volume") or 0))
            cells.append({"brokerCode": code, "displayName": brokers.get(code, code if code != "0" else "未披露"), "volume": volume})
        entry = {
            "id": f"{side_text}-{int(position)}-{float(price)}",
            "side": side_text,
            "position": int(position),
            "gear": int(position),
            "price": float(price),
            "volume": sum(item["volume"] for item in cells),
            "brokerCount": len(cells),
            "brokers": cells,
        }
        if side_text in result:
            result[side_text].append(entry)
    for side in ("ask", "bid"):
        result[side].sort(key=lambda item: int(item["position"]))
    return result


def filter_current_day(rows: list[dict[str, Any]], effective_day: str) -> list[dict[str, Any]]:
    if not effective_day:
        return rows
    filtered = []
    for row in rows:
        timestamp = row.get("timestamp") or row.get("updatedAt") or row.get("bar_ts") or row.get("tick_ts")
        if trade_date_from_timestamp(timestamp) == effective_day or row.get("tradeDate") == effective_day:
            filtered.append(row)
    return filtered


def update_quote_from_bar(state, bar: dict[str, Any]) -> None:
    quote = state.payload["snapshot"]
    quote.update(
        {
            "price": bar["close"],
            "open": bar["open"],
            "high": max(float(quote.get("high") or 0.0), bar["high"]),
            "low": bar["low"] if not quote.get("low") else min(float(quote["low"]), bar["low"]),
            "volume": sum(int(item.get("volume") or 0) for item in state.payload["minute_bars"]),
            "turnover": sum(float(item.get("turnover") or 0.0) for item in state.payload["minute_bars"]),
            "updatedAt": bar["timestamp"],
            "tradeDate": trade_date_from_timestamp(bar["timestamp"]),
        }
    )
    touch_freshness(state, bar["timestamp"], "minute_bars")


def update_quote_from_tick(state, tick: dict[str, Any]) -> None:
    quote = state.payload["snapshot"]
    quote["price"] = tick["price"]
    quote["updatedAt"] = tick["timestamp"]
    quote["tradeDate"] = tick["tradeDate"]


def upsert_bar(bars: list[dict[str, Any]], bar: dict[str, Any]) -> None:
    for index, item in enumerate(bars):
        if item.get("timestamp") == bar["timestamp"]:
            bars[index] = bar
            return
    bars.append(bar)
    bars.sort(key=lambda item: str(item.get("timestamp") or ""))
    del bars[:-420]


def big_trade_alert(state, tick: dict[str, Any]) -> dict[str, Any] | None:
    threshold = max(1, int(state.baseline_volume * 0.0005)) if state.baseline_volume > 0 else 1000
    if tick["volume"] < threshold:
        return None
    return {
        "id": f"big-{state.symbol}-{tick['id']}",
        "timestamp": tick["timestamp"],
        "tradeDate": tick["tradeDate"],
        "sourceDate": tick["tradeDate"],
        "historical": False,
        "source": "mock_hktransaction",
        "price": tick["price"],
        "volume": tick["volume"],
        "turnover": tick["turnover"],
        "side": tick["side"],
        "brokerCode": tick["brokerCode"],
        "thresholdVolume": threshold,
        "thresholdRatio": 0.0005,
        "baselineVolume": state.baseline_volume,
    }


def merge_alert(alerts: list[dict[str, Any]], alert: dict[str, Any]) -> None:
    if any(item.get("id") == alert.get("id") for item in alerts):
        return
    alerts.insert(0, alert)
    del alerts[100:]


def touch_freshness(state, timestamp: Any, key: str) -> None:
    state.payload["freshness"]["runtime_state"] = "LIVE"
    state.payload["freshness"].setdefault("source_dates", {})[key] = iso_from_any(timestamp) or str(timestamp or now_iso())


def empty_snapshot(symbol: str, name: str, effective_day: str = "") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "snapshot": {"symbol": symbol, "name": name, "currency": "HKD", "price": 0.0, "updatedAt": "", "tradeDate": effective_day},
        "minute_bars": [],
        "alerts": [],
        "broker_queue": {"ask": [], "bid": [], "sourceDate": "", "historical": False, "fallback": False},
        "freshness": {"runtime_state": "WARM", "effective_day": effective_day, "source_dates": {}},
    }
