"""
Donchian Channel Breakout Strategy (Turtle Trading).

The legendary Turtle Trading system adapted for cryptocurrency.
Uses Donchian Channels to identify breakouts with:
- 20-period channel for entries
- 10-period channel for exits
- EMA trend filter for direction confirmation
- ATR-based position sizing

This is one of the most battle-tested trend-following systems.
"""

import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Channel Breakout Strategy.
    
    Based on the famous Turtle Trading system. Enters on breakouts
    of the highest high/lowest low over N periods, exits on breaks
    of shorter-term channels.
    
    Highly effective in trending markets with clear directional moves.
    """
    
    name = "Donchian Breakout"
    description = "Turtle Trading system: buy on breakout of N-period high, sell on breakout of M-period low. Proven trend follower."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "entry_period": 20,        # Donchian channel for entries
            "exit_period": 10,         # Donchian channel for exits
            "ema_filter_period": 50,   # EMA trend filter (0 to disable)
            "atr_period": 14,          # ATR for volatility
            "atr_stop_multiplier": 2.0, # Stop loss = ATR * multiplier
            "use_ema_filter": True,    # Use EMA trend filter
        }
    
    def get_param_schema(self):
        return {
            "entry_period": {
                "type": "int", "min": 10, "max": 55,
                "description": "Period for entry channel (higher = fewer trades)"
            },
            "exit_period": {
                "type": "int", "min": 5, "max": 20,
                "description": "Period for exit channel"
            },
            "ema_filter_period": {
                "type": "int", "min": 20, "max": 200,
                "description": "EMA period for trend filter"
            },
            "atr_period": {
                "type": "int", "min": 7, "max": 21,
                "description": "ATR period for volatility"
            },
            "atr_stop_multiplier": {
                "type": "float", "min": 1.0, "max": 4.0,
                "description": "ATR multiplier for stop loss"
            },
            "use_ema_filter": {
                "type": "bool",
                "description": "Only trade in direction of EMA trend"
            }
        }
    
    def get_required_history(self) -> int:
        params = self._params
        return max(
            params["entry_period"],
            params["exit_period"],
            params["ema_filter_period"],
            params["atr_period"]
        ) + 5
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Donchian Channels and supporting indicators."""
        params = self._params
        entry_period = params["entry_period"]
        exit_period = params["exit_period"]
        ema_period = params["ema_filter_period"]
        atr_period = params["atr_period"]
        
        # Entry channel (higher highs and lower lows)
        df["dc_upper"] = df["high"].rolling(window=entry_period).max()
        df["dc_lower"] = df["low"].rolling(window=entry_period).min()
        df["dc_middle"] = (df["dc_upper"] + df["dc_lower"]) / 2
        
        # Exit channel (shorter period)
        df["exit_upper"] = df["high"].rolling(window=exit_period).max()
        df["exit_lower"] = df["low"].rolling(window=exit_period).min()
        
        # Previous values (to detect breakout THIS candle)
        df["prev_dc_upper"] = df["dc_upper"].shift(1)
        df["prev_dc_lower"] = df["dc_lower"].shift(1)
        
        # EMA trend filter
        if params["use_ema_filter"]:
            df["ema_filter"] = df["close"].ewm(span=ema_period, adjust=False).mean()
        
        # ATR for stop loss calculation
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift(1))
        low_close = abs(df["low"] - df["close"].shift(1))
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=atr_period).mean()
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """Generate trading signal based on Donchian breakout."""
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)
        
        params = self._params
        row = df.iloc[index]
        prev_row = df.iloc[index - 1]
        
        close = row["close"]
        high = row["high"]
        low = row["low"]
        
        prev_dc_upper = row.get("prev_dc_upper")
        prev_dc_lower = row.get("prev_dc_lower")
        exit_lower = row.get("exit_lower")
        atr = row.get("atr", 0)
        
        # Check for valid values
        if pd.isna(prev_dc_upper) or pd.isna(prev_dc_lower):
            return TradeSignal(signal=Signal.HOLD)
        
        # EMA trend filter
        if params["use_ema_filter"]:
            ema = row.get("ema_filter")
            if pd.isna(ema):
                return TradeSignal(signal=Signal.HOLD)
            uptrend = close > ema
            downtrend = close < ema
        else:
            uptrend = True
            downtrend = True
        
        # ENTRY: Breakout above previous period's high (only in uptrend)
        if high > prev_dc_upper and uptrend:
            stop_loss = close - (atr * params["atr_stop_multiplier"])
            take_profit = close + (atr * params["atr_stop_multiplier"] * 2)
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=0.8,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "breakout_level": prev_dc_upper,
                    "atr": atr,
                    "type": "channel_breakout"
                }
            )
        
        # EXIT: Price falls below exit channel lower band
        if low < exit_lower:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.8,
                metadata={
                    "exit_level": exit_lower,
                    "type": "channel_exit"
                }
            )
        
        return TradeSignal(signal=Signal.HOLD)
