"""Shared test fixtures for the trading bot test suite."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.backtesting.engine import BacktestEngine, BacktestResult, Trade
from src.backtesting.metrics import MetricsCalculator
from src.strategies.base import BaseStrategy, TradeSignal, Signal


# ---------------------------------------------------------------------------
# Synthetic OHLCV data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_ohlcv():
    """Generate 500 rows of synthetic OHLCV with realistic price action."""
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 10.0)
    high = close * (1 + np.abs(np.random.randn(n) * 0.005) + 0.001)
    low = close * (1 - np.abs(np.random.randn(n) * 0.005) - 0.001)
    open_ = low + np.random.rand(n) * (high - low)
    volume = np.random.randint(100, 10000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def large_ohlcv():
    """2000-row dataset for walk-forward / OOS tests."""
    np.random.seed(123)
    n = 2000
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    close = 50000.0 + np.cumsum(np.random.randn(n) * 50)
    close = np.maximum(close, 1000.0)
    high = close * (1 + np.abs(np.random.randn(n) * 0.003) + 0.001)
    low = close * (1 - np.abs(np.random.randn(n) * 0.003) - 0.001)
    open_ = low + np.random.rand(n) * (high - low)
    volume = np.random.randint(500, 50000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def trending_up_ohlcv():
    """300-row upward-trending dataset for strategy tests."""
    np.random.seed(7)
    n = 300
    dates = pd.date_range("2024-06-01", periods=n, freq="1h")
    trend = np.linspace(0, 30, n)
    noise = np.cumsum(np.random.randn(n) * 0.2)
    close = 100.0 + trend + noise
    close = np.maximum(close, 10.0)
    high = close * 1.005
    low = close * 0.995
    open_ = close * (1 + np.random.randn(n) * 0.001)
    volume = np.random.randint(200, 8000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ---------------------------------------------------------------------------
# Engine / calculator fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """Standard BacktestEngine."""
    return BacktestEngine(
        initial_capital=10000.0,
        fee_percent=0.1,
        slippage_percent=0.05,
    )


@pytest.fixture
def metrics_calculator():
    return MetricsCalculator(risk_free_rate=0.0)


# ---------------------------------------------------------------------------
# Deterministic test strategy
# ---------------------------------------------------------------------------

class AlwaysBuyStrategy(BaseStrategy):
    """Buys every N bars, sells after M bars. Deterministic for testing."""

    name = "Always Buy Test"
    description = "Test strategy that buys/sells on fixed intervals"
    version = "0.0.1"

    def default_params(self) -> Dict[str, Any]:
        return {"buy_every": 10, "hold_bars": 5}

    def get_required_history(self) -> int:
        return 1

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        buy_every = self._params["buy_every"]
        hold_bars = self._params["hold_bars"]
        if index % buy_every == 0:
            return TradeSignal(signal=Signal.BUY, strength=1.0)
        if index % buy_every == hold_bars:
            return TradeSignal(signal=Signal.SELL, strength=1.0)
        return TradeSignal(signal=Signal.HOLD)


class NeverTradeStrategy(BaseStrategy):
    """Always returns HOLD."""

    name = "Never Trade"
    description = "Test strategy that never trades"
    version = "0.0.1"

    def default_params(self):
        return {}

    def get_required_history(self):
        return 1

    def calculate_indicators(self, df):
        return df

    def analyze(self, df, index):
        return TradeSignal(signal=Signal.HOLD)


@pytest.fixture
def always_buy_strategy():
    return AlwaysBuyStrategy()


@pytest.fixture
def never_trade_strategy():
    return NeverTradeStrategy()


# ---------------------------------------------------------------------------
# Sample trades for metric testing
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_trades():
    """Pre-built list of trades with known outcomes."""
    base = datetime(2024, 1, 1)
    return [
        Trade(entry_time=base, exit_time=base + timedelta(hours=5),
              side="long", entry_price=100, exit_price=110,
              quantity=1.0, pnl=10.0, pnl_percent=10.0, fee=0.2),
        Trade(entry_time=base + timedelta(hours=10), exit_time=base + timedelta(hours=15),
              side="long", entry_price=110, exit_price=105,
              quantity=1.0, pnl=-5.0, pnl_percent=-4.55, fee=0.2),
        Trade(entry_time=base + timedelta(hours=20), exit_time=base + timedelta(hours=30),
              side="long", entry_price=105, exit_price=115,
              quantity=1.0, pnl=10.0, pnl_percent=9.52, fee=0.2),
        Trade(entry_time=base + timedelta(hours=35), exit_time=base + timedelta(hours=40),
              side="long", entry_price=115, exit_price=108,
              quantity=1.0, pnl=-7.0, pnl_percent=-6.09, fee=0.2),
    ]


@pytest.fixture
def sample_backtest_result(sample_trades, sample_ohlcv):
    """BacktestResult built from sample_trades."""
    eq_data = []
    equity = 10000.0
    for i, row in sample_ohlcv.iterrows():
        equity += np.random.randn() * 5
        eq_data.append({"timestamp": row["timestamp"], "equity": max(equity, 9000)})
    return BacktestResult(
        strategy_name="Test Strategy",
        symbol="BTC/USDT",
        timeframe="1h",
        start_date=sample_ohlcv["timestamp"].iloc[0],
        end_date=sample_ohlcv["timestamp"].iloc[-1],
        initial_capital=10000.0,
        final_capital=10008.0,
        trades=sample_trades,
        equity_curve=pd.DataFrame(eq_data),
        parameters={"fast": 9, "slow": 21},
    )


# ---------------------------------------------------------------------------
# Config fixture with temp file
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_config(tmp_path):
    """ConfigManager backed by a temp YAML file."""
    from src.core.config import ConfigManager
    cfg_path = tmp_path / "config.yaml"
    cfg = ConfigManager(config_path=str(cfg_path))
    return cfg
