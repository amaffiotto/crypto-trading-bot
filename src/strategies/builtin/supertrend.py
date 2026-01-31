"""
SuperTrend Strategy - Proven trend-following strategy.

Based on ATR (Average True Range) to determine trend direction.
Works well on 4h and 1d timeframes for BTC and major altcoins.

Research shows this strategy is effective in trending markets
when combined with proper position sizing and stop-loss.
"""

from typing import Any, Dict
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class SuperTrendStrategy(BaseStrategy):
    """
    SuperTrend Indicator Strategy.
    
    The SuperTrend indicator uses ATR to create dynamic support/resistance levels.
    - When price is above SuperTrend line -> Bullish (green)
    - When price is below SuperTrend line -> Bearish (red)
    
    Signals:
    - BUY when price crosses above SuperTrend (trend turns bullish)
    - SELL when price crosses below SuperTrend (trend turns bearish)
    
    Best used on: 4h, 1d timeframes
    Best markets: Trending (avoid sideways)
    """
    
    name = "SuperTrend"
    description = "ATR-based trend following. Buy on bullish crossover, sell on bearish."
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters optimized for crypto."""
        return {
            "atr_period": 10,      # ATR calculation period
            "multiplier": 3.0,     # ATR multiplier for band width
            "use_close": True,     # Use close price (vs HL2)
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "atr_period": {
                "type": "int",
                "min": 5,
                "max": 50,
                "description": "ATR calculation period"
            },
            "multiplier": {
                "type": "float",
                "min": 1.0,
                "max": 6.0,
                "description": "ATR multiplier (higher = less sensitive)"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return self._params["atr_period"] + 10
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate SuperTrend indicator."""
        atr_period = self._params["atr_period"]
        multiplier = self._params["multiplier"]
        
        # Calculate ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=atr_period).mean()
        
        # Calculate basic upper and lower bands
        hl2 = (df["high"] + df["low"]) / 2
        df["basic_upper"] = hl2 + (multiplier * df["atr"])
        df["basic_lower"] = hl2 - (multiplier * df["atr"])
        
        # Calculate SuperTrend
        df["supertrend"] = 0.0
        df["supertrend_direction"] = 1  # 1 = bullish, -1 = bearish
        
        for i in range(1, len(df)):
            # Final upper band
            if df["basic_upper"].iloc[i] < df["supertrend"].iloc[i-1] or \
               df["close"].iloc[i-1] > df["supertrend"].iloc[i-1]:
                final_upper = df["basic_upper"].iloc[i]
            else:
                final_upper = df["supertrend"].iloc[i-1] if df["supertrend_direction"].iloc[i-1] == -1 else df["basic_upper"].iloc[i]
            
            # Final lower band  
            if df["basic_lower"].iloc[i] > df["supertrend"].iloc[i-1] or \
               df["close"].iloc[i-1] < df["supertrend"].iloc[i-1]:
                final_lower = df["basic_lower"].iloc[i]
            else:
                final_lower = df["supertrend"].iloc[i-1] if df["supertrend_direction"].iloc[i-1] == 1 else df["basic_lower"].iloc[i]
            
            # Determine direction
            if df["supertrend_direction"].iloc[i-1] == 1:  # Was bullish
                if df["close"].iloc[i] < final_lower:
                    df.loc[df.index[i], "supertrend"] = final_upper
                    df.loc[df.index[i], "supertrend_direction"] = -1
                else:
                    df.loc[df.index[i], "supertrend"] = final_lower
                    df.loc[df.index[i], "supertrend_direction"] = 1
            else:  # Was bearish
                if df["close"].iloc[i] > final_upper:
                    df.loc[df.index[i], "supertrend"] = final_lower
                    df.loc[df.index[i], "supertrend_direction"] = 1
                else:
                    df.loc[df.index[i], "supertrend"] = final_upper
                    df.loc[df.index[i], "supertrend_direction"] = -1
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Generate trading signals based on SuperTrend crossovers.
        
        BUY: When direction changes from bearish to bullish
        SELL: When direction changes from bullish to bearish
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        if pd.isna(row["supertrend"]) or pd.isna(prev["supertrend"]):
            return TradeSignal(Signal.HOLD)
        
        curr_dir = row["supertrend_direction"]
        prev_dir = prev["supertrend_direction"]
        close = row["close"]
        supertrend = row["supertrend"]
        atr = row["atr"]
        
        # BUY: Direction changed from bearish (-1) to bullish (1)
        if prev_dir == -1 and curr_dir == 1:
            # Calculate signal strength based on distance from SuperTrend
            distance = (close - supertrend) / close
            strength = min(1.0, 0.5 + abs(distance) * 10)
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=strength,
                metadata={
                    "supertrend": supertrend,
                    "direction": "bullish",
                    "atr": atr,
                    "suggested_stop": supertrend - atr,  # Stop below SuperTrend
                    "reason": "supertrend_bullish_cross"
                }
            )
        
        # SELL: Direction changed from bullish (1) to bearish (-1)
        if prev_dir == 1 and curr_dir == -1:
            distance = (supertrend - close) / close
            strength = min(1.0, 0.5 + abs(distance) * 10)
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=strength,
                metadata={
                    "supertrend": supertrend,
                    "direction": "bearish",
                    "atr": atr,
                    "reason": "supertrend_bearish_cross"
                }
            )
        
        return TradeSignal(Signal.HOLD)
