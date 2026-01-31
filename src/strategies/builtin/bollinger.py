"""Bollinger Bands Strategy."""

from typing import Any, Dict
import pandas as pd

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class BollingerStrategy(BaseStrategy):
    """
    Bollinger Bands Mean Reversion Strategy.
    
    Generates BUY signals when price touches/crosses below the lower band.
    Generates SELL signals when price touches/crosses above the upper band.
    """
    
    name = "Bollinger Bands"
    description = "Mean reversion using Bollinger Bands"
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters for Bollinger Bands strategy."""
        return {
            "period": 20,
            "std_dev": 2.0
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "period": {
                "type": "int",
                "min": 5,
                "max": 100,
                "description": "Moving average period"
            },
            "std_dev": {
                "type": "float",
                "min": 0.5,
                "max": 4.0,
                "description": "Standard deviation multiplier"
            }
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return self._params["period"] + 1
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Bollinger Bands."""
        period = self._params["period"]
        std_dev = self._params["std_dev"]
        
        # Middle band (SMA)
        df["bb_middle"] = df["close"].rolling(window=period).mean()
        
        # Standard deviation
        rolling_std = df["close"].rolling(window=period).std()
        
        # Upper and lower bands
        df["bb_upper"] = df["bb_middle"] + (rolling_std * std_dev)
        df["bb_lower"] = df["bb_middle"] - (rolling_std * std_dev)
        
        # Bandwidth (volatility indicator)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        
        # %B indicator (where price is relative to bands)
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze for Bollinger Bands signals.
        
        Args:
            df: DataFrame with calculated Bollinger Bands
            index: Current candle index
            
        Returns:
            TradeSignal based on band touches
        """
        if index < 1:
            return TradeSignal(Signal.HOLD)
        
        # Check if we have valid values
        required_cols = ["bb_upper", "bb_lower", "bb_middle", "bb_pct"]
        for col in required_cols:
            if pd.isna(df.iloc[index][col]):
                return TradeSignal(Signal.HOLD)
        
        curr = df.iloc[index]
        prev = df.iloc[index - 1]
        
        close = curr["close"]
        bb_lower = curr["bb_lower"]
        bb_upper = curr["bb_upper"]
        bb_middle = curr["bb_middle"]
        bb_pct = curr["bb_pct"]
        
        # BUY: Price crosses below lower band or bounces from it
        if close <= bb_lower or (prev["close"] <= prev["bb_lower"] and close > bb_lower):
            # Stronger signal the more oversold
            strength = min(1.0, max(0.5, 1 - bb_pct))
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=strength,
                stop_loss=bb_lower * 0.99,  # 1% below lower band
                take_profit=bb_middle,  # Target middle band
                metadata={
                    "bb_pct": bb_pct,
                    "close": close,
                    "bb_lower": bb_lower,
                    "bb_upper": bb_upper,
                    "condition": "lower_band_touch"
                }
            )
        
        # SELL: Price crosses above upper band or drops from it
        if close >= bb_upper or (prev["close"] >= prev["bb_upper"] and close < bb_upper):
            strength = min(1.0, max(0.5, bb_pct))
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=strength,
                stop_loss=bb_upper * 1.01,  # 1% above upper band
                take_profit=bb_middle,
                metadata={
                    "bb_pct": bb_pct,
                    "close": close,
                    "bb_lower": bb_lower,
                    "bb_upper": bb_upper,
                    "condition": "upper_band_touch"
                }
            )
        
        return TradeSignal(Signal.HOLD)
