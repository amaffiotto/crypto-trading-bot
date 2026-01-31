"""
Momentum RSI Strategy.

A momentum-based strategy using RSI with trend confirmation.
Buy oversold in uptrends, sell overbought in downtrends.

This is a mean-reversion strategy that works well in volatile markets.
"""

import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class MomentumRSIStrategy(BaseStrategy):
    """
    Momentum RSI Strategy.
    
    Buys when RSI is oversold and price is above EMA (uptrend).
    Sells when RSI is overbought or trend reverses.
    """
    
    name = "Momentum RSI"
    description = "Buy oversold RSI in uptrends, sell overbought. Works well in volatile crypto markets."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "trend_ema": 50,
            "exit_rsi": 50,  # Exit when RSI returns to neutral
        }
    
    def get_param_schema(self):
        return {
            "rsi_period": {"type": "int", "min": 7, "max": 21, "description": "RSI period"},
            "rsi_oversold": {"type": "int", "min": 20, "max": 40, "description": "Oversold level"},
            "rsi_overbought": {"type": "int", "min": 60, "max": 80, "description": "Overbought level"},
            "trend_ema": {"type": "int", "min": 20, "max": 100, "description": "EMA for trend"},
        }
    
    def get_required_history(self) -> int:
        return max(self._params["rsi_period"], self._params["trend_ema"]) + 5
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        rsi_period = self._params["rsi_period"]
        trend_ema = self._params["trend_ema"]
        
        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # Trend EMA
        df["trend_ema"] = df["close"].ewm(span=trend_ema, adjust=False).mean()
        
        # Previous RSI for crossover detection
        df["prev_rsi"] = df["rsi"].shift(1)
        
        # Proper ATR (14-period)
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
        
        rsi = df["rsi"].iloc[index]
        prev_rsi = df["prev_rsi"].iloc[index]
        trend_ema = df["trend_ema"].iloc[index]
        close = df["close"].iloc[index]
        
        if pd.isna(rsi) or pd.isna(trend_ema) or pd.isna(prev_rsi):
            return TradeSignal(signal=Signal.HOLD)
        
        uptrend = close > trend_ema
        downtrend = close < trend_ema
        
        # Get proper ATR
        atr = df["atr"].iloc[index]
        if pd.isna(atr):
            atr = close * 0.03  # Fallback to 3%
        
        # BUY: RSI crosses up from oversold in uptrend
        if prev_rsi < params["rsi_oversold"] and rsi >= params["rsi_oversold"]:
            if uptrend:
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=0.9,
                    stop_loss=close - atr * 1.5,
                    take_profit=close + atr * 2.5,
                    metadata={"rsi": rsi, "trend": "up", "atr": atr}
                )
        
        # Also buy if RSI bounces from very oversold
        if rsi < 25 and uptrend and prev_rsi < rsi:  # RSI turning up
            return TradeSignal(
                signal=Signal.BUY,
                strength=0.7,
                stop_loss=close - atr * 2,
                take_profit=close + atr * 3,
                metadata={"rsi": rsi, "reason": "very_oversold", "atr": atr}
            )
        
        # SELL: RSI overbought or crosses down
        if rsi > params["rsi_overbought"]:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.9,
                metadata={"rsi": rsi, "reason": "overbought"}
            )
        
        # Sell if trend reverses
        if downtrend and rsi < params["exit_rsi"]:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.7,
                metadata={"rsi": rsi, "reason": "trend_reversal"}
            )
        
        return TradeSignal(signal=Signal.HOLD)
