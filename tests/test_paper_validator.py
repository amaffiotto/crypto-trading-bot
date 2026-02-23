"""Tests for PaperTradingValidator."""

import pytest

from src.backtesting.engine import BacktestEngine
from src.trading.paper_validator import PaperTradingValidator, ValidationReport


class TestPaperTradingValidator:

    def test_run_returns_validation_report(self, always_buy_strategy, sample_ohlcv):
        v = PaperTradingValidator(always_buy_strategy, initial_balance=10000)
        report = v.run(sample_ohlcv)
        assert isinstance(report, ValidationReport)
        assert report.initial_balance == 10000

    def test_trades_produced(self, always_buy_strategy, sample_ohlcv):
        v = PaperTradingValidator(always_buy_strategy)
        report = v.run(sample_ohlcv)
        assert report.num_trades > 0

    def test_no_trades_with_hold_strategy(self, never_trade_strategy, sample_ohlcv):
        v = PaperTradingValidator(never_trade_strategy)
        report = v.run(sample_ohlcv)
        assert report.num_trades == 0
        assert abs(report.final_balance - report.initial_balance) < 0.01

    def test_equity_curve_populated(self, always_buy_strategy, sample_ohlcv):
        v = PaperTradingValidator(always_buy_strategy)
        report = v.run(sample_ohlcv)
        assert not report.equity_curve.empty
        assert "equity" in report.equity_curve.columns

    def test_signals_log_populated(self, always_buy_strategy, sample_ohlcv):
        v = PaperTradingValidator(always_buy_strategy)
        report = v.run(sample_ohlcv)
        assert len(report.signals_log) > 0

    def test_metrics_attached(self, always_buy_strategy, sample_ohlcv):
        v = PaperTradingValidator(always_buy_strategy)
        report = v.run(sample_ohlcv)
        if report.num_trades > 0:
            assert report.metrics is not None

    def test_compare_with_backtest_close(self, always_buy_strategy, sample_ohlcv):
        """Paper replay and backtest should produce similar results."""
        engine = BacktestEngine(initial_capital=10000, fee_percent=0.1, slippage_percent=0.05)
        bt_result = engine.run(always_buy_strategy, sample_ohlcv)

        validator = PaperTradingValidator(
            always_buy_strategy,
            initial_balance=10000,
            fee_percent=0.1,
            slippage_percent=0.05,
        )
        report = validator.run(sample_ohlcv)

        comparison = PaperTradingValidator.compare_with_backtest(
            report, bt_result, tolerance_pct=2.0,
        )
        assert comparison["trades_diff"] <= 2
        assert comparison["capital_diff_pct"] < 5.0

    def test_progress_callback_called(self, always_buy_strategy, sample_ohlcv):
        calls = []
        v = PaperTradingValidator(always_buy_strategy)
        v.run(sample_ohlcv, progress_callback=lambda c, t: calls.append((c, t)))
        assert len(calls) > 0
