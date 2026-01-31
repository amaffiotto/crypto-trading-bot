"""RSI (Relative Strength Index) Strategy."""

from typing import Any, Dict
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class RSIStrategy(BaseStrategy):
    """
    RSI Overbought/Oversold Strategy.
    
    Generates BUY signals when RSI crosses above the oversold level.
    Generates SELL signals when RSI crosses below the overbought level.
    """
    
    name = "RSI Strategy"
    description = "Buy on oversold, sell on overbought RSI levels"
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters for RSI strategy."""
        return {
            "period": 14,
            "overbought": 70,
            "oversold": 30
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "period": {
                "type": "int",
                "min": 2,
                "max": 50,
                "description": "RSI calculation period"
            },
            "overbought": {
                "type": "int",
                "min": 50,
                "max": 95,
                "description": "Overbought threshold (sell signal)"
            },
            "oversold": {
                "type": "int",
                "min": 5,
                "max": 50,
                "description": "Oversold threshold (buy signal)"
            }
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return self._params["period"] + 2
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        # Use Wilder's smoothing for subsequent values
        for i in range(period, len(prices)):
            avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate RSI indicator."""
        period = self._params["period"]
        df["rsi"] = self._calculate_rsi(df["close"], period)
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze for RSI signals.
        
        Args:
            df: DataFrame with calculated RSI
            index: Current candle index
            
        Returns:
            TradeSignal based on RSI levels
        """
        if index < 1:
            return TradeSignal(Signal.HOLD)
        
        # Check if we have valid RSI values
        if pd.isna(df.iloc[index]["rsi"]) or pd.isna(df.iloc[index - 1]["rsi"]):
            return TradeSignal(Signal.HOLD)
        
        prev_rsi = df.iloc[index - 1]["rsi"]
        curr_rsi = df.iloc[index]["rsi"]
        
        overbought = self._params["overbought"]
        oversold = self._params["oversold"]
        
        # BUY: RSI crosses above oversold level
        if prev_rsi <= oversold and curr_rsi > oversold:
            # Stronger signal if RSI was very low
            strength = min(1.0, (oversold - prev_rsi + 10) / 20)
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=strength,
                metadata={
                    "rsi": curr_rsi,
                    "prev_rsi": prev_rsi,
                    "condition": "oversold_exit"
                }
            )
        
        # SELL: RSI crosses below overbought level
        if prev_rsi >= overbought and curr_rsi < overbought:
            strength = min(1.0, (prev_rsi - overbought + 10) / 20)
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=strength,
                metadata={
                    "rsi": curr_rsi,
                    "prev_rsi": prev_rsi,
                    "condition": "overbought_exit"
                }
            )
        
        return TradeSignal(Signal.HOLD)
