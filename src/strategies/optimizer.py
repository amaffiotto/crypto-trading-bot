"""Bayesian strategy parameter optimiser.

Uses Optuna (with a random-search fallback) to find optimal strategy
parameters by maximising a chosen backtest metric.  Supports one-shot
optimisation as well as adaptive re-optimisation on a rolling window.
"""

from dataclasses import dataclass, field
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
# Result containers
# ------------------------------------------------------------------

@dataclass
class TrialResult:
    """A single optimisation trial."""
    params: Dict[str, Any]
    metric_value: float
    metrics: Optional[PerformanceMetrics] = None


@dataclass
class OptimizationResult:
    """Full optimisation output."""
    strategy_name: str
    metric: str
    best_params: Dict[str, Any]
    best_score: float
    best_metrics: Optional[PerformanceMetrics]
    trials: List[TrialResult]
    n_trials: int
    symbol: str = ""
    timeframe: str = ""

    @property
    def convergence(self) -> List[float]:
        """Running best score across trials."""
        best = -np.inf
        out = []
        for t in self.trials:
            best = max(best, t.metric_value)
            out.append(best)
        return out


@dataclass
class AdaptiveResult:
    """Result of adaptive (rolling) re-optimisation."""
    windows: List[OptimizationResult]
    param_history: List[Dict[str, Any]]


# ------------------------------------------------------------------
# Optimiser
# ------------------------------------------------------------------

class StrategyOptimizer:
    """Find optimal strategy parameters via Bayesian optimisation.

    Example::

        optimizer = StrategyOptimizer(metric="sharpe_ratio", n_trials=100)
        result = optimizer.optimize(MACrossover, data, symbol="BTC/USDT")
        print(result.best_params, result.best_score)

    If *param_space* is not supplied the strategy's ``get_param_schema()``
    is used.
    """

    def __init__(
        self,
        engine: Optional[BacktestEngine] = None,
        metric: str = "sharpe_ratio",
        n_trials: int = 100,
    ):
        self.engine = engine or BacktestEngine()
        self.metric = metric
        self.n_trials = n_trials
        self.calc = MetricsCalculator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        strategy_class: Type[BaseStrategy],
        data: pd.DataFrame,
        param_space: Optional[Dict[str, Dict]] = None,
        symbol: str = "UNKNOWN",
        timeframe: str = "1h",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> OptimizationResult:
        """Run optimisation for *strategy_class* on *data*."""
        if param_space is None:
            param_space = strategy_class().get_param_schema()

        if not param_space:
            strat = strategy_class()
            result = self.engine.run(strat, data, symbol, timeframe)
            m = self.calc.calculate(result)
            return OptimizationResult(
                strategy_name=strategy_class.name if hasattr(strategy_class, "name") else strategy_class.__name__,
                metric=self.metric,
                best_params=strat.params,
                best_score=getattr(m, self.metric, 0.0),
                best_metrics=m,
                trials=[],
                n_trials=0,
                symbol=symbol,
                timeframe=timeframe,
            )

        if HAS_OPTUNA:
            return self._optuna_optimize(strategy_class, data, param_space, symbol, timeframe, progress_callback)
        return self._random_optimize(strategy_class, data, param_space, symbol, timeframe, progress_callback)

    def adaptive_optimize(
        self,
        strategy_class: Type[BaseStrategy],
        data: pd.DataFrame,
        param_space: Optional[Dict[str, Dict]] = None,
        retrain_every: int = 168,
        window_size: Optional[int] = None,
        symbol: str = "UNKNOWN",
        timeframe: str = "1h",
    ) -> AdaptiveResult:
        """Re-optimise parameters every *retrain_every* bars on a rolling window.

        Returns an ``AdaptiveResult`` with the parameter set chosen for
        each window.
        """
        if param_space is None:
            param_space = strategy_class().get_param_schema()

        win = window_size or retrain_every * 3
        results: List[OptimizationResult] = []
        param_history: List[Dict[str, Any]] = []

        idx = 0
        while idx + win < len(data):
            window = data.iloc[idx: idx + win].reset_index(drop=True)
            opt = self.optimize(strategy_class, window, param_space, symbol, timeframe)
            results.append(opt)
            param_history.append(opt.best_params)
            logger.info(f"Adaptive window @{idx}: best {self.metric}={opt.best_score:.4f}  params={opt.best_params}")
            idx += retrain_every

        return AdaptiveResult(windows=results, param_history=param_history)

    # ------------------------------------------------------------------
    # Internal: Optuna
    # ------------------------------------------------------------------

    def _optuna_optimize(self, strategy_class, data, param_space, symbol, timeframe, progress_cb):
        trials_log: List[TrialResult] = []
        metric_name = self.metric
        eng = self.engine
        calc = self.calc

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
            result = eng.run(strat, data, symbol, timeframe)
            m = calc.calculate(result)
            score = getattr(m, metric_name, 0.0)
            trials_log.append(TrialResult(params=params, metric_value=score, metrics=m))
            if progress_cb:
                progress_cb(len(trials_log), self.n_trials)
            return score

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)

        best_idx = max(range(len(trials_log)), key=lambda i: trials_log[i].metric_value)
        best = trials_log[best_idx]

        return OptimizationResult(
            strategy_name=strategy_class.name if hasattr(strategy_class, "name") else strategy_class.__name__,
            metric=self.metric,
            best_params=best.params,
            best_score=best.metric_value,
            best_metrics=best.metrics,
            trials=trials_log,
            n_trials=self.n_trials,
            symbol=symbol,
            timeframe=timeframe,
        )

    # ------------------------------------------------------------------
    # Internal: random-search fallback
    # ------------------------------------------------------------------

    def _random_optimize(self, strategy_class, data, param_space, symbol, timeframe, progress_cb):
        rng = np.random.default_rng(42)
        trials_log: List[TrialResult] = []
        best_score = -np.inf
        best_params = strategy_class().params
        best_metrics = None

        for i in range(self.n_trials):
            params = {}
            for name, spec in param_space.items():
                lo = spec.get("min", 1)
                hi = spec.get("max", 100)
                if spec.get("type") == "float":
                    params[name] = rng.uniform(lo, hi)
                else:
                    params[name] = int(rng.integers(int(lo), int(hi) + 1))

            strat = strategy_class(params=params)
            result = self.engine.run(strat, data, symbol, timeframe)
            m = self.calc.calculate(result)
            score = getattr(m, self.metric, 0.0)
            trials_log.append(TrialResult(params=params, metric_value=score, metrics=m))

            if score > best_score:
                best_score = score
                best_params = params
                best_metrics = m

            if progress_cb:
                progress_cb(i + 1, self.n_trials)

        return OptimizationResult(
            strategy_name=strategy_class.name if hasattr(strategy_class, "name") else strategy_class.__name__,
            metric=self.metric,
            best_params=best_params,
            best_score=best_score,
            best_metrics=best_metrics,
            trials=trials_log,
            n_trials=self.n_trials,
            symbol=symbol,
            timeframe=timeframe,
        )
