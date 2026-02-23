"""Tests for the BacktestEngine."""

import pandas as pd
import numpy as np
import pytest

from src.backtesting.engine import BacktestEngine, BacktestResult, Trade, Position
from src.strategies.base import BaseStrategy, TradeSignal, Signal


class TestBacktestEngine:

    def test_run_returns_backtest_result(self, engine, always_buy_strategy, sample_ohlcv):
        result = engine.run(always_buy_strategy, sample_ohlcv, symbol="BTC/USDT")
        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Always Buy Test"
        assert result.symbol == "BTC/USDT"

    def test_run_produces_trades(self, engine, always_buy_strategy, sample_ohlcv):
        result = engine.run(always_buy_strategy, sample_ohlcv)
        assert result.num_trades > 0

    def test_no_trades_with_hold_strategy(self, engine, never_trade_strategy, sample_ohlcv):
        result = engine.run(never_trade_strategy, sample_ohlcv)
        assert result.num_trades == 0
        assert result.final_capital == result.initial_capital

    def test_equity_curve_not_empty(self, engine, always_buy_strategy, sample_ohlcv):
        result = engine.run(always_buy_strategy, sample_ohlcv)
        assert not result.equity_curve.empty
        assert "equity" in result.equity_curve.columns
        assert "timestamp" in result.equity_curve.columns

    def test_initial_capital_preserved(self, engine, always_buy_strategy, sample_ohlcv):
        result = engine.run(always_buy_strategy, sample_ohlcv)
        assert result.initial_capital == 10000.0

    def test_fees_applied(self, engine, always_buy_strategy, sample_ohlcv):
        result = engine.run(always_buy_strategy, sample_ohlcv)
        if result.trades:
            assert all(t.fee > 0 for t in result.trades)

    def test_open_position_at_end_closed(self, engine, sample_ohlcv):
        """If strategy has open position at end, engine should close it."""

        class BuyOnceStrategy(BaseStrategy):
            name = "Buy Once"
            description = "test"
            version = "0.0.1"
            def default_params(self):
                return {}
            def get_required_history(self):
                return 1
            def calculate_indicators(self, df):
                return df
            def analyze(self, df, index):
                if index == 5:
                    return TradeSignal(signal=Signal.BUY, strength=1.0)
                return TradeSignal(signal=Signal.HOLD)

        result = engine.run(BuyOnceStrategy(), sample_ohlcv)
        assert result.num_trades == 1

    def test_win_rate_calculation(self, engine, always_buy_strategy, sample_ohlcv):
        result = engine.run(always_buy_strategy, sample_ohlcv)
        if result.num_trades > 0:
            expected_wr = result.winning_trades / result.num_trades * 100
            assert abs(result.win_rate - expected_wr) < 0.01

    def test_stop_loss_triggers(self, engine, sample_ohlcv):
        """Stop loss should close position when price drops."""

        class StopLossStrategy(BaseStrategy):
            name = "SL Test"
            description = "test"
            version = "0.0.1"
            def default_params(self):
                return {}
            def get_required_history(self):
                return 1
            def calculate_indicators(self, df):
                return df
            def analyze(self, df, index):
                if index == 5:
                    price = df["close"].iloc[index]
                    return TradeSignal(
                        signal=Signal.BUY, strength=1.0,
                        stop_loss=price * 0.5,
                        take_profit=price * 2.0,
                    )
                return TradeSignal(signal=Signal.HOLD)

        result = engine.run(StopLossStrategy(), sample_ohlcv)
        assert result.num_trades >= 1

    def test_custom_position_size(self, sample_ohlcv, always_buy_strategy):
        engine_half = BacktestEngine(initial_capital=10000, position_size=0.5)
        engine_full = BacktestEngine(initial_capital=10000, position_size=1.0)
        r_half = engine_half.run(always_buy_strategy, sample_ohlcv)
        r_full = engine_full.run(always_buy_strategy, sample_ohlcv)
        if r_half.trades and r_full.trades:
            assert r_half.trades[0].quantity < r_full.trades[0].quantity

    def test_progress_callback(self, engine, always_buy_strategy, sample_ohlcv):
        calls = []
        engine.run(always_buy_strategy, sample_ohlcv,
                   progress_callback=lambda cur, tot: calls.append((cur, tot)))
        assert len(calls) > 0
