# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A recruiting / internship take-home **lab**, not a production system. It ships fixed mock infrastructure + sample data, and three independent candidate assignments. The point is to reproduce real bugs we hit (realtime refresh, broker-queue semantics, effective-day alignment, IPO daily research) inside a controlled sandbox.

Two kinds of directories:

- **Candidate-editable** (`frontend-project/`, `backend-project/`, `strategy-project/`) — assignment skeletons. A candidate forks and completes **one**.
  - `backend-project` skeleton is **intentionally incomplete** (`app.py` `hydrate()` is a placeholder proving the import path; the real state engine must be written).
  - `strategy-project` is a **runnable scaffold** (baseline backtest already works end-to-end).
- **Fixed scaffolding (do not change)** — `mock-xtquant/`, `mock-feed/`, `mock-research-api/`, `sample-data/`, `research-data/`, `scripts/`, `docs/`. Never wire in real xtquant/Redis/Kafka or production tokens.

Default symbol universe: `02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK`.

## Architecture (the parts that span multiple files)

**No installable packages.** Nothing is `pip install`-ed as a package; imports resolve purely via `PYTHONPATH` wiring set by the `Makefile` and `pytest.ini`. `from xtquant import xtdata` resolves to `mock-xtquant/src/xtquant/xtdata.py`, a thin shim that delegates every call to `xtmock.ReplayEngine`.

**Two independent data planes, two servers** — keep them straight:

| Plane | Data | Server | Consumer | Granularity |
|---|---|---|---|---|
| Realtime | `sample-data/` | `mock-feed` (WebSocket :9021) and `mock-xtquant` SDK | frontend + backend assignments | intraday (1m / ticks / broker queue) |
| Research | `research-data/` | `mock-research-api` (HTTP :9041) | strategy assignment | daily bars + cost model |

**How "realtime" is faked** — `xtmock/replay_engine.py` (`ReplayEngine`) is the heart of the SDK mock. On `subscribe_quote`, it spawns a **daemon thread** that walks parquet/silver rows for that symbol and fires the callback spaced by real event-time deltas (scaled by `XTMOCK_REPLAY_SPEED`, capped by `XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION`). `mock-feed/server.py` does the analogous thing over WebSocket with `asyncio` replay tasks, and is **fully implemented** (a working reference for the backend candidate).

**WebSocket contract** — protocol `terminal-message-v3`, `schema_version: 1`. Client commands: `snapshot_request | visible_set | watchlist_set | health_request`. Server frames: `hello | heartbeat | ack | snapshot | delta | error`. Snapshot payload carries `snapshot / minute_bars / alerts / broker_queue / freshness`, with monotonic `seq`. Full shape in `docs/api-contract.md` and `docs/frontend-backend-projects.md`.

## Sharp edges (verified by reading every file — easy to get wrong)

- **Two different daily datasets, different schemas — do not mix them.** `sample-data/silver_daily_bars_v1.csv` is OHLCV only (63 rows, the 5 realtime symbols) and exists solely to derive the big-trade `baseline_volume` for front/back. `research-data/daily_bars.parquet` is the strategy dataset (3,673 rows, 65 symbols) and additionally has `previous_close` + `suspend_flag`. Strategy code must read the research one.
- **`mock-xtquant` has dead code that does not run in this lab.** `xtmock/http_server.py` imports `xtmock_trader` (a package that isn't in the repo), and `ParquetStore`/`catalog.py` target recorded "run_id=…/dataset=…" parquet trees that aren't shipped. The only live data path is `SilverStore` reading `sample-data/`. Ignore the recording/http_server machinery — it's leftover from a fuller internal system.
- **Broker-queue sample data has `position` only (no `gear` column)**, and positions are raw, large, and sparse (e.g. 819, 820). `silver_store._broker_queue_levels` falls back `gear or position`. This is the concrete shape behind the "never renumber gears" rule.
- **`backend-project/tests/test_contracts.py` validates against the `mock-feed` reference implementation**, not the candidate skeleton — it's effectively the executable spec a candidate backend must match. `test_smoke.py` is the only test that exercises the (intentionally incomplete) skeleton.

## Business invariants (these are the graded traps — get them right in any change)

- **Broker queue is a full-snapshot overwrite, never an incremental accumulate.** `10/100/1000` only filters the raw `position`/`gear` range — never renumber/normalize gears. A gear's total volume = sum of its broker cells regardless of the 10/100/1000 toggle. Price gears can be sparse; don't assume contiguity.
- **Effective-day isolation.** On a trade-day switch, drop stale-day minute bars and alerts. A historical alert may enter the current snapshot only when `sourceDate == effectiveTradeDate`.
- **Alert dedup** by `id`; big-trade threshold defaults to `max(1, daily_baseline_volume * 0.0005)`.
- When the latest available broker queue predates the effective day, `mock-feed` emits a fallback snapshot flagged via `broker_queue.sourceDate/historical/fallback`. Sample data deliberately mixes source dates — that mismatch is a test point, not a bug.
- Strategy side: no look-ahead, always net of fees/slippage/min-fee, every trade in the trade log, external IPO/grey-market data must cite a source.

## Commands

Python 3.12/3.13, Node `>=20.19.0`. From repo root after `python -m venv .venv && source .venv/bin/activate`:

```bash
make install          # pip install -r requirements.txt
make smoke            # replay a short subscription; prints callback_count => mock data path OK
make serve            # realtime mock feed -> ws://127.0.0.1:9021/ws
make serve-research   # strategy HTTP API -> http://127.0.0.1:9041
make test             # full pytest suite (backend + research-api + strategy tests)
```

The `make` targets are the source of truth for required env (`XTMOCK_SILVER_ROOT=sample-data`, `RESEARCH_DATA_ROOT=research-data`, `MARKET_SYMBOLS`) and `PYTHONPATH`. Replicate them when running things by hand.

**Single test** — `pytest.ini` already sets `pythonpath`, but env vars still must be supplied:

```bash
XTMOCK_SILVER_ROOT=sample-data RESEARCH_DATA_ROOT=research-data \
  python -m pytest backend-project/tests/test_contracts.py::test_name -q
```

**Frontend** (`frontend-project/`): `npm install`, `npm run dev` (Vite on :5176), `npm run build` (runs `vue-tsc --noEmit`), `npm run test` (Vitest).

**Backend skeleton** run (listens on :9031, distinct from the mock feed's :9021):

```bash
cd backend-project && PYTHONPATH=../mock-xtquant/src:src XTMOCK_SILVER_ROOT=../sample-data \
  python -m market_state_engine.app
```

**Strategy scaffold** (needs `make serve-research` running, or use `--source-root ../research-data` to skip the HTTP API):

```bash
cd strategy-project
python src/download_data.py --base-url http://127.0.0.1:9041 --start 2026-01-01
python src/build_features.py
python src/backtest.py        # outputs to data/processed/ and reports/
```

`make build-data SILVER_ROOT=/path/to/full/silver-root` regenerates `sample-data/` (maintainer-only).

## Ports

`9021` mock feed · `9031` backend skeleton · `9041` research API · `5176` frontend dev.

## Docs map

`docs/frontend-backend-projects.md` (shared semantics + WS contract + rubric), `docs/strategy-project.md`, `docs/api-contract.md`, `docs/data-contract.md`, `docs/grading-rubric.md`, `TROUBLESHOOTING.md` (per-component smoke recipes).
