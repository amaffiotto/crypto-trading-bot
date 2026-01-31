"""
Triple EMA Strategy - Enhanced trend following.

Uses 3 EMAs (fast, medium, slow) to confirm trend alignment.
Only trades when all 3 EMAs are aligned in the same direction.

This reduces false signals compared to simple 2-EMA crossover
by requiring stronger trend confirmation.

Best used on: 4h, 1d timeframes
Best markets: Trending markets with clear direction
"""

from typing import Any, Dict
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class TripleEMAStrategy(BaseStrategy):
    """
    Triple EMA Trend Alignment Strategy.
    
    Uses 3 EMAs to confirm trend:
    - Fast EMA (8): Quick reaction to price
    - Medium EMA (21): Intermediate trend
    - Slow EMA (55): Major trend direction
    
    Signals:
    - BUY when Fast > Medium > Slow (aligned uptrend) for 2+ candles
    - SELL when Fast < Medium < Slow (aligned downtrend) for 2+ candles
    
    Additional filters:
    - Volume confirmation
    - ADX for trend strength
    
    Best used on: 4h, 1d timeframes
    """
    
    name = "Triple EMA"
    description = "Trade only when all 3 EMAs align. Strong trend confirmation."
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters."""
        return {
            "ema_fast": 8,
            "ema_medium": 21,
            "ema_slow": 55,
            "confirmation_candles": 2,  # Candles to confirm alignment
            "use_volume_filter": True,
            "volume_sma": 20,
            "min_volume_ratio": 0.8,    # Volume must be at least 80% of average
            "use_adx_filter": True,
            "adx_period": 14,
            "adx_threshold": 20,        # ADX > 20 indicates trending market
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "ema_fast": {
                "type": "int",
                "min": 3,
                "max": 20,
                "description": "Fast EMA period"
            },
            "ema_medium": {
                "type": "int",
                "min": 10,
                "max": 50,
                "description": "Medium EMA period"
            },
            "ema_slow": {
                "type": "int",
                "min": 30,
                "max": 200,
                "description": "Slow EMA period"
            },
            "confirmation_candles": {
                "type": "int",
                "min": 1,
                "max": 5,
                "description": "Candles to confirm trend alignment"
            },
            "adx_threshold": {
                "type": "int",
                "min": 15,
                "max": 40,
                "description": "Minimum ADX for trend confirmation"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return max(
            self._params["ema_slow"],
            self._params["adx_period"] * 2,
            self._params["volume_sma"]
        ) + 10
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Triple EMA and supporting indicators."""
        fast = self._params["ema_fast"]
        medium = self._params["ema_medium"]
        slow = self._params["ema_slow"]
        adx_period = self._params["adx_period"]
        vol_sma = self._params["volume_sma"]
        
        # Calculate EMAs
        df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
        df["ema_medium"] = df["close"].ewm(span=medium, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
        
        # Trend alignment
        df["bullish_aligned"] = (df["ema_fast"] > df["ema_medium"]) & \
                                (df["ema_medium"] > df["ema_slow"])
        df["bearish_aligned"] = (df["ema_fast"] < df["ema_medium"]) & \
                                (df["ema_medium"] < df["ema_slow"])
        
        # Count consecutive alignment
        df["bullish_count"] = df["bullish_aligned"].groupby(
            (~df["bullish_aligned"]).cumsum()
        ).cumsum()
        df["bearish_count"] = df["bearish_aligned"].groupby(
            (~df["bearish_aligned"]).cumsum()
        ).cumsum()
        
        # Volume
        df["volume_sma"] = df["volume"].rolling(window=vol_sma).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]
        
        # ADX (Average Directional Index)
        df["tr"] = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs()
        ], axis=1).max(axis=1)
        
        df["dm_plus"] = np.where(
            (df["high"] - df["high"].shift()) > (df["low"].shift() - df["low"]),
            np.maximum(df["high"] - df["high"].shift(), 0),
            0
        )
        df["dm_minus"] = np.where(
            (df["low"].shift() - df["low"]) > (df["high"] - df["high"].shift()),
            np.maximum(df["low"].shift() - df["low"], 0),
            0
        )
        
        df["atr"] = df["tr"].rolling(window=adx_period).mean()
        df["di_plus"] = 100 * (df["dm_plus"].rolling(window=adx_period).mean() / df["atr"])
        df["di_minus"] = 100 * (df["dm_minus"].rolling(window=adx_period).mean() / df["atr"])
        
        dx = 100 * (df["di_plus"] - df["di_minus"]).abs() / (df["di_plus"] + df["di_minus"])
        df["adx"] = dx.rolling(window=adx_period).mean()
        
        # EMA separation (trend strength)
        df["ema_separation"] = ((df["ema_fast"] - df["ema_slow"]) / df["ema_slow"]) * 100
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Generate signals based on EMA alignment.
        
        BUY: All EMAs aligned bullish for N candles
        SELL: All EMAs aligned bearish for N candles
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        if pd.isna(row["adx"]) or pd.isna(row["ema_slow"]):
            return TradeSignal(Signal.HOLD)
        
        confirm = self._params["confirmation_candles"]
        use_volume = self._params["use_volume_filter"]
        use_adx = self._params["use_adx_filter"]
        min_vol = self._params["min_volume_ratio"]
        adx_thresh = self._params["adx_threshold"]
        
        bullish_count = int(row["bullish_count"])
        prev_bullish_count = int(prev["bullish_count"])
        bearish_count = int(row["bearish_count"])
        prev_bearish_count = int(prev["bearish_count"])
        
        volume_ok = row["volume_ratio"] >= min_vol if use_volume else True
        adx_ok = row["adx"] >= adx_thresh if use_adx else True
        
        close = row["close"]
        ema_fast = row["ema_fast"]
        ema_medium = row["ema_medium"]
        ema_slow = row["ema_slow"]
        adx = row["adx"]
        separation = row["ema_separation"]
        
        # BUY: Just confirmed bullish alignment
        if bullish_count >= confirm and prev_bullish_count < confirm:
            if volume_ok and adx_ok:
                strength = 0.5
                
                # Stronger if ADX is high
                if adx > 30:
                    strength += 0.2
                elif adx > 25:
                    strength += 0.1
                
                # Stronger if good separation
                if separation > 2:
                    strength += 0.2
                
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=min(1.0, strength),
                    metadata={
                        "ema_fast": ema_fast,
                        "ema_medium": ema_medium,
                        "ema_slow": ema_slow,
                        "adx": adx,
                        "separation_pct": separation,
                        "alignment_candles": bullish_count,
                        "reason": "triple_ema_bullish"
                    }
                )
        
        # SELL: Just confirmed bearish alignment
        if bearish_count >= confirm and prev_bearish_count < confirm:
            if volume_ok and adx_ok:
                strength = 0.5
                
                if adx > 30:
                    strength += 0.2
                elif adx > 25:
                    strength += 0.1
                
                if separation < -2:
                    strength += 0.2
                
                return TradeSignal(
                    signal=Signal.SELL,
                    strength=min(1.0, strength),
                    metadata={
                        "ema_fast": ema_fast,
                        "ema_medium": ema_medium,
                        "ema_slow": ema_slow,
                        "adx": adx,
                        "separation_pct": separation,
                        "alignment_candles": bearish_count,
                        "reason": "triple_ema_bearish"
                    }
                )
        
        return TradeSignal(Signal.HOLD)
