"""Tests for MetricsCalculator."""

import numpy as np
import pandas as pd
import pytest

from src.backtesting.metrics import MetricsCalculator, PerformanceMetrics


class TestMetricsCalculator:

    def test_calculate_returns_performance_metrics(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        assert isinstance(m, PerformanceMetrics)

    def test_total_trades_correct(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        assert m.total_trades == len(sample_backtest_result.trades)

    def test_win_rate_correct(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        wins = sum(1 for t in sample_backtest_result.trades if t.pnl > 0)
        expected = wins / len(sample_backtest_result.trades) * 100
        assert abs(m.win_rate - expected) < 0.01

    def test_profit_factor_positive(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        assert m.profit_factor >= 0

    def test_max_drawdown_non_negative(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        assert m.max_drawdown >= 0

    def test_largest_win_and_loss(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        pnls = [t.pnl for t in sample_backtest_result.trades]
        assert m.largest_win == max(pnls)
        assert m.largest_loss == min(pnls)

    def test_total_fees(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        expected_fees = sum(t.fee for t in sample_backtest_result.trades)
        assert abs(m.total_fees - expected_fees) < 0.01

    def test_sharpe_ratio_finite(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        assert np.isfinite(m.sharpe_ratio)

    def test_empty_equity_curve(self, metrics_calculator):
        from src.backtesting.engine import BacktestResult
        from datetime import datetime
        result = BacktestResult(
            strategy_name="Empty",
            symbol="X/Y",
            timeframe="1h",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            initial_capital=10000,
            final_capital=10000,
            trades=[],
            equity_curve=pd.DataFrame(),
            parameters={},
        )
        m = metrics_calculator.calculate(result)
        assert m.total_trades == 0
        assert m.sharpe_ratio == 0.0

    def test_to_dict_keys(self, metrics_calculator, sample_backtest_result):
        m = metrics_calculator.calculate(sample_backtest_result)
        d = m.to_dict()
        assert "Total Return" in d
        assert "Sharpe Ratio" in d
        assert "Win Rate" in d

    def test_monthly_returns(self, metrics_calculator, sample_backtest_result):
        mr = metrics_calculator.calculate_monthly_returns(sample_backtest_result)
        assert isinstance(mr, pd.DataFrame)

    def test_trade_distribution(self, metrics_calculator, sample_backtest_result):
        dist = metrics_calculator.get_trade_distribution(sample_backtest_result)
        assert isinstance(dist, pd.Series)
        assert len(dist) == len(sample_backtest_result.trades)
