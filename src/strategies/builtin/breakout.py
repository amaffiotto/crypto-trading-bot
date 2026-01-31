"""
Breakout Strategy - Momentum trading on price breakouts.

Identifies when price breaks out of consolidation ranges
with volume confirmation for momentum trades.

Best used on: 1h, 4h timeframes
Best markets: After consolidation periods, high volatility moves
"""

from typing import Any, Dict
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Trading Strategy with Volume Confirmation.
    
    Tracks recent highs/lows to identify support/resistance.
    Generates signals when price breaks out with strong volume.
    
    Features:
    - Dynamic support/resistance based on recent price action
    - Volume confirmation requirement
    - ATR-based stop-loss placement
    - Avoids false breakouts with confirmation candle
    
    Best used on: 1h, 4h timeframes
    """
    
    name = "Breakout"
    description = "Trade breakouts from consolidation with volume confirmation."
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters."""
        return {
            "lookback_period": 20,      # Candles to find highs/lows
            "volume_multiplier": 1.5,   # Volume must be X times average
            "atr_period": 14,           # ATR for stop-loss calculation
            "atr_stop_multiplier": 2.0, # Stop-loss at X * ATR
            "min_consolidation": 5,     # Min candles in range before breakout
            "breakout_margin": 0.001,   # Price must exceed level by this %
            "use_close_confirmation": True,  # Wait for close above level
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "lookback_period": {
                "type": "int",
                "min": 10,
                "max": 100,
                "description": "Candles to determine support/resistance"
            },
            "volume_multiplier": {
                "type": "float",
                "min": 1.0,
                "max": 5.0,
                "description": "Volume must be X times average"
            },
            "atr_stop_multiplier": {
                "type": "float",
                "min": 1.0,
                "max": 5.0,
                "description": "Stop-loss ATR multiplier"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return max(
            self._params["lookback_period"],
            self._params["atr_period"]
        ) + 10
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate support/resistance levels and volatility."""
        lookback = self._params["lookback_period"]
        atr_period = self._params["atr_period"]
        
        # Rolling high and low for resistance/support
        df["resistance"] = df["high"].rolling(window=lookback).max()
        df["support"] = df["low"].rolling(window=lookback).min()
        
        # Previous resistance/support (excluding current candle)
        df["prev_resistance"] = df["high"].shift(1).rolling(window=lookback).max()
        df["prev_support"] = df["low"].shift(1).rolling(window=lookback).min()
        
        # Range and consolidation detection
        df["range_size"] = df["resistance"] - df["support"]
        df["range_pct"] = (df["range_size"] / df["close"]) * 100
        
        # Detect tight consolidation (small range)
        df["avg_range"] = df["range_pct"].rolling(window=lookback).mean()
        df["is_consolidating"] = df["range_pct"] < df["avg_range"]
        
        # Count consolidation candles
        df["consolidation_count"] = df["is_consolidating"].groupby(
            (~df["is_consolidating"]).cumsum()
        ).cumsum()
        
        # ATR for stop-loss
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=atr_period).mean()
        
        # Volume analysis
        df["volume_sma"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]
        
        # Momentum
        df["momentum"] = df["close"].pct_change(periods=5) * 100
        
        # Check if breaking resistance or support
        margin = self._params["breakout_margin"]
        df["breaking_resistance"] = df["close"] > df["prev_resistance"] * (1 + margin)
        df["breaking_support"] = df["close"] < df["prev_support"] * (1 - margin)
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Generate breakout signals.
        
        BUY: Price breaks above resistance with volume
        SELL: Price breaks below support with volume (or trailing stop)
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        if pd.isna(row["atr"]) or pd.isna(row["resistance"]):
            return TradeSignal(Signal.HOLD)
        
        vol_mult = self._params["volume_multiplier"]
        min_consol = self._params["min_consolidation"]
        atr_mult = self._params["atr_stop_multiplier"]
        
        close = row["close"]
        resistance = row["prev_resistance"]
        support = row["prev_support"]
        atr = row["atr"]
        volume_ratio = row["volume_ratio"]
        consolidation = prev["consolidation_count"]  # Consolidation before breakout
        momentum = row["momentum"]
        
        breaking_up = row["breaking_resistance"]
        breaking_down = row["breaking_support"]
        was_breaking_up = prev["breaking_resistance"]
        was_breaking_down = prev["breaking_support"]
        
        # Volume confirmation
        volume_confirmed = volume_ratio >= vol_mult
        
        # Was in consolidation
        had_consolidation = consolidation >= min_consol
        
        # BULLISH BREAKOUT
        if breaking_up and not was_breaking_up:  # Just broke out
            if volume_confirmed:
                strength = 0.5
                
                # Stronger if had consolidation
                if had_consolidation:
                    strength += 0.2
                
                # Stronger if volume is very high
                if volume_ratio > 2.0:
                    strength += 0.2
                elif volume_ratio > 1.5:
                    strength += 0.1
                
                # Stronger if momentum is positive
                if momentum > 2:
                    strength += 0.1
                
                stop_loss = close - (atr * atr_mult)
                
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=min(1.0, strength),
                    metadata={
                        "breakout_level": resistance,
                        "volume_ratio": volume_ratio,
                        "consolidation_candles": consolidation,
                        "atr": atr,
                        "suggested_stop": stop_loss,
                        "momentum": momentum,
                        "reason": "bullish_breakout"
                    }
                )
        
        # BEARISH BREAKOUT / EXIT
        if breaking_down and not was_breaking_down:
            if volume_confirmed:
                strength = 0.5
                
                if had_consolidation:
                    strength += 0.2
                if volume_ratio > 2.0:
                    strength += 0.2
                if momentum < -2:
                    strength += 0.1
                
                return TradeSignal(
                    signal=Signal.SELL,
                    strength=min(1.0, strength),
                    metadata={
                        "breakout_level": support,
                        "volume_ratio": volume_ratio,
                        "consolidation_candles": consolidation,
                        "momentum": momentum,
                        "reason": "bearish_breakout"
                    }
                )
        
        return TradeSignal(Signal.HOLD)
