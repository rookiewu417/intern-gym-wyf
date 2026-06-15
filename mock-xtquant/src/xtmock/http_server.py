from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from xtmock.catalog import RecordingCatalog
from xtmock.config import load_config
from xtmock.parquet_store import ParquetStore
from xtmock_trader.depth_provider import create_depth_provider


class MarketDataHttpServer:
    def __init__(self):
        self.depth_provider = create_depth_provider()
        self.catalog = RecordingCatalog.discover(load_config())
        self.store = ParquetStore(self.catalog)

    def depth_response(self, symbol: str, levels: int, market: str) -> dict:
        levels = max(1, min(int(levels or 10), 10))
        lot_size = self._lot_size(symbol)
        depth = self.depth_provider.depth(market, symbol, advance=True)
        asks = [
            _level_payload(index, level.price, level.volume, lot_size)
            for index, level in enumerate(depth.asks[:levels], 1)
        ]
        bids = [
            _level_payload(index, level.price, level.volume, lot_size)
            for index, level in enumerate(depth.bids[:levels], 1)
        ]
        return {
            "symbol": symbol,
            "market": market,
            "last_price": depth.last_price,
            "open_price": depth.last_price,
            "previous_close": depth.last_price,
            "levels": levels,
            "asks": asks,
            "bids": bids,
            "cancelled_buy_lots": 0,
            "cancelled_sell_lots": 0,
            "updated_at": int(time.time() * 1000),
            "source": "xtmock",
            "channel": "l2quote",
            "ask_price": [item["price"] for item in asks],
            "ask_volume": [item["lots"] for item in asks],
            "bid_price": [item["price"] for item in bids],
            "bid_volume": [item["lots"] for item in bids],
        }

    def trading_rules_response(self, symbol: str, market: str) -> dict:
        detail = self._instrument_detail(symbol)
        price_tick = float(detail.get("PriceTick") or 0.001)
        lot_size = int(float(detail.get("VolumeMultiple") or 100))
        return {
            "symbol": symbol,
            "market": market or detail.get("ExchangeID") or "HK",
            "name": detail.get("InstrumentName", ""),
            "price_tick": price_tick,
            "tick_size": price_tick,
            "lot_size": lot_size,
            "board_lot": lot_size,
            "min_lots": 1,
            "min_order_lots": 1,
            "min_order_quantity": lot_size,
            "max_order_quantity": int(detail.get("MaxLimitOrderVolume") or 2_147_483_647),
            "currency": detail.get("Ccy") or "HKD",
            "is_trading": bool(detail.get("IsTrading", True)),
            "source": "xtmock",
        }

    def _instrument_detail(self, symbol: str) -> dict:
        records = self.store.payload_records("instrument_detail_raw", [symbol])
        if records.empty and "." in symbol:
            instrument, market = symbol.split(".", 1)
            records = self.store.payload_records("instrument_detail_raw", [f"{instrument}.{market}"])
        if records.empty:
            return {}
        return dict(records.iloc[-1]["payload"])

    def _lot_size(self, symbol: str) -> int:
        detail = self._instrument_detail(symbol)
        return int(float(detail.get("VolumeMultiple") or 100))


def make_handler(app: MarketDataHttpServer):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 3 and parts[0] == "quotes" and parts[2] == "depth":
                params = parse_qs(parsed.query)
                levels = int(params.get("levels", ["10"])[0])
                market = params.get("market", ["HK"])[0]
                self._json(200, app.depth_response(parts[1], levels, market))
                return
            if len(parts) == 3 and parts[0] == "instruments" and parts[2] == "trading-rules":
                params = parse_qs(parsed.query)
                market = params.get("market", ["HK"])[0]
                self._json(200, app.trading_rules_response(parts[1], market))
                return
            if parsed.path == "/health":
                self._json(200, {"ok": True})
                return
            self._json(404, {"error": "not_found"})

        def log_message(self, fmt, *args):
            return

        def _json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 18080):
    app = MarketDataHttpServer()
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"xtmock market-data HTTP listening on http://{host}:{port}")
    server.serve_forever()


def _level_payload(level: int, price: float, volume: int, lot_size: int) -> dict:
    lots = int(volume // lot_size) if lot_size > 0 else int(volume)
    return {"level": level, "price": price, "lots": lots, "volume": volume}
