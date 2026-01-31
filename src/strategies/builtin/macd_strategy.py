"""MACD (Moving Average Convergence Divergence) Strategy."""

from typing import Any, Dict
import pandas as pd

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class MACDStrategy(BaseStrategy):
    """
    MACD Signal Line Crossover Strategy.
    
    Generates BUY signals when MACD line crosses above the signal line.
    Generates SELL signals when MACD line crosses below the signal line.
    """
    
    name = "MACD Strategy"
    description = "Buy/sell on MACD and signal line crossovers"
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters for MACD strategy."""
        return {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "fast_period": {
                "type": "int",
                "min": 2,
                "max": 50,
                "description": "Fast EMA period"
            },
            "slow_period": {
                "type": "int",
                "min": 10,
                "max": 100,
                "description": "Slow EMA period"
            },
            "signal_period": {
                "type": "int",
                "min": 2,
                "max": 30,
                "description": "Signal line EMA period"
            }
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return self._params["slow_period"] + self._params["signal_period"] + 1
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate MACD, signal line, and histogram."""
        fast = self._params["fast_period"]
        slow = self._params["slow_period"]
        signal = self._params["signal_period"]
        
        # Calculate EMAs
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        
        # MACD line
        df["macd"] = ema_fast - ema_slow
        
        # Signal line
        df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
        
        # Histogram
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze for MACD crossover signals.
        
        Args:
            df: DataFrame with calculated MACD
            index: Current candle index
            
        Returns:
            TradeSignal based on MACD crossovers
        """
        if index < 1:
            return TradeSignal(Signal.HOLD)
        
        # Check if we have valid MACD values
        required_cols = ["macd", "macd_signal", "macd_hist"]
        for col in required_cols:
            if pd.isna(df.iloc[index][col]) or pd.isna(df.iloc[index - 1][col]):
                return TradeSignal(Signal.HOLD)
        
        prev_macd = df.iloc[index - 1]["macd"]
        prev_signal = df.iloc[index - 1]["macd_signal"]
        curr_macd = df.iloc[index]["macd"]
        curr_signal = df.iloc[index]["macd_signal"]
        curr_hist = df.iloc[index]["macd_hist"]
        
        # BUY: MACD crosses above signal line
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            # Stronger signal when crossing from negative to positive
            strength = 0.7
            if curr_macd > 0:
                strength = 0.9
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=strength,
                metadata={
                    "macd": curr_macd,
                    "signal": curr_signal,
                    "histogram": curr_hist,
                    "crossover": "bullish"
                }
            )
        
        # SELL: MACD crosses below signal line
        if prev_macd >= prev_signal and curr_macd < curr_signal:
            strength = 0.7
            if curr_macd < 0:
                strength = 0.9
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=strength,
                metadata={
                    "macd": curr_macd,
                    "signal": curr_signal,
                    "histogram": curr_hist,
                    "crossover": "bearish"
                }
            )
        
        return TradeSignal(Signal.HOLD)
