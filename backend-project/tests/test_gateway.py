import asyncio
import json

from market_state_engine.gateway.ws import Gateway


class FakeWS:
    def __init__(self, incoming=None):
        self.sent = []
        self._incoming = list(incoming or [])
    async def send(self, raw):
        self.sent.append(json.loads(raw))
    def __aiter__(self):
        self._it = iter(self._incoming)
        return self
    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeEngine:
    def __init__(self):
        self.snapshots = {"02723.HK": object()}
    def snapshot_frame(self, symbol):
        if symbol not in self.snapshots:
            return None
        return {"type": "snapshot", "symbol": symbol, "seq": 1, "payload": {"symbol": symbol}}
    def resume_since(self, symbol, last_seq):
        return ("deltas", [{"type": "delta", "symbol": symbol, "seq": last_seq + 1}])


def types(ws):
    return [m["type"] for m in ws.sent]


def run(coro):
    return asyncio.run(coro)


def test_hello_then_heartbeat_then_ack_snapshot():
    ws = FakeWS([json.dumps({"command": "snapshot_request", "request_id": "r1", "symbols": ["02723.HK"]})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "snapshot"]
    assert ws.sent[2]["payload"] == {"command": "snapshot_request", "accepted": True}
    assert ws.sent[3]["symbol"] == "02723.HK"


def test_health_request_returns_heartbeat():
    ws = FakeWS([json.dumps({"command": "health_request", "request_id": "h1"})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "heartbeat"]
    assert ws.sent[-1]["request_id"] == "h1" and ws.sent[-1]["payload"] == {"ready": True}


def test_bad_json_returns_error():
    ws = FakeWS(["{not json"])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "error"]
    assert ws.sent[-1]["payload"]["code"] == "bad_json"


def test_unknown_command_returns_error():
    ws = FakeWS([json.dumps({"command": "frobnicate", "request_id": "x"})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "error"]
    assert ws.sent[-1]["payload"]["code"] == "unknown_command"
    assert ws.sent[-1]["request_id"] == "x"   # request_id 必须在顶层信封，与 ack/heartbeat 一致


def test_resume_request_streams_deltas():
    ws = FakeWS([json.dumps({"command": "resume_request", "request_id": "r", "symbols": ["02723.HK"], "cursors": {"02723.HK": 5}})])
    gw = Gateway(FakeEngine(), bridge=None)
    run(gw.handle_client(ws))
    assert types(ws) == ["hello", "heartbeat", "ack", "delta"]
    assert ws.sent[-1]["seq"] == 6
