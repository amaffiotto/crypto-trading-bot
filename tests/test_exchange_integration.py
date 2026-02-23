"""Integration tests that talk to exchange sandboxes.

These tests require network access and valid sandbox API keys.
Run with: pytest -m integration

Environment variables:
    TEST_EXCHANGE_API_KEY   - sandbox API key
    TEST_EXCHANGE_API_SECRET - sandbox API secret
    TEST_EXCHANGE_ID        - exchange id (default: binance)
"""

import os

import pytest

from src.core.exchange import ExchangeManager

EXCHANGE_ID = os.environ.get("TEST_EXCHANGE_ID", "binance")
API_KEY = os.environ.get("TEST_EXCHANGE_API_KEY", "")
API_SECRET = os.environ.get("TEST_EXCHANGE_API_SECRET", "")

needs_sandbox = pytest.mark.skipif(
    not API_KEY or not API_SECRET,
    reason="Set TEST_EXCHANGE_API_KEY and TEST_EXCHANGE_API_SECRET to run",
)


@pytest.mark.integration
class TestExchangeIntegration:
    """Tests that require a live sandbox connection."""

    @pytest.fixture(autouse=True)
    def manager(self):
        self.mgr = ExchangeManager()

    @needs_sandbox
    def test_connect_sandbox(self):
        ex = self.mgr.connect(EXCHANGE_ID, API_KEY, API_SECRET, sandbox=True)
        assert ex is not None

    @needs_sandbox
    def test_fetch_ohlcv(self):
        self.mgr.connect(EXCHANGE_ID, API_KEY, API_SECRET, sandbox=True)
        candles = self.mgr.fetch_ohlcv(EXCHANGE_ID, "BTC/USDT", "1h", limit=10)
        assert len(candles) > 0
        assert len(candles[0]) == 6  # timestamp, o, h, l, c, v

    @needs_sandbox
    def test_fetch_ticker(self):
        self.mgr.connect(EXCHANGE_ID, API_KEY, API_SECRET, sandbox=True)
        ticker = self.mgr.fetch_ticker(EXCHANGE_ID, "BTC/USDT")
        assert "last" in ticker or "close" in ticker

    @needs_sandbox
    def test_fetch_balance(self):
        self.mgr.connect(EXCHANGE_ID, API_KEY, API_SECRET, sandbox=True)
        balance = self.mgr.fetch_balance(EXCHANGE_ID)
        assert isinstance(balance, dict)


@pytest.mark.integration
class TestExchangeManagerUnit:
    """Unit-level tests for ExchangeManager that don't need credentials."""

    def test_supported_exchanges_list(self):
        supported = ExchangeManager.get_supported_exchanges()
        assert "binance" in supported
        assert len(supported) > 5

    def test_all_exchanges_list(self):
        all_ex = ExchangeManager.get_all_exchanges()
        assert len(all_ex) > 50

    def test_timeframes(self):
        mgr = ExchangeManager()
        assert "1h" in mgr.TIMEFRAMES
        assert "1d" in mgr.TIMEFRAMES

    def test_connect_public_only(self):
        mgr = ExchangeManager()
        ex = mgr.connect("binance")
        assert ex is not None
