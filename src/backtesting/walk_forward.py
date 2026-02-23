"""Walk-forward optimisation engine.

Splits historical data into rolling train/test windows, optimises strategy
parameters on each training window, then evaluates on the test window.
Aggregated out-of-sample results reveal whether a strategy generalises.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

import numpy as np
import pandas as pd

from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.metrics import MetricsCalculator, PerformanceMetrics
from src.strategies.base import BaseStrategy
from src.utils.logger import get_logger

logger = get_logger()

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class WindowResult:
    """Result for a single walk-forward window."""
    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: Dict[str, Any]
    train_metrics: PerformanceMetrics
    test_metrics: PerformanceMetrics
    train_result: BacktestResult
    test_result: BacktestResult


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward analysis result."""
    strategy_name: str
    symbol: str
    timeframe: str
    n_windows: int
    windows: List[WindowResult]
    aggregated_oos_metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def oos_trades(self) -> int:
        return sum(w.test_result.num_trades for w in self.windows)

    @property
    def oos_return_pct(self) -> float:
        if not self.windows:
            return 0.0
        compound = 1.0
        for w in self.windows:
            compound *= (1 + w.test_result.total_return)
        return (compound - 1) * 100

    @property
    def efficiency_ratio(self) -> float:
        """Ratio of OOS to in-sample average return.  >0.5 is decent."""
        is_returns = [w.train_metrics.total_return_pct for w in self.windows]
        oos_returns = [w.test_metrics.total_return_pct for w in self.windows]
        avg_is = np.mean(is_returns) if is_returns else 0
        avg_oos = np.mean(oos_returns) if oos_returns else 0
        if avg_is == 0:
            return 0.0
        return avg_oos / avg_is


# ------------------------------------------------------------------
# Walk-forward engine
# ------------------------------------------------------------------

