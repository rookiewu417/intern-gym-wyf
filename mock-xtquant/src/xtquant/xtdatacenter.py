"""Minimal xtdatacenter module for import compatibility."""


_STATE = {
    "token": None,
    "allow_optmize_address": None,
    "data_home_dir": None,
    "initialized": False,
    "listening": False,
}


def set_token(*args, **kwargs):
    _STATE["token"] = args[0] if args else kwargs.get("token")
    return None


def set_allow_optmize_address(*args, **kwargs):
    _STATE["allow_optmize_address"] = args[0] if args else kwargs.get("addresses")
    return None


def set_data_home_dir(*args, **kwargs):
    _STATE["data_home_dir"] = args[0] if args else kwargs.get("data_home_dir")
    return None


def init(*args, **kwargs):
    _STATE["initialized"] = True
    return None


def listen(*args, **kwargs):
    _STATE["listening"] = True
    return None


def shutdown(*args, **kwargs):
    _STATE["listening"] = False
    return None
