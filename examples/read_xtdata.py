from __future__ import annotations

import os
import time

from xtquant import xtdata


SYMBOLS = ["02723.HK", "02675.HK"]


def main() -> int:
    print("xtdata:", xtdata.__file__)
    print("XTMOCK_SILVER_ROOT:", os.getenv("XTMOCK_SILVER_ROOT"))
    for period in ("1m", "hktransaction", "hkbrokerqueueex"):
        data = xtdata.get_market_data_ex([], SYMBOLS, period=period, count=2)
        print(period, {symbol: len(frame) for symbol, frame in data.items()})

    callbacks = []

    def callback(payload):
        callbacks.append(payload)
        print("callback", len(callbacks), list(payload.keys()))

    seqs = [xtdata.subscribe_quote("02723.HK", period=period, callback=callback) for period in ("1m", "hktransaction", "hkbrokerqueueex")]
    time.sleep(2)
    for seq in seqs:
        xtdata.unsubscribe_quote(seq)
    print("callback_count", len(callbacks))
    return 0 if callbacks else 1


if __name__ == "__main__":
    raise SystemExit(main())

