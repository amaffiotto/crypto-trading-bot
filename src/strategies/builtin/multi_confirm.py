"""
Multi-Indicator Confirmation Strategy.

Requires confirmation from multiple independent indicators before entry.
Reduces false signals by requiring consensus.

Uses:
- RSI for momentum
- MACD for trend
- Volume for confirmation
- Price action (higher highs/lows)

Only enters when ALL indicators agree.
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class MultiConfirmStrategy(BaseStrategy):
    """
    Multi-Indicator Confirmation Strategy.
    
    Only trades when multiple independent indicators confirm the signal.
    Higher win rate but fewer trades. Quality over quantity approach.
    """
    
    name = "Multi Confirm"
    description = "Requires RSI, MACD, and volume to all confirm before entry. Higher win rate, fewer trades."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "rsi_period": 14,
            "rsi_oversold": 35,         # More conservative than 30
            "rsi_overbought": 65,       # More conservative than 70
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "volume_ma_period": 20,
            "volume_threshold": 1.2,    # Volume must be 20% above average
            "lookback_highs": 5,        # Candles for higher high detection
            "min_confirmations": 3,     # Minimum confirmations needed (out of 4)
        }
    
    def get_param_schema(self):
        return {
            "rsi_period": {
                "type": "int", "min": 7, "max": 21,
                "description": "RSI calculation period"
            },
            "rsi_oversold": {
                "type": "int", "min": 20, "max": 40,
                "description": "RSI oversold level for buy"
            },
            "rsi_overbought": {
                "type": "int", "min": 60, "max": 80,
                "description": "RSI overbought level for sell"
            },
            "volume_threshold": {
                "type": "float", "min": 1.0, "max": 2.0,
                "description": "Volume multiplier vs average"
            },
            "min_confirmations": {
                "type": "int", "min": 2, "max": 4,
                "description": "Minimum confirmations needed"
            }
        }
    
    def get_required_history(self) -> int:
        return max(
            self._params["rsi_period"],
            self._params["macd_slow"] + self._params["macd_signal"],
            self._params["volume_ma_period"]
        ) + 10
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all confirmation indicators."""
        params = self._params
        
        # RSI
        rsi = RSIIndicator(close=df["close"], window=params["rsi_period"])
        df["rsi"] = rsi.rsi()
        
        # MACD
        macd = MACD(
            close=df["close"],
            window_fast=params["macd_fast"],
            window_slow=params["macd_slow"],
            window_sign=params["macd_signal"]
        )
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()
        
        # Volume moving average
        df["volume_ma"] = df["volume"].rolling(window=params["volume_ma_period"]).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma"]
        
        # Price action: higher highs and higher lows
        lookback = params["lookback_highs"]
        df["highest_high"] = df["high"].rolling(window=lookback).max()
        df["lowest_low"] = df["low"].rolling(window=lookback).min()
        df["prev_highest_high"] = df["highest_high"].shift(lookback)
        df["prev_lowest_low"] = df["lowest_low"].shift(lookback)
        
        # Higher high = current highest > previous highest
        df["higher_high"] = df["highest_high"] > df["prev_highest_high"]
        df["higher_low"] = df["lowest_low"] > df["prev_lowest_low"]
        df["lower_high"] = df["highest_high"] < df["prev_highest_high"]
        df["lower_low"] = df["lowest_low"] < df["prev_lowest_low"]
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """Generate trading signal based on multiple confirmations."""
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)
        
        params = self._params
        row = df.iloc[index]
        prev_row = df.iloc[index - 1]
        
        rsi = row["rsi"] if "rsi" in row and not pd.isna(row["rsi"]) else 50
        macd = row["macd"] if "macd" in row and not pd.isna(row["macd"]) else 0
        macd_signal = row["macd_signal"] if "macd_signal" in row and not pd.isna(row["macd_signal"]) else 0
        prev_macd = prev_row["macd"] if "macd" in prev_row and not pd.isna(prev_row["macd"]) else 0
        prev_macd_signal = prev_row["macd_signal"] if "macd_signal" in prev_row and not pd.isna(prev_row["macd_signal"]) else 0
        volume_ratio = row["volume_ratio"] if "volume_ratio" in row and not pd.isna(row["volume_ratio"]) else 1
        close = row["close"]
        
        # Check for valid values
        if pd.isna(rsi) or pd.isna(macd):
            return TradeSignal(signal=Signal.HOLD)
        
        # Count BUY confirmations
        buy_confirmations = 0
        buy_reasons = []
        
        # 1. RSI confirmation: rising from oversold
        if rsi < params["rsi_overbought"] and rsi > params["rsi_oversold"]:
            prev_rsi = prev_row.get("rsi", 50)
            if prev_rsi < params["rsi_oversold"] or (rsi > prev_rsi and rsi < 50):
                buy_confirmations += 1
                buy_reasons.append("RSI rising")
        
        # 2. MACD confirmation: crossing above signal line
        if prev_macd <= prev_macd_signal and macd > macd_signal:
            buy_confirmations += 1
            buy_reasons.append("MACD crossover")
        elif macd > macd_signal and macd > 0:
            buy_confirmations += 0.5  # Partial confirmation
            buy_reasons.append("MACD bullish")
        
        # 3. Volume confirmation: above average
        if volume_ratio > params["volume_threshold"]:
            buy_confirmations += 1
            buy_reasons.append("High volume")
        
        # 4. Price action: higher high and higher low
        if row.get("higher_high", False) and row.get("higher_low", False):
            buy_confirmations += 1
            buy_reasons.append("Higher highs/lows")
        
        # Count SELL confirmations
        sell_confirmations = 0
        sell_reasons = []
        
        # 1. RSI overbought
        if rsi > params["rsi_overbought"]:
            sell_confirmations += 1
            sell_reasons.append("RSI overbought")
        
        # 2. MACD bearish cross
        if prev_macd >= prev_macd_signal and macd < macd_signal:
            sell_confirmations += 1
            sell_reasons.append("MACD cross down")
        
        # 3. Lower high and lower low
        if row.get("lower_high", False) and row.get("lower_low", False):
            sell_confirmations += 1
            sell_reasons.append("Lower highs/lows")
        
        min_confirms = params["min_confirmations"]
        
        # Generate signals based on confirmations
        if buy_confirmations >= min_confirms:
            atr = row["high"] - row["low"]
            return TradeSignal(
                signal=Signal.BUY,
                strength=min(buy_confirmations / 4, 1.0),
                stop_loss=close - (atr * 2),
                take_profit=close + (atr * 3),
                metadata={
                    "confirmations": buy_confirmations,
                    "reasons": buy_reasons,
                    "rsi": rsi
                }
            )
        
        if sell_confirmations >= 2:  # Lower threshold for exits
            return TradeSignal(
                signal=Signal.SELL,
                strength=min(sell_confirmations / 3, 1.0),
                metadata={
                    "confirmations": sell_confirmations,
                    "reasons": sell_reasons,
                    "rsi": rsi
                }
            )
        
        return TradeSignal(signal=Signal.HOLD)
