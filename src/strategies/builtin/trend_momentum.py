"""
Trend + Momentum Strategy - More robust trading strategy.

Combines multiple indicators for better signal quality:
- EMA 200 for trend direction (only trade with the trend)
- RSI for momentum confirmation
- MACD for entry timing
- ATR for volatility-based stops
"""

from typing import Any, Dict
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class TrendMomentumStrategy(BaseStrategy):
    """
    Trend Following + Momentum Strategy.
    
    This strategy only trades in the direction of the major trend,
    uses momentum confirmation, and has stricter entry conditions.
    
    Rules:
    - Only BUY when price > EMA200 (uptrend) AND RSI < 70 AND MACD bullish
    - Only SELL when price < EMA200 (downtrend) OR RSI > 80 OR MACD bearish
    - Requires volume confirmation
    """
    
    name = "Trend Momentum"
    description = "Trade with trend, confirm with momentum indicators"
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters."""
        return {
            # Trend
            "trend_ema": 200,
            # Momentum
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            # MACD
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            # Filters
            "volume_filter": True,
            "volume_sma": 20,
            "min_volume_ratio": 1.0,  # Volume must be at least equal to average
            # Risk management
            "atr_period": 14,
            "atr_multiplier": 2.0,  # For stop-loss calculation
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "trend_ema": {
                "type": "int",
                "min": 50,
                "max": 500,
                "description": "EMA period for trend detection"
            },
            "rsi_period": {
                "type": "int",
                "min": 5,
                "max": 30,
                "description": "RSI period"
            },
            "rsi_oversold": {
                "type": "int",
                "min": 10,
                "max": 40,
                "description": "RSI oversold level"
            },
            "rsi_overbought": {
                "type": "int",
                "min": 60,
                "max": 90,
                "description": "RSI overbought level"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return max(
            self._params["trend_ema"],
            self._params["macd_slow"] + self._params["macd_signal"],
            self._params["volume_sma"],
            self._params["atr_period"]
        ) + 5
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators."""
        # Trend EMA
        df["ema_trend"] = df["close"].ewm(
            span=self._params["trend_ema"], adjust=False
        ).mean()
        
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
        
        # MACD
        ema_fast = df["close"].ewm(
            span=self._params["macd_fast"], adjust=False
        ).mean()
        ema_slow = df["close"].ewm(
            span=self._params["macd_slow"], adjust=False
        ).mean()
        df["macd"] = ema_fast - ema_slow
        df["macd_signal"] = df["macd"].ewm(
            span=self._params["macd_signal"], adjust=False
        ).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        
        # Volume SMA
        df["volume_sma"] = df["volume"].rolling(
            window=self._params["volume_sma"]
        ).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]
        
        # ATR for volatility
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=self._params["atr_period"]).mean()
        
        # Trend direction
        df["uptrend"] = df["close"] > df["ema_trend"]
        df["downtrend"] = df["close"] < df["ema_trend"]
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze for trading signals.
        
        BUY conditions (all must be true):
        1. Price above EMA200 (uptrend)
        2. RSI not overbought (< 70)
        3. RSI coming out of oversold OR MACD bullish crossover
        4. Volume above average (if filter enabled)
        
        SELL conditions (any can be true):
        1. RSI overbought (> 80)
        2. MACD bearish crossover while in position
        3. Price drops below EMA200 (trend reversal)
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        required = ["ema_trend", "rsi", "macd", "macd_signal", "atr", "volume_sma"]
        for col in required:
            if pd.isna(row[col]) or pd.isna(prev[col]):
                return TradeSignal(Signal.HOLD)
        
        # Current values
        close = row["close"]
        ema = row["ema_trend"]
        rsi = row["rsi"]
        prev_rsi = prev["rsi"]
        macd = row["macd"]
        macd_sig = row["macd_signal"]
        prev_macd = prev["macd"]
        prev_macd_sig = prev["macd_signal"]
        volume_ratio = row["volume_ratio"]
        atr = row["atr"]
        
        # Trend check
        in_uptrend = close > ema
        in_downtrend = close < ema
        
        # Volume filter
        volume_ok = True
        if self._params["volume_filter"]:
            volume_ok = volume_ratio >= self._params["min_volume_ratio"]
        
        # RSI conditions
        rsi_oversold = self._params["rsi_oversold"]
        rsi_overbought = self._params["rsi_overbought"]
        rsi_was_oversold = prev_rsi < rsi_oversold
        rsi_exiting_oversold = rsi_was_oversold and rsi >= rsi_oversold
        rsi_not_overbought = rsi < rsi_overbought
        rsi_is_overbought = rsi > 80  # Strong overbought for exit
        
        # MACD conditions
        macd_bullish_cross = prev_macd <= prev_macd_sig and macd > macd_sig
        macd_bearish_cross = prev_macd >= prev_macd_sig and macd < macd_sig
        macd_positive = macd > 0
        
        # BUY SIGNAL
        # Strong conditions: uptrend + momentum confirmation + volume
        if in_uptrend and rsi_not_overbought and volume_ok:
            # Either RSI exiting oversold OR MACD bullish cross with positive MACD
            if rsi_exiting_oversold or (macd_bullish_cross and macd_positive):
                # Calculate signal strength
                strength = 0.5
                
                # Boost for RSI near oversold
                if rsi < 40:
                    strength += 0.2
                
                # Boost for strong MACD
                if macd > 0 and macd > macd_sig:
                    strength += 0.2
                
                # Boost for high volume
                if volume_ratio > 1.5:
                    strength += 0.1
                
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=min(1.0, strength),
                    metadata={
                        "trend": "uptrend",
                        "rsi": rsi,
                        "macd": macd,
                        "volume_ratio": volume_ratio,
                        "atr": atr,
                        "suggested_stop": close - (atr * self._params["atr_multiplier"]),
                        "reason": "rsi_oversold_exit" if rsi_exiting_oversold else "macd_bullish"
                    }
                )
        
        # SELL SIGNAL
        # Exit on: trend reversal, RSI overbought, or MACD bearish cross
        sell_reasons = []
        
        if in_downtrend:
            sell_reasons.append("trend_reversal")
        
        if rsi_is_overbought:
            sell_reasons.append("rsi_overbought")
        
        if macd_bearish_cross:
            sell_reasons.append("macd_bearish")
        
        if sell_reasons:
            strength = 0.3 * len(sell_reasons)  # More reasons = stronger signal
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=min(1.0, strength),
                metadata={
                    "trend": "downtrend" if in_downtrend else "uptrend",
                    "rsi": rsi,
                    "macd": macd,
                    "reasons": sell_reasons
                }
            )
        
        return TradeSignal(Signal.HOLD)
