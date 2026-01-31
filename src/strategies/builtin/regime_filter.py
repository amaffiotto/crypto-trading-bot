"""
Regime Filter Strategy.

Uses market regime detection to only trade in favorable conditions.
Identifies three regimes:
1. TRENDING UP - Trade long only
2. TRENDING DOWN - Exit or short
3. RANGING - No trades (most losses occur here)

Based on research showing regime filters reduce drawdown by 23%+
while maintaining similar returns.
"""

import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class RegimeFilterStrategy(BaseStrategy):
    """
    Regime Filter Strategy.
    
    Only trades when market is in a clear trend regime.
    Uses multiple EMAs and volatility to detect regime.
    Avoids the biggest pitfall of most strategies: trading in
    sideways/choppy markets.
    """
    
    name = "Regime Filter"
    description = "Detects market regime (trend/range) and only trades in trending conditions. Reduces drawdown significantly."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "fast_ema": 8,              # Fast EMA for signals
            "medium_ema": 21,           # Medium EMA for trend
            "slow_ema": 55,             # Slow EMA for regime
            "regime_ema": 200,          # Very slow EMA for major trend
            "atr_period": 14,           # ATR period
            "regime_threshold": 0.02,   # Min % distance between EMAs
            "volatility_filter": True,  # Use volatility regime filter
        }
    
    def get_param_schema(self):
        return {
            "fast_ema": {
                "type": "int", "min": 5, "max": 15,
                "description": "Fast EMA for entry signals"
            },
            "medium_ema": {
                "type": "int", "min": 15, "max": 30,
                "description": "Medium EMA for trend"
            },
            "slow_ema": {
                "type": "int", "min": 40, "max": 100,
                "description": "Slow EMA for regime detection"
            },
            "regime_ema": {
                "type": "int", "min": 100, "max": 300,
                "description": "Long-term EMA for major trend"
            },
            "regime_threshold": {
                "type": "float", "min": 0.01, "max": 0.05,
                "description": "Minimum EMA separation for trend"
            },
            "volatility_filter": {
                "type": "bool",
                "description": "Enable volatility-based regime filter"
            }
        }
    
    def get_required_history(self) -> int:
        return self._params["regime_ema"] + 20
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate EMAs and regime detection indicators."""
        params = self._params
        
        # Multiple EMAs
        df["ema_fast"] = df["close"].ewm(span=params["fast_ema"], adjust=False).mean()
        df["ema_medium"] = df["close"].ewm(span=params["medium_ema"], adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=params["slow_ema"], adjust=False).mean()
        df["ema_regime"] = df["close"].ewm(span=params["regime_ema"], adjust=False).mean()
        
        # EMA alignment score (-1 to 1)
        # 1 = perfect bullish alignment, -1 = perfect bearish alignment
        df["ema_alignment"] = 0.0
        bullish_align = (
            (df["ema_fast"] > df["ema_medium"]) & 
            (df["ema_medium"] > df["ema_slow"]) &
            (df["ema_slow"] > df["ema_regime"])
        )
        bearish_align = (
            (df["ema_fast"] < df["ema_medium"]) & 
            (df["ema_medium"] < df["ema_slow"]) &
            (df["ema_slow"] < df["ema_regime"])
        )
        df.loc[bullish_align, "ema_alignment"] = 1.0
        df.loc[bearish_align, "ema_alignment"] = -1.0
        
        # EMA spread (distance between fast and slow as % of price)
        df["ema_spread"] = abs(df["ema_fast"] - df["ema_slow"]) / df["close"]
        
        # ATR for volatility regime
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift(1))
        low_close = abs(df["low"] - df["close"].shift(1))
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=params["atr_period"]).mean()
        df["atr_pct"] = df["atr"] / df["close"]
        
        # Volatility regime (compare current ATR to historical)
        df["atr_sma"] = df["atr"].rolling(window=50).mean()
        df["volatility_regime"] = df["atr"] / df["atr_sma"]
        
        # Regime classification
        # 1 = bullish trend, -1 = bearish trend, 0 = ranging
        df["regime"] = 0
        
        # Bullish regime: EMAs aligned bullish AND spread > threshold
        bullish_regime = (df["ema_alignment"] == 1) & (df["ema_spread"] > params["regime_threshold"])
        # Bearish regime: EMAs aligned bearish AND spread > threshold
        bearish_regime = (df["ema_alignment"] == -1) & (df["ema_spread"] > params["regime_threshold"])
        
        df.loc[bullish_regime, "regime"] = 1
        df.loc[bearish_regime, "regime"] = -1
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """Generate trading signal based on regime filter."""
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)
        
        params = self._params
        row = df.iloc[index]
        prev_row = df.iloc[index - 1]
        
        regime = row.get("regime", 0)
        ema_fast = row.get("ema_fast")
        ema_medium = row.get("ema_medium")
        atr = row.get("atr", 0)
        close = row["close"]
        
        # Volatility filter: don't trade in extremely low volatility
        if params["volatility_filter"]:
            vol_regime = row.get("volatility_regime", 1.0)
            if vol_regime < 0.5:  # Volatility too low
                return TradeSignal(
                    signal=Signal.HOLD,
                    metadata={"reason": "Low volatility regime"}
                )
        
        # ONLY trade in trending regimes
        if regime == 0:
            return TradeSignal(
                signal=Signal.HOLD,
                metadata={"reason": "Ranging market - no trade"}
            )
        
        # In bullish regime: look for pullback entries
        if regime == 1:
            prev_ema_fast = prev_row.get("ema_fast")
            # Entry: Fast EMA crosses above medium EMA (momentum confirmation)
            if prev_ema_fast <= prev_row.get("ema_medium") and ema_fast > ema_medium:
                stop_loss = close - (atr * 2)
                take_profit = close + (atr * 3)
                
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=0.85,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "regime": "bullish",
                        "ema_spread": row.get("ema_spread", 0)
                    }
                )
        
        # In bearish regime or regime change: exit
        if regime == -1:
            return TradeSignal(
                signal=Signal.SELL,
                strength=0.85,
                metadata={"regime": "bearish"}
            )
        
        return TradeSignal(signal=Signal.HOLD)
