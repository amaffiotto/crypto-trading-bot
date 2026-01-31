"""
Mean Reversion Strategy - Works in ranging/sideways markets.

This strategy profits from price returning to the mean after
extreme deviations. Better for sideways markets.
"""

from typing import Any, Dict
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy using Bollinger Bands and RSI.
    
    Buys when price is oversold AND at lower Bollinger Band.
    Sells when price reaches middle band or becomes overbought.
    
    Best used on higher timeframes (4h, 1d) in ranging markets.
    """
    
    name = "Mean Reversion"
    description = "Buy oversold extremes, sell at mean. Best for ranging markets."
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters."""
        return {
            # Bollinger Bands
            "bb_period": 20,
            "bb_std": 2.0,
            # RSI
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            # Entry thresholds
            "bb_lower_threshold": 0.05,  # How close to lower band (5%)
            "bb_upper_threshold": 0.05,  # How close to upper band (5%)
            # Exit
            "exit_at_middle": True,  # Exit when price reaches middle band
            "partial_exit": False,   # Partial exit at middle, rest at upper
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "bb_period": {
                "type": "int",
                "min": 10,
                "max": 50,
                "description": "Bollinger Bands period"
            },
            "bb_std": {
                "type": "float",
                "min": 1.0,
                "max": 3.0,
                "description": "Bollinger Bands standard deviation"
            },
            "rsi_period": {
                "type": "int",
                "min": 5,
                "max": 30,
                "description": "RSI period"
            },
            "rsi_oversold": {
                "type": "int",
                "min": 15,
                "max": 40,
                "description": "RSI oversold level"
            },
            "rsi_overbought": {
                "type": "int",
                "min": 60,
                "max": 85,
                "description": "RSI overbought level"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return max(self._params["bb_period"], self._params["rsi_period"]) + 5
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Bollinger Bands and RSI."""
        # Bollinger Bands
        period = self._params["bb_period"]
        std_dev = self._params["bb_std"]
        
        df["bb_middle"] = df["close"].rolling(window=period).mean()
        rolling_std = df["close"].rolling(window=period).std()
        df["bb_upper"] = df["bb_middle"] + (rolling_std * std_dev)
        df["bb_lower"] = df["bb_middle"] - (rolling_std * std_dev)
        
        # Bollinger Band width (for volatility)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        
        # %B - Where price is within bands (0 = lower, 1 = upper)
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        
        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(
            window=self._params["rsi_period"]
        ).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(
            window=self._params["rsi_period"]
        ).mean()
        rs = gain / loss.replace(0, np.inf)
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # Price momentum
        df["momentum"] = df["close"].pct_change(periods=5) * 100
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze for mean reversion signals.
        
        BUY when:
        - Price near lower Bollinger Band (%B < 0.05)
        - RSI oversold (< 30)
        - Not in strong downtrend
        
        SELL when:
        - Price reaches middle band (if exit_at_middle)
        - Price reaches upper band
        - RSI overbought (> 70)
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        required = ["bb_middle", "bb_upper", "bb_lower", "bb_pct", "rsi"]
        for col in required:
            if pd.isna(row[col]):
                return TradeSignal(Signal.HOLD)
        
        close = row["close"]
        bb_pct = row["bb_pct"]
        prev_bb_pct = prev["bb_pct"]
        rsi = row["rsi"]
        prev_rsi = prev["rsi"]
        bb_lower = row["bb_lower"]
        bb_middle = row["bb_middle"]
        bb_upper = row["bb_upper"]
        bb_width = row["bb_width"]
        
        # Thresholds
        lower_threshold = self._params["bb_lower_threshold"]
        upper_threshold = 1 - self._params["bb_upper_threshold"]
        rsi_oversold = self._params["rsi_oversold"]
        rsi_overbought = self._params["rsi_overbought"]
        
        # BUY CONDITIONS
        # Price at or below lower band AND RSI oversold
        price_at_lower = bb_pct <= lower_threshold
        price_bouncing = bb_pct > prev_bb_pct  # Starting to bounce
        rsi_is_oversold = rsi < rsi_oversold
        rsi_turning_up = rsi > prev_rsi  # RSI starting to rise
        
        if price_at_lower and rsi_is_oversold:
            # Extra confirmation: price starting to bounce
            if price_bouncing or rsi_turning_up:
                # Signal strength based on how extreme the condition
                strength = 0.5
                
                # More extreme = stronger signal
                if bb_pct < 0:  # Price below lower band
                    strength += 0.2
                if rsi < 25:
                    strength += 0.2
                if price_bouncing and rsi_turning_up:
                    strength += 0.1
                
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=min(1.0, strength),
                    metadata={
                        "bb_pct": bb_pct,
                        "rsi": rsi,
                        "bb_width": bb_width,
                        "target": bb_middle if self._params["exit_at_middle"] else bb_upper,
                        "reason": "oversold_bounce"
                    }
                )
        
        # SELL CONDITIONS
        sell_reasons = []
        strength = 0
        
        # Exit at middle band (mean)
        if self._params["exit_at_middle"]:
            if prev_bb_pct < 0.5 and bb_pct >= 0.5:  # Crossed middle from below
                sell_reasons.append("reached_mean")
                strength += 0.5
        
        # Exit at upper band
        if bb_pct >= upper_threshold:
            sell_reasons.append("reached_upper_band")
            strength += 0.3
        
        # RSI overbought
        if rsi > rsi_overbought:
            sell_reasons.append("rsi_overbought")
            strength += 0.4
        
        # Strong overbought
        if rsi > 80 and bb_pct > 0.9:
            sell_reasons.append("extreme_overbought")
            strength += 0.3
        
        if sell_reasons:
            return TradeSignal(
                signal=Signal.SELL,
                strength=min(1.0, strength),
                metadata={
                    "bb_pct": bb_pct,
                    "rsi": rsi,
                    "reasons": sell_reasons
                }
            )
        
        return TradeSignal(Signal.HOLD)
