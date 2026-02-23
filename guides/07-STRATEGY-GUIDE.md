# Strategy Development and Testing Guide

How to create custom trading strategies, apply filters, use ML models, run backtests, walk-forward analysis, and validate with paper trading.

---

## Table of Contents

1. [Strategy Architecture](#strategy-architecture)
2. [Creating a Custom Strategy](#creating-a-custom-strategy)
3. [Strategy Signals and Parameters](#strategy-signals-and-parameters)
4. [Adding Technical Indicators](#adding-technical-indicators)
5. [Backtesting Your Strategy](#backtesting-your-strategy)
6. [Using Filters](#using-filters)
7. [ML Signal Filtering](#ml-signal-filtering)
8. [Sentiment Filtering](#sentiment-filtering)
9. [Walk-Forward Optimization](#walk-forward-optimization)
10. [Out-of-Sample Testing](#out-of-sample-testing)
11. [Dynamic Parameter Optimization](#dynamic-parameter-optimization)
12. [Paper Trading Validation](#paper-trading-validation)
13. [Running Tests](#running-tests)

---

## Strategy Architecture

Every strategy extends `BaseStrategy` and implements two methods:

```
BaseStrategy (abstract)
├── default_params()        → Dict of parameter defaults
├── analyze(df, index)      → Returns TradeSignal (BUY / SELL / HOLD)
├── calculate_indicators()  → Adds columns to DataFrame (optional)
├── get_required_history()  → Minimum candles needed (optional)
└── get_param_schema()      → Parameter ranges for optimization (optional)
```

Strategies produce `TradeSignal` objects that optionally pass through a `FilterChain` before the engine acts on them.

---

## Creating a Custom Strategy

### Step 1: Create the file

Place your strategy in `src/strategies/custom/`:

```python
# src/strategies/custom/my_strategy.py

import pandas as pd
import numpy as np
from src.strategies.base import BaseStrategy, TradeSignal, Signal


class MyStrategy(BaseStrategy):
    name = "My Custom Strategy"
    description = "EMA crossover with volume confirmation"
    version = "1.0.0"

    def default_params(self):
        return {
            "fast_ema": 12,
            "slow_ema": 26,
            "volume_mult": 1.5,
        }

    def get_param_schema(self):
        return {
            "fast_ema": {"type": "int", "min": 5, "max": 50, "description": "Fast EMA period"},
            "slow_ema": {"type": "int", "min": 10, "max": 100, "description": "Slow EMA period"},
            "volume_mult": {"type": "float", "min": 1.0, "max": 3.0, "description": "Volume threshold"},
        }

    def get_required_history(self) -> int:
        return self._params["slow_ema"] + 5

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = self._params["fast_ema"]
        slow = self._params["slow_ema"]

        df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
        df["vol_avg"] = df["volume"].rolling(window=20).mean()

        # ATR for stop loss / take profit
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift(1))
        low_close = abs(df["low"] - df["close"].shift(1))
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()

        return df

    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)

        fast = df["ema_fast"].iloc[index]
        slow = df["ema_slow"].iloc[index]
        fast_prev = df["ema_fast"].iloc[index - 1]
        slow_prev = df["ema_slow"].iloc[index - 1]
        vol = df["volume"].iloc[index]
        vol_avg = df["vol_avg"].iloc[index]
        close = df["close"].iloc[index]
        atr = df["atr"].iloc[index]

        if pd.isna(fast) or pd.isna(slow) or pd.isna(atr):
            return TradeSignal(signal=Signal.HOLD)

        vol_ok = vol > vol_avg * self._params["volume_mult"]

        # BUY: fast crosses above slow with volume
        if fast_prev <= slow_prev and fast > slow and vol_ok:
            return TradeSignal(
                signal=Signal.BUY,
                strength=0.8,
                stop_loss=close - atr * 2,
                take_profit=close + atr * 3,
                metadata={"reason": "ema_crossover_up"},
            )

        # SELL: fast crosses below slow
        if fast_prev >= slow_prev and fast < slow:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.8,
                metadata={"reason": "ema_crossover_down"},
            )

        return TradeSignal(signal=Signal.HOLD)
```

### Step 2: Register it

The `StrategyRegistry` auto-discovers strategies from `src/strategies/custom/` at startup. Just make sure your file is in that directory and the class inherits from `BaseStrategy`.

Verify:

```python
from src.strategies.registry import get_registry
reg = get_registry()
print(reg.get_names())
# Should include "My Custom Strategy"
```

---

## Strategy Signals and Parameters

### TradeSignal

```python
@dataclass
class TradeSignal:
    signal: Signal           # Signal.BUY, Signal.SELL, or Signal.HOLD
    strength: float = 1.0    # 0.0 to 1.0 confidence
    stop_loss: float = None  # Optional stop loss price
    take_profit: float = None # Optional take profit price
    metadata: dict = {}      # Any extra data
```

- `signal` is the only required field
- `stop_loss` and `take_profit` are respected by both the backtest engine and the live engine
- `strength` can be used by filters (e.g., only trade when strength > 0.7)
- `metadata` is logged and appears in reports

### Parameters

Access parameters via `self._params`:

```python
def analyze(self, df, index):
    period = self._params["period"]
    threshold = self._params["threshold"]
    # ...
```

Override defaults at instantiation:

```python
strategy = MyStrategy(params={"fast_ema": 20, "slow_ema": 50})
```

---

## Adding Technical Indicators

The project includes the `ta` library. Use it in `calculate_indicators()`:

```python
import ta

def calculate_indicators(self, df):
    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # MACD
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()

    return df
```

Or compute manually using pandas/numpy (as shown in the built-in strategies).

---

## Backtesting Your Strategy

### Python API

```python
from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import MetricsCalculator
from src.backtesting.report import ReportGenerator
from src.core.data_manager import DataManager
from src.strategies.custom.my_strategy import MyStrategy

# Get data
dm = DataManager()
data = dm.get_ohlcv("binance", "BTC/USDT", "1h",
                     start=datetime(2024, 1, 1),
                     end=datetime(2024, 6, 1))

# Run backtest
engine = BacktestEngine(initial_capital=10000, fee_percent=0.1)
strategy = MyStrategy()
result = engine.run(strategy, data, symbol="BTC/USDT", timeframe="1h")

# Calculate metrics
calc = MetricsCalculator()
metrics = calc.calculate(result)
print(metrics.to_dict())

# Generate HTML report
report = ReportGenerator()
path = report.generate(result, metrics)
print(f"Report: {path}")
```

### Via the GUI

1. Open the Electron app
2. Go to **Backtest**
3. Select your strategy, symbol, timeframe, and date range
4. Click **Run**

### Via the API

```bash
curl -X POST http://localhost:8765/api/backtest/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "strategy": "My Custom Strategy",
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01",
    "initial_capital": 10000
  }'
```

---

## Using Filters

Filters wrap a strategy and can block or modify signals based on external conditions.

### Regime Filter

Only trade in trending markets:

```python
from src.strategies.filters import FilteredStrategy, RegimeFilter

strategy = MyStrategy()
filtered = FilteredStrategy(strategy, filters=[
    RegimeFilter(allowed_regimes=["trending_bullish", "trending_bearish"])
])

result = engine.run(filtered, data)
```

### Multi-Timeframe Filter

Require higher timeframe confirmation:

```python
from src.strategies.filters import MultiTimeframeFilter
from src.strategies.filters.multi_timeframe import resample_to_higher_timeframe

# Resample data to 4h and 1d
data_4h = resample_to_higher_timeframe(data, "1h", "4h")
data_1d = resample_to_higher_timeframe(data, "1h", "1d")

filtered = FilteredStrategy(strategy, filters=[
    MultiTimeframeFilter(confirmation_timeframes=["4h", "1d"])
])
filtered.set_context({"timeframe_data": {"4h": data_4h, "1d": data_1d}})

result = engine.run(filtered, data)
```

### Chaining filters

```python
filtered = FilteredStrategy(strategy, filters=[
    RegimeFilter(allowed_regimes=["trending_bullish", "trending_bearish"]),
    MultiTimeframeFilter(confirmation_timeframes=["4h"]),
])
```

Signals must pass ALL filters in the chain.

---

## ML Signal Filtering

### Training the ML filter

```python
from src.strategies.filters.ml_filter import MLSignalFilter

# First, run a backtest to get trade data
result = engine.run(strategy, data)

# Build training labels from trade outcomes
trade_indices = []
trade_labels = []
for trade in result.trades:
    idx = data[data["timestamp"] == trade.entry_time].index
    if len(idx) > 0:
        trade_indices.append(idx[0])
        trade_labels.append(1 if trade.pnl > 0 else 0)

# Train
ml_filter = MLSignalFilter(model_type="gradient_boosting")
df_with_indicators = strategy.calculate_indicators(data.copy())
stats = ml_filter.train(df_with_indicators, trade_indices, trade_labels)
print(f"Test accuracy: {stats['test_accuracy']:.3f}")

# Save model
ml_filter.save_model("data/models/my_strategy_filter.pkl")
```

### Using the LSTM filter

```python
from src.strategies.filters.ml_filter import LSTMSignalFilter

lstm_filter = LSTMSignalFilter(seq_len=20, hidden_size=32)
stats = lstm_filter.train(df_with_indicators, trade_indices, trade_labels, epochs=30)
lstm_filter.save_model("data/models/my_strategy_lstm.pt")
```

### Applying in production

```python
ml_filter = MLSignalFilter()
ml_filter.load_model("data/models/my_strategy_filter.pkl")

filtered = FilteredStrategy(strategy, filters=[ml_filter])
result = engine.run(filtered, data)
```

---

## Sentiment Filtering

```python
from src.strategies.filters.sentiment_filter import SentimentFilter

sentiment = SentimentFilter(
    fear_greed_threshold=25,
    greed_threshold=75,
    news_api_key="",  # optional CryptoCompare key
)

filtered = FilteredStrategy(strategy, filters=[sentiment])
```

The filter calls the Fear & Greed Index API and optionally analyses news headlines with VADER sentiment. Results are cached to avoid rate limits.

---

## Walk-Forward Optimization

Walk-forward analysis splits data into rolling train/test windows to check if optimized parameters generalize.

```python
from src.backtesting.walk_forward import WalkForwardEngine
from src.strategies.custom.my_strategy import MyStrategy

wf = WalkForwardEngine(
    n_splits=5,
    train_ratio=0.7,
    optimisation_metric="sharpe_ratio",
    n_trials=50,
)

result = wf.run(
    MyStrategy,
    data,
    symbol="BTC/USDT",
    timeframe="1h",
)

print(f"OOS return: {result.oos_return_pct:.2f}%")
print(f"Efficiency ratio: {result.efficiency_ratio:.2f}")
print(f"Aggregated OOS metrics: {result.aggregated_oos_metrics}")
```

An efficiency ratio above 0.5 suggests the strategy generalises reasonably well.

---

## Out-of-Sample Testing

Simple train/test split to detect overfitting:

```python
from src.backtesting.oos_testing import OOSTester

tester = OOSTester(test_ratio=0.3)
result = tester.run(strategy, data, symbol="BTC/USDT")

print(f"Overfitting score: {result.overfitting_score:.2f}")
# 0 = no overfitting, 1 = completely overfit

for metric, values in result.comparison.items():
    print(f"  {metric}: IS={values['in_sample']:.2f}  OOS={values['oos']:.2f}  "
          f"degradation={values.get('degradation_pct', 'N/A')}")
```

---

## Dynamic Parameter Optimization

Find optimal parameters with Bayesian optimization:

```python
from src.strategies.optimizer import StrategyOptimizer

optimizer = StrategyOptimizer(metric="sharpe_ratio", n_trials=100)
result = optimizer.optimize(MyStrategy, data, symbol="BTC/USDT")

print(f"Best params: {result.best_params}")
print(f"Best {result.metric}: {result.best_score:.4f}")
```

### Adaptive re-optimization

Re-optimize on a rolling window:

```python
adaptive = optimizer.adaptive_optimize(
    MyStrategy, data,
    retrain_every=168,     # re-optimize every 168 bars (1 week of hourly data)
    window_size=500,       # optimize on the last 500 bars
)

for i, params in enumerate(adaptive.param_history):
    print(f"Window {i}: {params}")
```

---

## Paper Trading Validation

Replay historical data as if it were live to validate your strategy matches backtest expectations:

```python
from src.trading.paper_validator import PaperTradingValidator

validator = PaperTradingValidator(
    strategy=MyStrategy(),
    symbol="BTC/USDT",
    timeframe="1h",
    initial_balance=10000,
    fee_percent=0.1,
    slippage_percent=0.05,
)

report = validator.run(data)
print(f"Paper trades: {report.num_trades}")
print(f"Return: {report.total_return_pct:.2f}%")

# Compare against backtest
bt_result = engine.run(strategy, data)
comparison = PaperTradingValidator.compare_with_backtest(report, bt_result)
print(f"Match: {comparison['match']}")
print(f"Return diff: {comparison['return_diff_pct']:.2f}%")
```

---

## Running Tests

### Run all tests

```bash
cd "/path/to/crypto-trading-bot"
python3 -m pytest tests/ -v
```

### Run specific test files

```bash
python3 -m pytest tests/test_strategies.py -v
python3 -m pytest tests/test_backtest_engine.py -v
```

### Run with coverage

```bash
python3 -m pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in a browser
```

### Run integration tests (requires exchange sandbox keys)

```bash
export TEST_EXCHANGE_API_KEY="your_sandbox_key"
export TEST_EXCHANGE_API_SECRET="your_sandbox_secret"
python3 -m pytest tests/ -m integration -v
```

### Skip slow tests

```bash
python3 -m pytest tests/ -m "not slow" -v
```

### Write tests for your custom strategy

Create `tests/test_my_strategy.py`:

```python
import pytest
from src.strategies.custom.my_strategy import MyStrategy
from src.backtesting.engine import BacktestEngine


class TestMyStrategy:

    @pytest.fixture
    def strategy(self):
        return MyStrategy()

    def test_produces_valid_signals(self, strategy, sample_ohlcv):
        df = strategy.calculate_indicators(sample_ohlcv.copy())
        for i in range(strategy.get_required_history(), len(df)):
            sig = strategy.analyze(df, i)
            assert sig.signal in ("buy", "sell", "hold") or hasattr(sig.signal, "value")

    def test_backtest_completes(self, strategy, sample_ohlcv):
        engine = BacktestEngine(initial_capital=10000)
        result = engine.run(strategy, sample_ohlcv, symbol="TEST/USDT")
        assert result.initial_capital == 10000

    def test_param_schema(self, strategy):
        schema = strategy.get_param_schema()
        assert "fast_ema" in schema
        assert schema["fast_ema"]["min"] < schema["fast_ema"]["max"]
```