class WalkForwardEngine:
    """Rolling-window walk-forward optimisation."""

    def __init__(
        self,
        engine: Optional[BacktestEngine] = None,
        n_splits: int = 5,
        train_ratio: float = 0.7,
        optimisation_metric: str = "sharpe_ratio",
        n_trials: int = 50,
    ):
        self.engine = engine or BacktestEngine()
        self.n_splits = n_splits
        self.train_ratio = train_ratio
        self.metric = optimisation_metric
        self.n_trials = n_trials
        self.calc = MetricsCalculator()

    # ------------------------------------------------------------------
    def run(
        self,
        strategy_class: Type[BaseStrategy],
        data: pd.DataFrame,
        param_space: Optional[Dict[str, Dict]] = None,
        symbol: str = "UNKNOWN",
        timeframe: str = "1h",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> WalkForwardResult:
        """Execute walk-forward analysis.

        Parameters
        ----------
        strategy_class : class inheriting BaseStrategy
        data : OHLCV DataFrame
        param_space : ``{param_name: {"type": "int"/"float", "min": ..., "max": ...}}``
            Defaults to ``strategy_class().get_param_schema()``.
        """
        if param_space is None:
            param_space = strategy_class().get_param_schema()

        windows = self._split_data(data)
        results: List[WindowResult] = []

        for idx, (train_df, test_df) in enumerate(windows):
            if progress_callback:
                progress_callback(idx, len(windows))

            logger.info(f"Walk-forward window {idx+1}/{len(windows)}  "
                        f"train={len(train_df)} bars  test={len(test_df)} bars")

            best_params = self._optimise_window(strategy_class, train_df, param_space, symbol, timeframe)

            # evaluate on train
            train_strat = strategy_class(params=best_params)
            train_bt = self.engine.run(train_strat, train_df, symbol, timeframe)
            train_m = self.calc.calculate(train_bt)

            # evaluate on test
            test_strat = strategy_class(params=best_params)
            test_bt = self.engine.run(test_strat, test_df, symbol, timeframe)
            test_m = self.calc.calculate(test_bt)

            results.append(WindowResult(
                window_index=idx,
                train_start=train_df["timestamp"].iloc[0],
                train_end=train_df["timestamp"].iloc[-1],
                test_start=test_df["timestamp"].iloc[0],
                test_end=test_df["timestamp"].iloc[-1],
                best_params=best_params,
                train_metrics=train_m,
                test_metrics=test_m,
                train_result=train_bt,
                test_result=test_bt,
            ))

        if progress_callback:
            progress_callback(len(windows), len(windows))

        wf = WalkForwardResult(
            strategy_name=strategy_class.name if hasattr(strategy_class, "name") else strategy_class.__name__,
            symbol=symbol,
            timeframe=timeframe,
            n_windows=len(windows),
            windows=results,
        )
        wf.aggregated_oos_metrics = self._aggregate_oos(results)
        return wf

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split_data(self, data: pd.DataFrame):
        """Create rolling train/test splits."""
        n = len(data)
        window_size = n // self.n_splits
        if window_size < 50:
            logger.warning("Window size very small – consider using more data")

        train_size = int(window_size * self.train_ratio)
        test_size = window_size - train_size
        splits = []

        for i in range(self.n_splits):
            start = i * window_size
            train_end = start + train_size
            test_end = min(start + window_size, n)
            if train_end >= n or test_end > n:
                break
            splits.append((
                data.iloc[start:train_end].reset_index(drop=True),
                data.iloc[train_end:test_end].reset_index(drop=True),
            ))

        return splits

    def _optimise_window(
        self,
        strategy_class: Type[BaseStrategy],
        train_data: pd.DataFrame,
        param_space: Dict,
        symbol: str,
        timeframe: str,
    ) -> Dict[str, Any]:
        """Find best params for a single training window."""
        if not param_space:
            return strategy_class().params

        if HAS_OPTUNA:
            return self._optuna_optimise(strategy_class, train_data, param_space, symbol, timeframe)
        return self._grid_optimise(strategy_class, train_data, param_space, symbol, timeframe)

    def _optuna_optimise(self, strategy_class, train_data, param_space, symbol, timeframe):
        metric_name = self.metric

        def objective(trial: "optuna.Trial") -> float:
            params = {}
            for name, spec in param_space.items():
                ptype = spec.get("type", "int")
                lo = spec.get("min", 1)
                hi = spec.get("max", 100)
                if ptype == "float":
                    params[name] = trial.suggest_float(name, lo, hi)
                else:
                    params[name] = trial.suggest_int(name, int(lo), int(hi))

            strat = strategy_class(params=params)
            result = self.engine.run(strat, train_data, symbol, timeframe)
            m = self.calc.calculate(result)
            return getattr(m, metric_name, 0.0)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)
        return study.best_params

    def _grid_optimise(self, strategy_class, train_data, param_space, symbol, timeframe):
        """Simple random search fallback when optuna is unavailable."""
        best_score = -np.inf
        best_params = strategy_class().params
        rng = np.random.default_rng(42)

        for _ in range(min(self.n_trials, 30)):
            params = {}
            for name, spec in param_space.items():
                lo = spec.get("min", 1)
                hi = spec.get("max", 100)
                if spec.get("type") == "float":
                    params[name] = rng.uniform(lo, hi)
                else:
                    params[name] = int(rng.integers(int(lo), int(hi) + 1))
            strat = strategy_class(params=params)
            result = self.engine.run(strat, train_data, symbol, timeframe)
            m = self.calc.calculate(result)
            score = getattr(m, self.metric, 0.0)
            if score > best_score:
                best_score = score
                best_params = params

        return best_params

    def _aggregate_oos(self, windows: List[WindowResult]) -> Dict[str, float]:
        if not windows:
            return {}
        oos_returns = [w.test_metrics.total_return_pct for w in windows]
        oos_sharpe = [w.test_metrics.sharpe_ratio for w in windows]
        oos_dd = [w.test_metrics.max_drawdown for w in windows]
        return {
            "avg_return_pct": float(np.mean(oos_returns)),
            "std_return_pct": float(np.std(oos_returns)),
            "avg_sharpe": float(np.mean(oos_sharpe)),
            "avg_max_drawdown": float(np.mean(oos_dd)),
            "total_oos_trades": sum(w.test_result.num_trades for w in windows),
        }
