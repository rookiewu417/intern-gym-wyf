PYTHON ?= python
SILVER_ROOT ?= sample-data-source
SYMBOLS ?= 02723.HK,02675.HK,00100.HK,02513.HK,06082.HK
PORT ?= 9021

.PHONY: install build-data smoke serve test

install:
	$(PYTHON) -m pip install -r requirements.txt

build-data:
	$(PYTHON) scripts/build_sample_data.py \
		--source-silver-root "$(SILVER_ROOT)" \
		--output-root sample-data \
		--symbols "$(SYMBOLS)"

smoke:
	PYTHONPATH=mock-xtquant/src XTMOCK_SILVER_ROOT=sample-data \
		$(PYTHON) examples/read_xtdata.py

serve:
	PYTHONPATH=mock-xtquant/src:mock-feed/src XTMOCK_SILVER_ROOT=sample-data \
		MARKET_SYMBOLS="$(SYMBOLS)" \
		$(PYTHON) -m market_mock_feed.server --host 0.0.0.0 --port $(PORT)

test:
	PYTHONPATH=mock-xtquant/src:mock-feed/src:backend-project/src XTMOCK_SILVER_ROOT=sample-data \
		$(PYTHON) -m pytest -q
