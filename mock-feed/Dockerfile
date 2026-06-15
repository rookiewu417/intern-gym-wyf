FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY mock-xtquant /app/mock-xtquant
COPY mock-feed /app/mock-feed
COPY sample-data /app/sample-data

ENV PYTHONPATH=/app/mock-xtquant/src:/app/mock-feed/src
ENV XTMOCK_SILVER_ROOT=/app/sample-data
EXPOSE 9021

CMD ["python", "-m", "market_mock_feed.server", "--host", "0.0.0.0", "--port", "9021"]

