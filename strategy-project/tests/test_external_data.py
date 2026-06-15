from external_data import load_external, IPO_COLS, GREY_COLS


def test_load_external_missing_files_returns_empty_with_schema(tmp_path):
    ipo, grey = load_external(tmp_path)
    assert list(ipo.columns) == list(IPO_COLS)
    assert list(grey.columns) == list(GREY_COLS)
    assert ipo.empty and grey.empty
