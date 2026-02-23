"""Out-of-sample testing to detect strategy overfitting.

Splits data into in-sample and out-of-sample segments, runs a backtest
on each, and compares the performance metrics to quantify overfitting.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.metrics import MetricsCalculator, PerformanceMetrics
from src.strategies.base import BaseStrategy
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class OOSResult:
    """Results from an out-of-sample test."""
    strategy_name: str
    symbol: str
    timeframe: str
    in_sample_metrics: PerformanceMetrics
    out_of_sample_metrics: PerformanceMetrics
    in_sample_result: BacktestResult
    oos_result: BacktestResult
    overfitting_score: float
    comparison: Dict[str, Any]


class OOSTester:
    """Simple train/test split to detect overfitting."""

    def __init__(
        self,
        engine: Optional[BacktestEngine] = None,
        test_ratio: float = 0.3,
    ):
        self.engine = engine or BacktestEngine()
        self.test_ratio = min(0.5, max(0.1, test_ratio))
        self.calc = MetricsCalculator()

    def run(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        symbol: str = "UNKNOWN",
        timeframe: str = "1h",
    ) -> OOSResult:
        """Split *data*, backtest on both halves, and compare metrics."""
        split_idx = int(len(data) * (1 - self.test_ratio))
        in_sample = data.iloc[:split_idx].reset_index(drop=True)
        oos_data = data.iloc[split_idx:].reset_index(drop=True)

        logger.info(f"OOS split: in-sample={len(in_sample)} bars, oos={len(oos_data)} bars")

        is_result = self.engine.run(strategy, in_sample, symbol, timeframe)
        is_metrics = self.calc.calculate(is_result)

        oos_result = self.engine.run(strategy, oos_data, symbol, timeframe)
        oos_metrics = self.calc.calculate(oos_result)

        comparison = self._compare(is_metrics, oos_metrics)
        ov_score = self._overfitting_score(is_metrics, oos_metrics)

        return OOSResult(
            strategy_name=strategy.name,
            symbol=symbol,
            timeframe=timeframe,
            in_sample_metrics=is_metrics,
            out_of_sample_metrics=oos_metrics,
            in_sample_result=is_result,
            oos_result=oos_result,
            overfitting_score=ov_score,
            comparison=comparison,
        )

    @staticmethod
    def _compare(is_m: PerformanceMetrics, oos_m: PerformanceMetrics) -> Dict[str, Any]:
        pairs = [
            ("total_return_pct", is_m.total_return_pct, oos_m.total_return_pct),
            ("sharpe_ratio", is_m.sharpe_ratio, oos_m.sharpe_ratio),
            ("max_drawdown", is_m.max_drawdown, oos_m.max_drawdown),
            ("win_rate", is_m.win_rate, oos_m.win_rate),
            ("profit_factor", is_m.profit_factor, oos_m.profit_factor),
            ("total_trades", is_m.total_trades, oos_m.total_trades),
        ]
        out: Dict[str, Any] = {}
        for name, is_val, oos_val in pairs:
            out[name] = {
                "in_sample": round(float(is_val), 4),
                "oos": round(float(oos_val), 4),
                "degradation_pct": (
                    round((1 - oos_val / is_val) * 100, 2)
                    if is_val != 0 and np.isfinite(is_val) and np.isfinite(oos_val)
                    else None
                ),
            }
        return out

    @staticmethod
    def _overfitting_score(is_m: PerformanceMetrics, oos_m: PerformanceMetrics) -> float:
        """Return 0-1 score where 0 = no overfitting, 1 = completely overfit.

        Uses a weighted combination of return degradation, Sharpe
        degradation, and drawdown increase.
        """
        scores = []

        # Return degradation
        if is_m.total_return_pct > 0:
            ret_deg = max(0, 1 - oos_m.total_return_pct / is_m.total_return_pct)
            scores.append(min(ret_deg, 1.0))

        # Sharpe degradation
        if is_m.sharpe_ratio > 0:
            sharpe_deg = max(0, 1 - oos_m.sharpe_ratio / is_m.sharpe_ratio)
            scores.append(min(sharpe_deg, 1.0))

        # Drawdown increase
        if is_m.max_drawdown > 0:
            dd_increase = max(0, oos_m.max_drawdown / is_m.max_drawdown - 1)
            scores.append(min(dd_increase, 1.0))

        if not scores:
            return 0.0
        return float(np.mean(scores))
