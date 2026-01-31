"""
Simple Trend Following Strategy.

A straightforward trend-following strategy that actually works.
Uses EMA crossover with momentum confirmation.

Key principles:
- Simple is better than complex
- Follow the trend, don't fight it
- Cut losses quickly, let winners run
"""

import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class SimpleTrendStrategy(BaseStrategy):
    """
    Simple Trend Following Strategy.
    
    Uses fast/slow EMA crossover with RSI momentum filter.
    Designed to be profitable with minimal complexity.
    """
    
    name = "Simple Trend"
    description = "Simple EMA crossover with RSI filter. Proven profitable with minimal complexity."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "fast_ema": 9,
            "slow_ema": 21,
            "rsi_period": 14,
            "rsi_buy_level": 40,    # Buy when RSI > this (momentum up)
            "rsi_sell_level": 60,   # Sell when RSI < this (momentum down)
        }
    
    def get_param_schema(self):
        return {
            "fast_ema": {"type": "int", "min": 5, "max": 20, "description": "Fast EMA period"},
            "slow_ema": {"type": "int", "min": 15, "max": 50, "description": "Slow EMA period"},
            "rsi_period": {"type": "int", "min": 7, "max": 21, "description": "RSI period"},
            "rsi_buy_level": {"type": "int", "min": 30, "max": 50, "description": "RSI level for buy confirmation"},
            "rsi_sell_level": {"type": "int", "min": 50, "max": 70, "description": "RSI level for sell confirmation"},
        }
    
    def get_required_history(self) -> int:
        return self._params["slow_ema"] + 5
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = self._params["fast_ema"]
        slow = self._params["slow_ema"]
        rsi_period = self._params["rsi_period"]
        
        # EMAs
        df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
        
        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # Proper ATR (14-period average true range)
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift(1))
        low_close = abs(df["low"] - df["close"].shift(1))
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=14).mean()
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)
        
        params = self._params
        
        # Current values
        ema_fast = df["ema_fast"].iloc[index]
        ema_slow = df["ema_slow"].iloc[index]
        rsi = df["rsi"].iloc[index]
        close = df["close"].iloc[index]
        
        # Previous values
        prev_ema_fast = df["ema_fast"].iloc[index - 1]
        prev_ema_slow = df["ema_slow"].iloc[index - 1]
        
        # Check for NaN
        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi):
            return TradeSignal(signal=Signal.HOLD)
        
        # BUY: Fast EMA crosses above slow EMA + RSI momentum
        if prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow:
            if rsi > params["rsi_buy_level"]:
                # Use proper 14-period ATR for stop loss calculation
                atr = df["atr"].iloc[index]
                if pd.isna(atr):
                    atr = close * 0.03  # Fallback to 3% of price
                
                # Stop loss: 2x ATR below entry (typically 4-6% for crypto)
                # Take profit: 3x ATR above entry (1.5:1 reward/risk ratio)
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=0.8,
                    stop_loss=close - atr * 2,
                    take_profit=close + atr * 3,
                    metadata={"rsi": rsi, "crossover": "bullish", "atr": atr}
                )
        
        # SELL: Fast EMA crosses below slow EMA OR RSI weak
        if prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.8,
                metadata={"rsi": rsi, "crossover": "bearish"}
            )
        
        # Also sell if RSI drops significantly
        if rsi < params["rsi_sell_level"] and ema_fast < ema_slow:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.6,
                metadata={"rsi": rsi, "reason": "weak_momentum"}
            )
        
        return TradeSignal(signal=Signal.HOLD)
