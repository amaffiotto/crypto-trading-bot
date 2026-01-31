"""
Volatility Breakout Strategy.

Uses Average True Range (ATR) to identify and trade volatility breakouts.
When price moves more than N * ATR from the previous close, it signals
a potential trend start.

This strategy is designed for:
- Catching the start of big moves
- Avoiding choppy sideways markets
- Using volatility-adjusted position sizing
"""

import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class VolatilityBreakoutStrategy(BaseStrategy):
    """
    Volatility Breakout Strategy.
    
    Enters when price breaks out of its normal volatility range.
    Uses ATR to dynamically adjust breakout thresholds.
    Excellent for catching trend starts.
    """
    
    name = "Volatility Breakout"
    description = "Trades breakouts when price moves beyond normal volatility. Catches big moves early."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "atr_period": 14,
            "breakout_multiplier": 1.5,  # Price must move 1.5x ATR
            "ema_period": 20,            # EMA for trend direction
            "volume_confirm": True,      # Require volume confirmation
            "volume_multiplier": 1.5,    # Volume must be 1.5x average
            "consolidation_period": 5,   # Min candles of consolidation
            "max_atr_percent": 0.08,     # Max ATR as % of price (avoid crazy vol)
        }
    
    def get_param_schema(self):
        return {
            "atr_period": {
                "type": "int", "min": 7, "max": 21,
                "description": "ATR calculation period"
            },
            "breakout_multiplier": {
                "type": "float", "min": 1.0, "max": 3.0,
                "description": "ATR multiplier for breakout detection"
            },
            "ema_period": {
                "type": "int", "min": 10, "max": 50,
                "description": "EMA period for trend filter"
            },
            "volume_confirm": {
                "type": "bool",
                "description": "Require volume confirmation"
            },
            "volume_multiplier": {
                "type": "float", "min": 1.0, "max": 3.0,
                "description": "Required volume vs average"
            }
        }
    
    def get_required_history(self) -> int:
        params = self._params
        return max(params["atr_period"], params["ema_period"], 20) + 10
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate ATR and breakout levels."""
        params = self._params
        atr_period = params["atr_period"]
        
        # True Range calculation
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift(1))
        low_close = abs(df["low"] - df["close"].shift(1))
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # ATR
        df["atr"] = true_range.rolling(window=atr_period).mean()
        df["atr_pct"] = df["atr"] / df["close"]
        
        # Breakout levels
        multiplier = params["breakout_multiplier"]
        df["upper_breakout"] = df["close"].shift(1) + (df["atr"] * multiplier)
        df["lower_breakout"] = df["close"].shift(1) - (df["atr"] * multiplier)
        
        # EMA for trend
        df["ema"] = df["close"].ewm(span=params["ema_period"], adjust=False).mean()
        
        # Volume analysis
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma"]
        
        # Consolidation detection (low volatility period before breakout)
        df["range_pct"] = (df["high"] - df["low"]) / df["close"]
        df["avg_range"] = df["range_pct"].rolling(window=params["consolidation_period"]).mean()
        df["is_consolidating"] = df["avg_range"] < df["atr_pct"]
        
        # Momentum (close position within range)
        df["momentum"] = (df["close"] - df["low"]) / (df["high"] - df["low"] + 0.0001)
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """Generate trading signal based on volatility breakout."""
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)
        
        params = self._params
        row = df.iloc[index]
        
        close = row["close"]
        high = row["high"]
        low = row["low"]
        atr = row.get("atr", 0)
        atr_pct = row.get("atr_pct", 0)
        upper_breakout = row.get("upper_breakout")
        lower_breakout = row.get("lower_breakout")
        ema = row.get("ema")
        volume_ratio = row.get("volume_ratio", 1)
        momentum = row.get("momentum", 0.5)
        
        # Validate indicators
        if pd.isna(atr) or pd.isna(upper_breakout) or pd.isna(ema):
            return TradeSignal(signal=Signal.HOLD)
        
        # Filter: Don't trade in extremely volatile conditions
        if atr_pct > params["max_atr_percent"]:
            return TradeSignal(
                signal=Signal.HOLD,
                metadata={"reason": "Volatility too high"}
            )
        
        # Volume confirmation check
        volume_confirmed = True
        if params["volume_confirm"]:
            volume_confirmed = volume_ratio >= params["volume_multiplier"]
        
        # BULLISH BREAKOUT
        if high > upper_breakout:
            # Additional filters
            uptrend = close > ema
            strong_close = momentum > 0.6  # Close in upper 40% of range
            
            if uptrend and strong_close and volume_confirmed:
                stop_loss = close - (atr * 2)
                take_profit = close + (atr * 3)
                
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=min(volume_ratio / 2, 1.0),
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "breakout_type": "bullish",
                        "atr": atr,
                        "volume_ratio": volume_ratio,
                        "momentum": momentum
                    }
                )
        
        # BEARISH BREAKOUT / EXIT
        if low < lower_breakout:
            downtrend = close < ema
            weak_close = momentum < 0.4  # Close in lower 40% of range
            
            if downtrend or weak_close:
                return TradeSignal(
                    signal=Signal.SELL,
                    strength=0.8,
                    metadata={
                        "breakout_type": "bearish",
                        "atr": atr
                    }
                )
        
        return TradeSignal(signal=Signal.HOLD)
