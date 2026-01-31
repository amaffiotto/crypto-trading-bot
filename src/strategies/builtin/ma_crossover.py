"""Moving Average Crossover Strategy."""

from typing import Any, Dict
import pandas as pd

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class MACrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy.
    
    Generates BUY signals when the fast MA crosses above the slow MA (golden cross).
    Generates SELL signals when the fast MA crosses below the slow MA (death cross).
    """
    
    name = "MA Crossover"
    description = "Buy on golden cross, sell on death cross"
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters for MA Crossover strategy."""
        return {
            "fast_period": 9,
            "slow_period": 21,
            "ma_type": "sma"  # 'sma' or 'ema'
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "fast_period": {
                "type": "int",
                "min": 2,
                "max": 100,
                "description": "Fast moving average period"
            },
            "slow_period": {
                "type": "int",
                "min": 5,
                "max": 200,
                "description": "Slow moving average period"
            },
            "ma_type": {
                "type": "str",
                "options": ["sma", "ema"],
                "description": "Moving average type (SMA or EMA)"
            }
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return max(self._params["fast_period"], self._params["slow_period"]) + 1
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate fast and slow moving averages."""
        fast = self._params["fast_period"]
        slow = self._params["slow_period"]
        ma_type = self._params.get("ma_type", "sma")
        
        if ma_type == "ema":
            df["ma_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
            df["ma_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
        else:  # sma
            df["ma_fast"] = df["close"].rolling(window=fast).mean()
            df["ma_slow"] = df["close"].rolling(window=slow).mean()
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze for MA crossover signals.
        
        Args:
            df: DataFrame with calculated MAs
            index: Current candle index
            
        Returns:
            TradeSignal with BUY on golden cross, SELL on death cross
        """
        # Need at least 2 candles to detect a crossover
        if index < 1:
            return TradeSignal(Signal.HOLD)
        
        # Check if we have valid MA values
        if pd.isna(df.iloc[index]["ma_fast"]) or pd.isna(df.iloc[index]["ma_slow"]):
            return TradeSignal(Signal.HOLD)
        
        if pd.isna(df.iloc[index - 1]["ma_fast"]) or pd.isna(df.iloc[index - 1]["ma_slow"]):
            return TradeSignal(Signal.HOLD)
        
        prev_fast = df.iloc[index - 1]["ma_fast"]
        prev_slow = df.iloc[index - 1]["ma_slow"]
        curr_fast = df.iloc[index]["ma_fast"]
        curr_slow = df.iloc[index]["ma_slow"]
        
        # Golden cross: fast MA crosses above slow MA
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            # Calculate signal strength based on crossover magnitude
            magnitude = (curr_fast - curr_slow) / curr_slow
            strength = min(1.0, abs(magnitude) * 100)
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=strength,
                metadata={
                    "crossover_type": "golden_cross",
                    "ma_fast": curr_fast,
                    "ma_slow": curr_slow
                }
            )
        
        # Death cross: fast MA crosses below slow MA
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            magnitude = (curr_slow - curr_fast) / curr_slow
            strength = min(1.0, abs(magnitude) * 100)
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=strength,
                metadata={
                    "crossover_type": "death_cross",
                    "ma_fast": curr_fast,
                    "ma_slow": curr_slow
                }
            )
        
        return TradeSignal(Signal.HOLD)
