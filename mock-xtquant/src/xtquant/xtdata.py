from __future__ import annotations

from xtmock.replay_engine import ReplayEngine


_engine: ReplayEngine | None = None
enable_hello = False


def _get_engine() -> ReplayEngine:
    global _engine
    if _engine is None:
        _engine = ReplayEngine()
    return _engine


def connect(ip="", port=None, remember_if_success=True):
    del ip, port, remember_if_success
    global _engine
    _engine = ReplayEngine()
    return None


def reconnect(ip="", port=None, remember_if_success=True):
    return connect(ip, port, remember_if_success)


def run():
    import time

    while True:
        time.sleep(1)


def subscribe_quote(stock_code, period="1d", start_time="", end_time="", count=0, callback=None):
    del start_time, end_time, count
    return _get_engine().subscribe_quote(stock_code, period=period, callback=callback)


def subscribe_quote2(stock_code, period="1d", start_time="", end_time="", count=0, dividend_type=None, callback=None):
    del dividend_type
    return subscribe_quote(stock_code, period, start_time, end_time, count, callback)


def unsubscribe_quote(seq):
    return _get_engine().unsubscribe_quote(seq)


def subscribe_l2thousand(stock_code, gear_num=None, callback=None):
    return _get_engine().subscribe_l2thousand(stock_code, gear_num=gear_num, callback=callback)


def get_full_tick(code_list):
    return _get_engine().get_full_tick(list(code_list))


def get_market_data_ex(
    field_list=[],
    stock_list=[],
    period="1d",
    start_time="",
    end_time="",
    count=-1,
    dividend_type="none",
    fill_data=True,
):
    return _get_engine().get_market_data_ex(
        field_list,
        stock_list,
        period,
        start_time=start_time,
        end_time=end_time,
        count=count,
        dividend_type=dividend_type,
        fill_data=fill_data,
    )


def get_market_data(
    field_list=[],
    stock_list=[],
    period="1d",
    start_time="",
    end_time="",
    count=-1,
    dividend_type="none",
    fill_data=True,
):
    return _get_engine().get_market_data(
        field_list,
        stock_list,
        period,
        start_time=start_time,
        end_time=end_time,
        count=count,
        dividend_type=dividend_type,
        fill_data=fill_data,
    )


def download_history_data(stock_code, period, start_time="", end_time="", incrementally=None):
    return _get_engine().download_history_data(stock_code, period, start_time, end_time, incrementally=incrementally)


def download_history_data2(stock_list, period, start_time="", end_time="", callback=None, incrementally=None):
    return _get_engine().download_history_data2(
        stock_list, period, start_time, end_time, callback=callback, incrementally=incrementally
    )


def get_instrument_detail(stock_code, iscomplete=False):
    return _get_engine().get_instrument_detail(stock_code, iscomplete=iscomplete)


def get_instrument_detail_list(stock_list, iscomplete=False):
    return _get_engine().get_instrument_detail_list(stock_list, iscomplete=iscomplete)


def get_trading_dates(market, start_time="", end_time="", count=-1):
    return _get_engine().get_trading_dates(market, start_time=start_time, end_time=end_time, count=count)
