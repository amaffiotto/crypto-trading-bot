"""Tests for built-in strategies."""

import pandas as pd
import numpy as np
import pytest

from src.strategies.base import BaseStrategy, TradeSignal, Signal
from src.strategies.registry import StrategyRegistry, get_registry


class TestBaseStrategy:

    def test_always_buy_returns_valid_signals(self, always_buy_strategy, sample_ohlcv):
        df = always_buy_strategy.calculate_indicators(sample_ohlcv.copy())
        for i in range(always_buy_strategy.get_required_history(), len(df)):
            sig = always_buy_strategy.analyze(df, i)
            assert isinstance(sig, TradeSignal)
            assert sig.signal in (Signal.BUY, Signal.SELL, Signal.HOLD)

    def test_strategy_params_settable(self, always_buy_strategy):
        always_buy_strategy.set_params(buy_every=20)
        assert always_buy_strategy.params["buy_every"] == 20

    def test_validate_data(self, always_buy_strategy, sample_ohlcv):
        assert always_buy_strategy.validate_data(sample_ohlcv)


class TestStrategyRegistry:

    def test_load_builtin_strategies(self):
        registry = StrategyRegistry()
        count = registry.load_builtin()
        assert count > 0

    def test_list_strategies(self):
        registry = get_registry()
        strategies = registry.list_strategies()
        assert len(strategies) > 0
        assert all("name" in s for s in strategies)

    def test_get_instance(self):
        registry = get_registry()
        names = registry.get_names()
        assert len(names) > 0
        instance = registry.get_instance(names[0])
        assert isinstance(instance, BaseStrategy)

    def test_register_and_unregister(self):
        from tests.conftest import AlwaysBuyStrategy
        registry = StrategyRegistry()
        registry.register(AlwaysBuyStrategy)
        assert registry.get("Always Buy Test") is not None
        assert registry.unregister("Always Buy Test")
        assert registry.get("Always Buy Test") is None


class TestBuiltinStrategies:
    """Smoke-test each builtin strategy: indicators + analyze must not crash."""

    @pytest.fixture
    def registry(self):
        reg = get_registry()
        return reg

    def test_all_strategies_produce_signals(self, registry, sample_ohlcv):
        for name in registry.get_names():
            strategy = registry.get_instance(name)
            assert strategy is not None, f"Failed to instantiate {name}"
            df = strategy.calculate_indicators(sample_ohlcv.copy())
            required = strategy.get_required_history()
            sig = strategy.analyze(df, max(required, len(df) - 1))
            assert isinstance(sig, TradeSignal), f"{name} returned non-TradeSignal"

    def test_all_strategies_have_param_schema(self, registry):
        for name in registry.get_names():
            strategy = registry.get_instance(name)
            schema = strategy.get_param_schema()
            assert isinstance(schema, dict), f"{name} param_schema is not dict"

    def test_all_strategies_run_backtest(self, registry, sample_ohlcv):
        """Each builtin strategy should complete a backtest without errors."""
        from src.backtesting.engine import BacktestEngine
        engine = BacktestEngine(initial_capital=10000)
        for name in registry.get_names():
            strategy = registry.get_instance(name)
            result = engine.run(strategy, sample_ohlcv, symbol="TEST/USDT")
            assert result.initial_capital == 10000
